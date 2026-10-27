"""Run mission control against an already installed, local llama-server."""
import argparse
import asyncio

from app.portability import install_stop_handlers
import signal
import time
from aiohttp import web
from adapters.llama import LlamaBackend
from app.server import local_only, ROOT
from app.mission_runtime import MissionRuntime
from app.mission_api import install


class LocalModel:
    def __init__(self):
        self.backend = LlamaBackend(timeout=12)
        self.lock = asyncio.Lock()

    def status(self):
        return {'name': 'Local Qwen 2B + Florence verifier', 'external': True,
                'ready': not self.backend.quarantined, 'state': 'ready' if not self.backend.quarantined else 'restart required', 'busy': self.lock.locked()}

    async def text(self, prompt, schema, timeout=12):
        async with self.lock:
            return await self.backend.text(prompt, schema, time.monotonic()+timeout)

    async def image(self, jpeg, prompt, schema, timeout=12, max_tokens=180):
        async with self.lock:
            return await self.backend.image(jpeg, prompt, schema, time.monotonic()+timeout, max_tokens=max_tokens)


async def serve(args):
    model = LocalModel()
    await model.backend.health()
    runtime = MissionRuntime(model, ROOT/'.local/data/mission-runs')
    app = web.Application(middlewares=[local_only], client_max_size=8192)
    launcher = install(app, runtime, places=ROOT/'.local/data/places.sqlite3')
    from app.component_api import install as install_components
    install_components(app, runtime.components)
    from hardware.esp32.connection_api import install as install_aircraft
    aircraft = install_aircraft(app, ROOT/'.local/data/aircraft.sqlite3', runtime.components)
    from hardware.esp32.manual_api import install as install_manual
    install_manual(app, aircraft[1], mission_busy=lambda: runtime.busy)
    from app.preflight_api import install as install_preflight
    install_preflight(app)
    from app.watch_api import install as install_watch
    install_watch(app, aircraft[1], model=model)
    from app.mission_assistant import Assistant, install as install_assistant
    from app.mission_wizard import load_templates
    from app.place_memory import PlaceMemory
    assistant = Assistant(model, runtime, aircraft, launcher, load_templates())
    assistant.places = PlaceMemory(ROOT/'.local/data/places.sqlite3')
    install_assistant(app, assistant)
    from app.place_api import install as install_places
    install_places(app, ROOT/'.local/data/places.sqlite3', model)
    from app.dock_api import install as install_docks
    install_docks(app, runtime.docks, clients=runtime.dock_clients, runtime=runtime, current_pose=runtime.current_pose)
    from app.airspace_api import install as install_airspace
    install_airspace(app, runtime)
    async def dashboard(request):
        return web.FileResponse(ROOT/'app/ui/mission-console.html')
    app.router.add_get('/control', dashboard)
    app.router.add_static('/assets', ROOT/'app/ui')
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '127.0.0.1', args.port).start()
    print(f'Drone137 mission control: http://127.0.0.1:{args.port}/control', flush=True)
    done = asyncio.Event()
    install_stop_handlers(asyncio.get_running_loop(), done.set)
    try:
        await done.wait()
    finally:
        await runner.cleanup()
        await model.backend.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8153)
    asyncio.run(serve(parser.parse_args()))
