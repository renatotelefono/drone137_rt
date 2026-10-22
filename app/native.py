import asyncio
import importlib.util
import os
import socket
from pathlib import Path

from adapters.llama import LlamaBackend
from scripts.tools import DATA, BUILD, ROOT, digest, native_mac
import json
import xml.etree.ElementTree as ET


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
        # Match the server's reuse semantics: a recently closed connection in
        # TIME_WAIT is not an active service. A live listener still blocks bind.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
                               "-c", "2048", "-np", "1", "-ngl", "99", "-t", "2",
                               "--cache-ram", "0", "--no-cache-prompt"],
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
        "PX4_GZ_STANDALONE": "1", "PX4_GZ_MODEL_NAME": "x500_mono_cam_0",
        "PX4_GZ_NO_FOLLOW": "1", "GZ_IP": "127.0.0.1",
        "PX4_SIM_MODEL": "gz_x500_mono_cam",
        "GZ_SIM_RESOURCE_PATH": f"{DATA / 'sim/models'}:{DATA / 'sim/worlds'}:{px4 / 'Tools/simulation/gz/models'}",
        "GZ_SIM_SYSTEM_PLUGIN_PATH": str(px4/'build/px4_sitl_default/src/modules/simulation/gz_plugins'),
    })
    # PX4's generated gz_env.sh hard-codes its upstream world/model directories.
    # Launch our own world and named vehicle, then attach PX4 in standalone mode.
    # This keeps generated assets local and avoids editing upstream source.
    tree = ET.parse(DATA/'sim/worlds/courtyard.sdf')
    include = ET.SubElement(tree.find('world'), 'include')
    ET.SubElement(include, 'uri').text = (DATA/'sim/models/x500_mono_cam/model.sdf').as_uri()
    ET.SubElement(include, 'name').text = 'x500_mono_cam_0'
    ET.SubElement(include, 'pose').text = '0 0 .3 0 0 0'
    native_world = DATA/'sim/worlds/courtyard-vehicle.sdf'
    tree.write(native_world)
    await owned.spawn('gazebo', [str(ROOT/'scripts/with-sim.sh'), 'gz', 'sim', '-r', '-s', str(native_world)],
                      DATA/'logs/gazebo.log', env=environment)
    await owned.spawn("px4", [str(ROOT/'scripts/with-sim.sh'),
                            str(px4/'build/px4_sitl_default/bin/px4'), '-d'],
                            DATA / "logs/px4.log", cwd=px4, env=environment)
    await owned.spawn("mavsdk", [str(sdk), "-p", "50051", "udpin://127.0.0.1:14540"],
                      DATA / "logs/mavsdk.log")
    return bridge, "/drone137/camera"
