"""A renderer owned by the service, not by the operator's dashboard tab."""
import asyncio
import json
from aiohttp import web
from adapters.rapier_drone import ROOT


class MissionCamera:
    async def call(self, **body):
        self.process.stdin.write((json.dumps(body)+'\n').encode())
        await self.process.stdin.drain()
        raw = await asyncio.wait_for(self.process.stdout.readline(), 45)
        if not raw:
            raise RuntimeError('Camera renderer exited')
        result = json.loads(raw)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    async def open(self, vehicle, folder):
        self.folder, self.sequence = folder, 0
        app = web.Application(client_max_size=1024*1024)
        async def state(request):
            return web.json_response(vehicle.snapshot())
        async def scene(request):
            return web.json_response(vehicle.scene)
        async def index(request):
            return web.FileResponse(ROOT/'app/ui/flight-lab.html')
        async def video(request):
            if request.query.get('sequence') != str(self.sequence):
                raise web.HTTPConflict()
            data = await request.read()
            path = folder/'onboard.webm'
            if path.exists() and path.stat().st_size+len(data) > 100*1024**2:
                raise web.HTTPInsufficientStorage()
            with path.open('ab') as f:
                f.write(data)
            self.sequence += 1
            return web.json_response({'saved': True})
        app.router.add_get('/', index)
        app.router.add_get('/scene.json', scene)
        app.router.add_get('/state', state)
        app.router.add_post('/video', video)
        app.router.add_static('/assets', ROOT/'app/ui')
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.log = (folder/'camera.log').open('wb')
        self.process = await asyncio.create_subprocess_exec('node', 'scripts/flight-camera.cjs',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.log, cwd=ROOT)
        await self.call(op='open', folder=str(folder), url=f'http://127.0.0.1:{port}', live=True)

    async def close(self):
        try:
            if getattr(self, 'process', None) and self.process.returncode is None:
                self.stats = await self.call(op='close')
                self.process.stdin.close()
                await asyncio.wait_for(self.process.wait(), 10)
                if self.stats.get('video', {}).get('error') or self.stats.get('stats', {}).get('errors'):
                    raise RuntimeError('Camera/video finalization failed')
        finally:
            try:
                if getattr(self, 'process', None) and self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
            finally:
                try:
                    if getattr(self, 'runner', None):
                        await self.runner.cleanup()
                        self.runner = None
                finally:
                    if hasattr(self, 'log'):
                        self.log.close()
