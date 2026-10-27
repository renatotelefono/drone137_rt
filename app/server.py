import argparse
import asyncio

from app.portability import install_stop_handlers
import json
import os
import re
import signal
import time
from pathlib import Path

from aiohttp import web

from adapters.fixtures import FakeDrone, ReplayCamera, ScriptedPolicy
from adapters.llama import LlamaBackend, QwenPolicy
from app.executor import MissionExecutor
from app.watchdog import ProcessSupervisor

ROOT = Path(__file__).resolve().parents[1]


@web.middleware
async def local_only(request, handler):
    if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
        raise web.HTTPForbidden(text="Loopback host required")
    if request.method == "POST" and request.headers.get("X-Drone137-Control") != "local":
        raise web.HTTPForbidden(text="Local control header required")
    try:
        return await handler(request)
    except (ValueError, RuntimeError) as exc:
        return web.json_response({"error": str(exc)}, status=409)


def make_app(executor):
    app = web.Application(middlewares=[local_only], client_max_size=4096)

    async def index(request):
        return web.FileResponse(ROOT / "app/ui/index.html")

    async def asset(request):
        return web.FileResponse(ROOT / "app/ui" / request.match_info["name"])

    async def status(request):
        return web.json_response(executor.snapshot())

    async def frame(request):
        image = executor.camera.latest()
        if image is None:
            raise web.HTTPServiceUnavailable(text="No camera frame")
        return web.Response(body=image.jpeg, content_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})

    async def control(request):
        operation = request.match_info["operation"]
        await getattr(executor, operation)()
        return web.json_response(executor.snapshot())

    async def report(request):
        episode = request.match_info["episode"]
        if not re.fullmatch(r"[a-f0-9]{32}", episode):
            raise web.HTTPNotFound()
        path = executor.runs / episode / "summary.json"
        if not path.is_file():
            raise web.HTTPNotFound(text="Report available after run completion")
        return web.FileResponse(path)

    app.router.add_get("/", index)
    app.router.add_get(r"/assets/{name:app.js|style.css}", asset)
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/frame", frame)
    app.router.add_post(r"/api/{operation:start|pause|land}", control)
    app.router.add_get("/reports/{episode}/summary.json", report)
    return app


async def serve(args):
    config = json.loads((ROOT / "config/lean-8gb.json").read_text())
    runs = Path(os.environ.get("DRONE137_DATA_DIR", ROOT / ".local/data")) / "runs"
    owned = ProcessSupervisor()
    executor = camera = policy = drone = runner = manager = None
    try:
        if args.mode == "recon":
            from app.model_manager import ModelManager
            from app.recon import Recon
            from app.recon_server import make_recon_app
            manager = ModelManager(owned)
            executor = Recon(manager, runs)
            runner = web.AppRunner(make_recon_app(executor))
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", args.port).start()
            print(json.dumps({"event": "app_listening", "port": args.port, "mode": "browser-kinematic-recon"}), flush=True)
            if args.open_browser:
                import webbrowser
                webbrowser.open(f"http://127.0.0.1:{args.port}/control")
            done = asyncio.Event()
            install_stop_handlers(asyncio.get_running_loop(), done.set)
            await done.wait()
            return
        if args.mode == "fixture":
            if args.profile != "cloud-dev" or args.policy != "scripted":
                raise ValueError("fixture mode requires --profile cloud-dev --policy scripted")
            camera = ReplayCamera([ROOT / "sim/assets/fixture-01.jpg", ROOT / "sim/assets/fixture-02.jpg"])
            drone = FakeDrone()
            policy = ScriptedPolicy()
        else:
            if args.profile != "lean-8gb":
                raise ValueError("native simulation requires lean-8gb")
            from app.native import start_native
            from adapters.mavsdk_drone import MavsdkDrone
            from adapters.camera import GazeboCamera
            bridge, topic = await start_native(owned, args.policy)
            camera = GazeboCamera(bridge, topic)
            drone = MavsdkDrone(speed_limit=config["speed_limit_m_s"])
            policy = QwenPolicy(LlamaBackend()) if args.policy == "qwen" else ScriptedPolicy()
        await camera.start()
        await drone.connect()
        if args.mode == 'sim':
            # Discovery of a topic alone does not prove that rendering or the
            # bridge works. Require a fresh native frame before offering Start.
            async with asyncio.timeout(15):
                while True:
                    if camera.error:
                        raise RuntimeError(f'Native camera unavailable: {camera.error}')
                    frame = camera.latest()
                    if frame and 0 <= time.monotonic()-frame.received_monotonic <= 1:
                        break
                    await asyncio.sleep(.1)
        if args.mode == "sim" and args.policy == "qwen":
            await policy.backend.health()
        provenance = {
            "profile": args.profile, "mode": args.mode, "policy": policy.identity,
            "real_inference": args.mode == "sim" and args.policy == "qwen",
            "real_camera": args.mode == "sim", "real_flight_dynamics": args.mode == "sim",
            "physical_transport": False,
            "capture_clock": "sensor_simulation" if args.mode == "sim" else "host_receipt_only",
            "mac_virtual_acceptance": "unverified", "lean_memory_budget": "unverified",
            "actual_8gb_validation": "unverified", "hardware_gate": "blocked",
        }
        executor = MissionExecutor(drone, camera, policy, config, runs, provenance,
                                   process_health=owned.healthy)
        runner = web.AppRunner(make_app(executor))
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", args.port).start()
        print(json.dumps({"event": "app_listening", "port": args.port, **provenance}), flush=True)
        done = asyncio.Event()
        loop = asyncio.get_running_loop()
        install_stop_handlers(loop, done.set)
        await done.wait()
    finally:
        try:
            if runner:
                await runner.cleanup()
            if executor:
                await executor.close()
            else:
                for resource in (camera, drone, policy):
                    if resource:
                        await resource.close()
        finally:
            if manager:
                await manager.close()
            await owned.close()


def main():
    parser = argparse.ArgumentParser(description="Local inspection prototype; simulation only")
    parser.add_argument("--mode", choices=["recon", "sim", "fixture"], default="recon")
    parser.add_argument("--profile", choices=["lean-8gb", "cloud-dev"], default="lean-8gb")
    parser.add_argument("--policy", choices=["qwen", "scripted"], default="scripted")
    parser.add_argument("--scenario", choices=["courtyard"], default="courtyard")
    parser.add_argument("--port", type=int, default=8137)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    asyncio.run(serve(args))


if __name__ == "__main__":
    main()
