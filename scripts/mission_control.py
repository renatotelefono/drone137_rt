"""Run mission control against an already installed, local llama-server."""
import argparse
import asyncio
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
    install(app, runtime, places=ROOT/'.local/data/places.sqlite3')
    from app.component_api import install as install_components
    install_components(app, runtime.components)
    from hardware.esp32.connection_api import install as install_aircraft
    install_aircraft(app, ROOT/'.local/data/aircraft.sqlite3', runtime.components)
    from app.place_api import install as install_places
    install_places(app, ROOT/'.local/data/places.sqlite3', model)
    async def dashboard(request):
        return web.FileResponse(ROOT/'app/ui/mission-console.html')
    app.router.add_get('/control', dashboard)
    app.router.add_static('/assets', ROOT/'app/ui')
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '127.0.0.1', args.port).start()
    print(f'Drone137 mission control: http://127.0.0.1:{args.port}/control', flush=True)
    done = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, done.set)
    try:
        await done.wait()
    finally:
        await runner.cleanup()
        await model.backend.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8153)
    asyncio.run(serve(parser.parse_args()))
