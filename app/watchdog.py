import asyncio
import os
import json
from pathlib import Path

from app.portability import kill_tree, spawn_kwargs, terminate_tree


class ProcessSupervisor:
    """Own only explicitly launched process groups, including surviving children."""
    def __init__(self):
        self.processes = {}
        self.logs = []
        self.log_tasks = []
        self.log_limit_reached = False

    def _publish(self):
        path = os.environ.get("DRONE137_OWNERSHIP_FILE")
        if path:
            target = Path(path)
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps({name: p.pid for name, p in self.processes.items()}))
            temporary.replace(target)

    async def spawn(self, name: str, argv: list[str], log: Path, *, cwd=None, env=None):
        if name in self.processes:
            raise ValueError("process name already owned")
        log.parent.mkdir(parents=True, exist_ok=True)
        log_limit = 8 * 1024 * 1024
        existing = log.stat().st_size if log.exists() else 0
        if existing >= log_limit - 8192:
            raise RuntimeError(f"Native log cap reached: {log}; explicitly archive it before restarting")
        handle = log.open("ab")
        try:
            process = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd, env=env, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **spawn_kwargs())
        except BaseException:
            handle.close()
            raise
        self.logs.append(handle)
        self.processes[name] = process
        self._publish()
        async def drain():
            used = existing
            capped = False
            while chunk := await process.stdout.read(8192):
                if capped:
                    continue
                if used + len(chunk) > log_limit - 128:
                    handle.write(b"\n[drone137: 8 MiB log cap reached; additional output discarded; restart blocked]\n")
                    handle.flush()
                    self.log_limit_reached = True
                    capped = True
                else:
                    handle.write(chunk)
                    handle.flush()
                    used += len(chunk)
        self.log_tasks.append(asyncio.create_task(drain()))
        return process

    def healthy(self):
        return not self.log_limit_reached and all(p.returncode is None for p in self.processes.values())

    async def stop(self, name):
        process = self.processes.pop(name)
        terminate_tree(process.pid)
        try:
            await asyncio.wait_for(process.wait(), 3)
        except TimeoutError:
            pass
        # A group may still contain children even if its parent exited.
        kill_tree(process.pid)
        await process.wait()
        self._publish()

    async def close(self):
        # Stop SDK before simulator so its orphaned heartbeat cannot persist.
        names = sorted(self.processes, key=lambda n: n != "mavsdk")
        for name in names:
            await self.stop(name)
        await asyncio.gather(*self.log_tasks, return_exceptions=True)
        for handle in self.logs:
            handle.close()
        self.logs.clear()
