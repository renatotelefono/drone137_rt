import asyncio
import importlib.util
import os
import socket
from pathlib import Path

from adapters.llama import LlamaBackend
from scripts.tools import DATA, BUILD, ROOT, digest, native_mac
import json


def model_paths():
    manifest_path = DATA / "models/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    paths = []
    for item in manifest["files"]:
        path = DATA / "models" / item["name"]
        if not item.get("sha256") or digest(path) != item["sha256"]:
            raise RuntimeError(f"Model hash mismatch: {item['name']}")
        paths.append(path)
    if len(paths) != 2 or not manifest.get("revision"):
        raise RuntimeError("A pinned, verified model/projector pair is required")
    return paths


def unused_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} already in use; stop the existing service explicitly") from exc


async def start_model(owned):
    native_mac()
    unused_port(8081)
    model, projector = model_paths()
    binary = BUILD / "llama.cpp/build/bin/llama-server"
    await owned.spawn("llama", [str(binary), "-m", str(model), "--mmproj", str(projector),
                               "--host", "127.0.0.1", "--port", "8081",
                               "-c", "2048", "-np", "1", "-ngl", "99"],
                      DATA / "logs/llama.log")
    backend = LlamaBackend(timeout=2)
    try:
        async with asyncio.timeout(90):
            while True:
                if not owned.healthy():
                    raise RuntimeError("Native runtime exited; inspect its local log")
                try:
                    await backend.health()
                    break
                except (OSError, RuntimeError, TimeoutError):
                    await asyncio.sleep(.5)
                except Exception as exc:
                    import aiohttp
                    if not isinstance(exc, aiohttp.ClientError):
                        raise
                    await asyncio.sleep(.5)
    finally:
        await backend.close()


async def start_native(owned, policy):
    native_mac()
    unused_port(50051)
    px4 = BUILD / "PX4-Autopilot"
    bridge = BUILD / "image-bridge/drone137-image-bridge"
    if not bridge.is_file() or not (DATA / "sim/worlds/courtyard.sdf").exists():
        raise RuntimeError("Run install-sim and validate the native camera bridge first")
    spec = importlib.util.find_spec("mavsdk")
    if spec is None:
        raise RuntimeError("Install the pinned sim dependency set")
    sdk = Path(os.environ.get("DRONE137_MAVSDK_SERVER",
                             Path(spec.origin).parent / "bin/mavsdk_server"))
    if not sdk.is_file():
        raise RuntimeError("Set DRONE137_MAVSDK_SERVER to a matching native server; bundled binary missing")
    if policy == "qwen":
        await start_model(owned)
    environment = dict(os.environ)
    environment.update({
        "PX4_GZ_WORLD": "courtyard", "HEADLESS": "1",
        "GZ_SIM_RESOURCE_PATH": f"{DATA / 'sim/models'}:{DATA / 'sim/worlds'}:{px4 / 'Tools/simulation/gz/models'}",
    })
    await owned.spawn("px4", ["bash", "-c",
                            'source "$1/.venv/bin/activate"; exec make px4_sitl gz_x500_mono_cam',
                            "_", str(px4)], DATA / "logs/px4.log", cwd=px4, env=environment)
    await owned.spawn("mavsdk", [str(sdk), "-p", "50051", "udpin://127.0.0.1:14540"],
                      DATA / "logs/mavsdk.log")
    return bridge, "/drone137/camera"
