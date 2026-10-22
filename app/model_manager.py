import asyncio
import json
import platform
import shutil
import sys
import time
import uuid
import os

from adapters.llama import LlamaBackend, DECISION_SCHEMA
from app.model_store import ModelStore
from app.native import unused_port
from scripts.tools import DATA, BUILD, ROOT


class ModelManager:
    """One supported model, one owned process, one inference request."""
    def __init__(self, owned):
        self.owned = owned
        self.store = ModelStore(DATA / "models")
        self.backend = None
        self.job = None
        self.state = "stopped"
        self.job_name = None
        self.error = None
        self.check_result = None
        self.binary = BUILD / "llama.cpp/build/bin/llama-server"

    @property
    def ready(self):
        process = self.owned.processes.get("llama")
        return bool(self.backend and not self.backend.quarantined and process and process.returncode is None
                    and self.state == "ready")

    def status(self):
        process=self.owned.processes.get('llama')
        return {
            "name": "Qwen3-VL-2B-Instruct · Q4_K_M + Q8_0 projector",
            "state": self.state if self.state != "ready" or self.ready else "unavailable",
            "ready": self.ready, "busy": bool(self.job and not self.job.done()),
            "job": self.job_name, "error": self.error, "store": self.store.status(),
            "runtime_installed": self.binary.is_file(),
            "host": {"os": platform.system(), "architecture": platform.machine(),
                     "native_metal_candidate": platform.system() == "Darwin" and platform.machine() == "arm64",
                     "cmake": bool(shutil.which("cmake")), "compiler": bool(shutil.which("clang"))},
            "vision_check": self.check_result, "acceptance": "unverified",
            "app_pid":os.getpid(),"model_pid":process.pid if process and process.returncode is None else None,
        }

    def submit(self, name):
        if self.job and not self.job.done():
            raise RuntimeError("A model operation is already running")
        if name not in ("download", "verify", "install-runtime", "start", "stop", "check", "reset-partials"):
            raise ValueError("Unknown model operation")
        if name in ("download", "install-runtime", "reset-partials") and "llama" in self.owned.processes:
            raise RuntimeError("Stop the model before changing its files/runtime")
        self.job_name, self.error = name, None
        self.job = asyncio.create_task(self._perform(name))

    async def _perform(self, name):
        try:
            if name == "download":
                await asyncio.to_thread(self.store.download)
            elif name == "verify":
                await asyncio.to_thread(self.store.verify)
            elif name == "reset-partials":
                self.store.reset_partials()
            elif name == "install-runtime":
                if platform.system() != "Darwin" or platform.machine() != "arm64":
                    raise RuntimeError("Automatic native runtime installation currently requires an Apple Silicon Mac")
                process = await self.owned.spawn("runtime-build",
                    [sys.executable, "-m", "scripts.tools", "install-runtime"],
                    DATA / "logs/runtime-build.log", cwd=ROOT)
                code = await process.wait()
                await self.owned.stop("runtime-build")
                if code:
                    raise RuntimeError("Runtime build failed; inspect the bounded build log in Diagnostics")
            elif name == "start":
                await self.start()
            elif name == "stop":
                await self.stop()
            elif name == "check":
                await self.check()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            if name == "start":
                await self.stop()
            if self.backend and self.backend.quarantined:
                self.state = "restart_required"

    async def start(self):
        if self.ready:
            return
        if "llama" in self.owned.processes:
            await self.stop()
        self.state = "verifying"
        model, projector = await asyncio.to_thread(self.store.verify)
        if not self.binary.is_file():
            raise RuntimeError("Install the native runtime first")
        unused_port(8081)
        self.state = "starting"
        metal = platform.system() == "Darwin" and platform.machine() == "arm64"
        await self.owned.spawn("llama", [
            str(self.binary), "-m", str(model), "--mmproj", str(projector),
            "--host", "127.0.0.1", "--port", "8081", "-c", "2048", "-np", "1",
            # The server otherwise retains idle prompt states in an 8 GiB cache,
            # even though our requests disable prompt reuse. Inspections are stateless.
            "--cache-ram", "0", "--no-cache-prompt",
            "-ngl", "99" if metal else "0", "--threads", "2",
        ], DATA / "logs/llama.log")
        self.backend = LlamaBackend(timeout=6)
        async with asyncio.timeout(120):
            while True:
                if self.owned.processes["llama"].returncode is not None:
                    raise RuntimeError("llama-server exited; inspect Diagnostics")
                try:
                    await self.backend.health()
                    break
                except Exception:
                    await asyncio.sleep(.5)
        self.state = "ready"

    async def stop(self):
        if self.backend:
            await self.backend.close()
            self.backend = None
        if "llama" in self.owned.processes:
            await self.owned.stop("llama")
        self.state = "stopped"

    async def image(self, jpeg, prompt, schema, timeout=6, reference=None, max_tokens=128):
        if not self.ready:
            raise RuntimeError("Local model is not ready; download, verify and start it first")
        try:
            return await self.backend.image(jpeg, prompt, schema, time.monotonic()+timeout,
                                            reference=reference, max_tokens=max_tokens)
        except BaseException:
            if self.backend and self.backend.quarantined:
                self.state = "restart_required"
            raise

    async def text(self, prompt, schema, timeout=6):
        if not self.ready:
            raise RuntimeError('Local model is not ready')
        try:
            return await self.backend.text(prompt, schema, time.monotonic()+timeout)
        except BaseException:
            if self.backend and self.backend.quarantined:
                self.state = 'restart_required'
            raise

    async def check(self):
        from app.perception import inspect, VERSION
        self.check_result = None
        results = []
        for index, expected in ((1, 'open'), (2, 'closed')):
            jpeg = (ROOT / f'sim/assets/fixture-{index:02d}.jpg').read_bytes()
            started = time.monotonic()
            visual = await inspect(self.image, jpeg)
            observed = {'open_space': 'open', 'solid_surface': 'closed', 'uncertain': 'uncertain'}[visual['center']]
            results.append({'expected': expected, 'observed': observed, 'perception': visual,
                            'latency_s': time.monotonic()-started, 'correct': observed == expected})
        self.check_result = {"passed": all(r["correct"] for r in results), "results": results,
                             "real_inference": True, "images": "synthetic paired images", "perception_version": VERSION,
                             "host": platform.platform(), "actual_8gb_validation": "unverified"}
        from app.recorder import RunRecorder
        recorder = RunRecorder(DATA/"runs", uuid.uuid4().hex, 1024**3,
                               {"test": "actual local model paired-image check", "profile": "lean-8gb"})
        recorder._write(recorder.directory/"vision.json", json.dumps(self.check_result, indent=2).encode())
        recorder.finish(**self.check_result)

    async def close(self):
        self.store.cancel.set()
        if self.job and not self.job.done():
            # Download worker cooperatively stops at a chunk boundary; don't leave
            # a hidden worker downloading after the application closes.
            if self.job_name == "download":
                await self.job
            else:
                self.job.cancel()
                await asyncio.gather(self.job, return_exceptions=True)
        await self.stop()
