import re
import json
from aiohttp import web
from app.server import ROOT, local_only
from app.recon import ACTIVE
from scripts.tools import DATA
from app.reports import list_runs, render_report
from app.fleet import Fleet, DRONES


def make_recon_app(recon):
    app = web.Application(middlewares=[local_only], client_max_size=1024*1024+4096)
    from app.component_api import install
    from app.components import Components
    components = Components(recon.runs.parent/'components.sqlite3')
    install(app, components)
    from hardware.esp32.connection_api import install as install_aircraft
    aircraft = install_aircraft(app, recon.runs.parent/'aircraft.sqlite3', components)
    from app.place_api import install as install_places
    install_places(app, recon.runs.parent/'places.sqlite3', recon.manager)
    fleet = Fleet(recon)
    from app.mission_runtime import MissionRuntime
    from app.mission_api import install as install_missions
    missions = MissionRuntime(recon.manager, recon.runs.parent/'mission-runs')
    # One admission lock for both mission implementations and the earlier lab.
    missions.lock = fleet.lock
    old_available = fleet.available
    def legacy_available():
        if missions.busy:
            raise RuntimeError('Finish the Rapier mission before using the earlier fleet')
        old_available()
    fleet.available = legacy_available
    install_missions(app, missions, old_available)
    from hardware.esp32.manual_api import install as install_manual
    install_manual(app, aircraft[1], mission_busy=lambda: missions.busy)
    from app.preflight_api import install as install_preflight
    install_preflight(app)
    from app.watch_api import install as install_watch
    install_watch(app, aircraft[1], model=recon.manager)
    from app.dock_api import install as install_docks
    install_docks(app, missions.docks, clients=missions.dock_clients, runtime=missions, current_pose=missions.current_pose)

    async def startup(app):
        import asyncio
        fleet.task = asyncio.create_task(fleet.run())

    async def cleanup(app):
        await fleet.close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)

    def aircraft(request):
        drone_id = request.match_info.get('drone')
        if drone_id is None:
            return recon
        if drone_id not in DRONES:
            raise web.HTTPNotFound()
        return fleet.drones[drone_id]

    async def index(request):
        return web.FileResponse(ROOT/'app/ui/recon.html')

    async def dashboard(request):
        return web.FileResponse(ROOT/'app/ui/mission-console.html')

    async def legacy_dashboard(request):
        return web.FileResponse(ROOT/'app/ui/mission-control.html')

    async def hardware_page(request):return web.FileResponse(ROOT/'app/ui/airframes.html')

    async def hardware(request):
        if request.method=='GET':
            return web.json_response({'profiles':fleet.airframes.list(),'assignments':{d:fleet.airframes.assigned(d) for d in DRONES}},headers={'Cache-Control':'no-store'})
        body=await request.json()
        if not isinstance(body,dict):raise ValueError('Expected a profile operation')
        if request.match_info['operation']=='save':
            return web.json_response(fleet.airframes.save(body.get('profile'),body.get('expected_revision')))
        async with fleet.lock:
            fleet.available()
            if body.get('vehicle_id') not in DRONES:raise ValueError('Unknown aircraft')
            value=fleet.airframes.assign(body['vehicle_id'],body.get('reference',''))
            fleet.draft=None
            return web.json_response(value)

    async def status(request):
        value = (fleet.drone_snapshot(request.match_info['drone']) if request.match_info.get('drone') in DRONES
                 else aircraft(request).snapshot())
        return web.json_response(value, headers={'Cache-Control': 'no-store'})

    async def control(request):
        if missions.busy:
            raise RuntimeError('Finish the Rapier mission before using the earlier lab')
        name = request.match_info['operation']
        body = await request.json()
        if missions.busy:
            raise RuntimeError('Finish the Rapier mission before using the earlier lab')
        if fleet.busy and name in ('start', 'room'):
            raise RuntimeError('Finish the fleet mission before using the Recon lab')
        if name == 'start':
            async with fleet.lock:
                if missions.busy:
                    raise RuntimeError('Finish the Rapier mission before using the earlier lab')
                if fleet.busy:
                    raise RuntimeError('Finish the fleet mission before using the Recon lab')
                await recon.start(body.get('policy'), body.get('client'), body.get('mission', 'explore'), body.get('compare', True))
        elif name == 'room':
            recon.configure(body.get('seed'), body.get('scenario', 'room'), body.get('variant', 'baseline'), body.get('condition', 'nominal'))
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
        stamp = request.query.get('video_time_s')
        aircraft(request).camera(request.query.get('episode'), request.query.get('client'), request.query.get('ticket'), await request.read(),
                     float(stamp) if stamp is not None else None)
        return web.json_response({'accepted': True})

    async def video(request):
        await aircraft(request).video(request.query.get('episode'), request.query.get('client'),
            int(request.query.get('sequence', '-1')), request.query.get('mime'), await request.read())
        return web.json_response({'accepted': True})

    async def finalize(request):
        body = await request.json()
        drone = aircraft(request)
        await drone.finalize_video(body.get('episode'), body.get('client'))
        return web.json_response({'complete': drone.video_complete})

    async def model(request):
        if recon.state in ACTIVE | {'paused'} or fleet.busy or missions.busy:
            raise RuntimeError('End the virtual mission before changing or testing the model')
        operation = request.match_info['operation']
        if operation == 'cancel':
            recon.manager.store.cancel.set()
        else:
            recon.manager.submit(operation)
        return web.json_response(recon.manager.status())

    async def fleet_status(request):
        return web.json_response(fleet.snapshot(), headers={'Cache-Control': 'no-store'})

    async def fleet_control(request):
        if missions.busy:
            raise RuntimeError('Finish the Rapier mission before using the earlier fleet')
        body = await request.json()
        if missions.busy:
            raise RuntimeError('Finish the Rapier mission before using the earlier fleet')
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        operation = request.match_info['operation']
        if operation == 'plan':
            return web.json_response(await fleet.plan(body))
        if operation == 'launch':
            return web.json_response(await fleet.launch(body.get('draft_id'), body.get('session')))
        if operation == 'site':
            fleet.configure(body.get('seed'), body.get('scenario', 'realism'), body.get('variant', 'baseline'), body.get('condition', 'nominal'))
        else:
            await fleet.stop(return_home=operation == 'return')
        return web.json_response(fleet.snapshot())

    async def ready(request):
        aircraft(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a camera heartbeat')
        fleet.heartbeat(request.match_info['drone'], body)
        return web.json_response({'accepted': True})

    async def camera_stop(request):
        # An encoder failure invalidates the entire shared-airspace dispatch.
        drone = aircraft(request)
        body = await request.json()
        if body.get('client') != drone.client or body.get('episode') != drone.episode:
            raise ValueError('Stop belongs to another camera mission')
        await fleet.stop()
        return web.json_response(fleet.snapshot())

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
        if name == 'report.html':
            summary = recon.runs/episode/'summary.json'
            if not summary.is_file() or summary.stat().st_size > 512_000:
                raise web.HTTPNotFound()
            value = json.loads(summary.read_text())
            if value.get('mode') == 'virtual-fleet-mission':
                from app.reports import render_fleet_report
                return web.Response(text=render_fleet_report(episode, value), content_type='text/html')
            return web.Response(text=render_report(episode, value), content_type='text/html')
        if not re.fullmatch(r'summary.json|world.json|events.jsonl|onboard.webm|onboard.mp4|[a-f0-9]{32}\.jpg', name):
            raise web.HTTPNotFound()
        path = recon.runs/episode/name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def history(request):
        fields = ('episode', 'state', 'scenario', 'variant', 'seed', 'condition', 'policy', 'mission',
                  'distance_m', 'observed_fraction', 'video', 'report_page', 'unreached', 'task_context')
        return web.json_response([{k: run.get(k) for k in fields} for run in list_runs(recon.runs)],
                                 headers={'Cache-Control': 'no-store'})

    app.router.add_get('/', index)
    app.router.add_get('/control', dashboard)
    app.router.add_get('/control-legacy', legacy_dashboard)
    app.router.add_get('/camera-worker', index)
    app.router.add_static('/assets/', ROOT/'app/ui', show_index=False)
    app.router.add_get('/api/status', status)
    app.router.add_get('/api/runs', history)
    app.router.add_get('/api/fleet/status', fleet_status)
    app.router.add_get('/airframes',hardware_page)
    app.router.add_get('/api/airframes',hardware)
    app.router.add_post(r'/api/airframes/{operation:save|assign}',hardware)
    app.router.add_post(r'/api/fleet/{operation:plan|launch|site|stop|return}', fleet_control)
    app.router.add_get('/api/fleet/drones/{drone}/status', status)
    app.router.add_post('/api/fleet/drones/{drone}/ready', ready)
    app.router.add_post('/api/fleet/drones/{drone}/camera', frame)
    app.router.add_post('/api/fleet/drones/{drone}/video', video)
    app.router.add_post('/api/fleet/drones/{drone}/video-finalize', finalize)
    app.router.add_post('/api/fleet/drones/{drone}/land', camera_stop)
    app.router.add_post('/api/camera', frame)
    app.router.add_post('/api/video', video)
    app.router.add_post('/api/video-finalize', finalize)
    app.router.add_post(r'/api/{operation:start|room|pause|land|freeze-sensors}', control)
    app.router.add_post(r'/api/model/{operation:download|verify|install-runtime|start|stop|check|cancel|reset-partials}', model)
    app.router.add_get(r'/api/log/{name:llama|runtime-build}', log)
    app.router.add_get('/reports/{episode}/{name}', report)
    return app
