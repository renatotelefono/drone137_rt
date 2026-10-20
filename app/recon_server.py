import re
from aiohttp import web
from app.server import ROOT, local_only
from app.recon import ACTIVE
from scripts.tools import DATA


def make_recon_app(recon):
    app = web.Application(middlewares=[local_only], client_max_size=1024*1024+4096)

    async def index(request):
        return web.FileResponse(ROOT/'app/ui/recon.html')

    async def status(request):
        return web.json_response(recon.snapshot(), headers={'Cache-Control': 'no-store'})

    async def control(request):
        name = request.match_info['operation']
        body = await request.json()
        if name == 'start':
            await recon.start(body.get('policy'), body.get('client'))
        elif name == 'room':
            recon.configure(body.get('seed'))
        elif name == 'pause':
            await recon.pause()
        elif name == 'land':
            await recon.land()
        elif name == 'freeze-sensors':
            if recon.state not in ACTIVE:
                raise RuntimeError('Start a virtual mission first')
            recon.sensor_frozen = True
        return web.json_response(recon.snapshot())

    async def frame(request):
        recon.camera(request.query.get('episode'), request.query.get('client'), request.query.get('ticket'), await request.read())
        return web.json_response({'accepted': True})

    async def video(request):
        await recon.video(request.query.get('episode'), request.query.get('client'),
            int(request.query.get('sequence', '-1')), request.query.get('mime'), await request.read())
        return web.json_response({'accepted': True})

    async def finalize(request):
        body = await request.json()
        await recon.finalize_video(body.get('episode'), body.get('client'))
        return web.json_response({'complete': recon.video_complete})

    async def model(request):
        if recon.state in ACTIVE | {'paused'}:
            raise RuntimeError('End the virtual mission before changing or testing the model')
        operation = request.match_info['operation']
        if operation == 'cancel':
            recon.manager.store.cancel.set()
        else:
            recon.manager.submit(operation)
        return web.json_response(recon.manager.status())

    async def log(request):
        name = request.match_info['name']
        path = DATA/'logs'/f'{name}.log'
        if not path.is_file():
            return web.Response(text='No log yet.')
        with path.open('rb') as source:
            source.seek(max(0, path.stat().st_size-16000))
            content = source.read(16000)
        return web.Response(body=content, content_type='text/plain')

    async def report(request):
        episode, name = request.match_info['episode'], request.match_info['name']
        if not re.fullmatch('[a-f0-9]{32}', episode):
            raise web.HTTPNotFound()
        if not re.fullmatch(r'summary.json|world.json|events.jsonl|onboard.webm|onboard.mp4|[a-f0-9]{32}\.jpg', name):
            raise web.HTTPNotFound()
        path = recon.runs/episode/name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    app.router.add_get('/', index)
    app.router.add_static('/assets/', ROOT/'app/ui', show_index=False)
    app.router.add_get('/api/status', status)
    app.router.add_post('/api/camera', frame)
    app.router.add_post('/api/video', video)
    app.router.add_post('/api/video-finalize', finalize)
    app.router.add_post(r'/api/{operation:start|room|pause|land|freeze-sensors}', control)
    app.router.add_post(r'/api/model/{operation:download|verify|install-runtime|start|stop|check|cancel|reset-partials}', model)
    app.router.add_get(r'/api/log/{name:llama|runtime-build}', log)
    app.router.add_get('/reports/{episode}/{name}', report)
    return app
