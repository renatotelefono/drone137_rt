import html
import json
import re
from aiohttp import web
from adapters.rapier_drone import ROOT
from app import mission_wizard


def install(app, runtime, available=lambda: None, places=None, launcher=None):
    runtime.available = available
    templates = mission_wizard.load_templates()
    launcher = launcher or mission_wizard.ExplorationLauncher(ROOT)
    memory = None
    if places is not None:
        from app.place_memory import PlaceMemory
        memory = PlaceMemory(places)
    async def dashboard(request):
        return web.FileResponse(ROOT/'app/ui/mission-console.html')

    async def status(request):
        return web.json_response(runtime.snapshot(), headers={'Cache-Control': 'no-store'})

    async def control(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        op = request.match_info['operation']
        if op == 'plan':
            result = await runtime.plan(body)
        elif op == 'launch':
            result = await runtime.launch(body.get('draft_id'))
        else:
            result = await runtime.stop(return_home=op == 'return')
        return web.json_response(result)

    async def frame(request):
        if not runtime.run:
            raise web.HTTPNotFound()
        path = runtime.directory/runtime.run['id']/'live.jpg'
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'no-store'})

    async def history(request):
        entries = []
        for folder in sorted(runtime.directory.iterdir(), reverse=True):
            path = folder/'summary.json'
            if not path.is_file():
                continue
            record = json.loads(path.read_text())
            entry = {k: record.get(k) for k in ('id', 'state', 'started_at', 'outcome', 'report', 'error')}
            entry['template'] = (record.get('plan') or {}).get('template')
            entries.append(entry)
        return web.json_response(sorted(entries, key=lambda r: r['started_at'], reverse=True)[:100])

    async def report(request):
        episode, name = request.match_info['episode'], request.match_info['name']
        if not re.fullmatch('[a-f0-9]{32}', episode) or not re.fullmatch(r'report.html|summary.json|onboard.webm|(?:identity-)?frame-[0-9]+\.jpg', name):
            raise web.HTTPNotFound()
        folder = runtime.directory/episode
        if name != 'report.html':
            path = folder/name
            if not path.is_file():
                raise web.HTTPNotFound()
            return web.FileResponse(path)
        path = folder/'summary.json'
        if not path.is_file():
            raise web.HTTPNotFound()
        record = json.loads(path.read_text())
        cards = ''.join('<article><img src="'+s['image']+'"><p>'+html.escape(s['visual']['evidence'])+'</p><pre>'+html.escape(json.dumps(s.get('identity'), indent=2))+'</pre></article>' for s in record['steps'])
        return web.Response(text='<!doctype html><meta charset=utf-8><title>Drone137 mission evidence</title><style>body{background:#101c22;color:#deebe9;font:16px system-ui;max-width:1100px;margin:35px auto;padding:20px}img,video{max-width:100%}article{display:inline-block;vertical-align:top;width:46%;padding:1%}pre{white-space:pre-wrap}a{color:#a6d9ee}</style><h1>Drone137 mission evidence</h1><p>'+html.escape(record['state']+' / '+record['outcome'])+'</p><p>'+html.escape(record.get('error') or '')+'</p><p>Rapier microquad, local vision, service-owned camera. Ideal external pose and known floor plan. Hardware unqualified.</p><a href="summary.json">Full evidence record</a><video controls src="onboard.webm"></video>'+cards, content_type='text/html')

    async def wizard_templates(request):
        return web.json_response(templates)

    async def wizard_suggestions(request):
        snapshot = runtime.snapshot()
        model = snapshot.get('model') or {}
        places = mission_wizard.place_summary(memory) if memory else []
        result = mission_wizard.suggest(templates, places, model_ready=bool(model.get('ready')),
                                        mission_busy=bool(snapshot.get('busy')), exploration_active=launcher.active,
                                        brief=request.query.get('brief'))
        result['places'] = places[:12]
        result['exploration'] = launcher.status()
        return web.json_response(result, headers={'Cache-Control': 'no-store'})

    async def wizard_compose(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        return web.json_response(mission_wizard.compose(templates, body.get('template'), body.get('fields')))

    async def wizard_explore(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        runtime.available()
        if runtime.busy:
            raise RuntimeError('Finish the active mission first')
        plan = mission_wizard.compose(templates, 'map', body)
        return web.json_response(await launcher.start(plan['place'], plan['seed'], plan['name']))

    async def wizard_explore_status(request):
        status = launcher.status()
        if status is None:
            raise web.HTTPNotFound()
        return web.json_response(status, headers={'Cache-Control': 'no-store'})

    app.router.add_get('/api/wizard/templates', wizard_templates)
    app.router.add_get('/api/wizard/suggestions', wizard_suggestions)
    app.router.add_post('/api/wizard/compose', wizard_compose)
    app.router.add_post('/api/wizard/explore', wizard_explore)
    app.router.add_get('/api/wizard/explore/status', wizard_explore_status)
    app.router.add_get('/missions', dashboard)
    app.router.add_get('/api/mission/status', status)
    app.router.add_post('/api/mission/{operation:plan|launch|stop|return}', control)
    app.router.add_get('/api/mission/frame', frame)
    app.router.add_get('/api/mission/runs', history)
    app.router.add_get('/api/mission/runs/{episode}/{name}', report)

    async def cleanup(app):
        await launcher.close()
        await runtime.close()
    app.on_cleanup.append(cleanup)
    return launcher
