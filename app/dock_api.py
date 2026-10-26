"""Dock endpoints: registry, controller status and mode, and ending the active mission on a dock."""
from aiohttp import web

from app.docks import MODES, public


def install(app, docks, *, clients=None, runtime=None, current_pose=None):
    """clients: {dock id: object with status()/set_mode()}; current_pose: () -> {x,y,z,yaw} of the aircraft, for registration."""
    clients = clients if clients is not None else {}

    async def listing(request):
        return web.json_response([{**entry, 'dock': public(entry['dock'])} for entry in docks.list()], headers={'Cache-Control': 'no-store'})

    async def register(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        pose = body.get('pose')
        if pose is None:
            if current_pose is None:
                raise ValueError('No aircraft pose available; give the dock pose explicitly')
            pose = current_pose()
            if pose is None:
                raise ValueError('The aircraft has no pose estimate yet')
        entry = docks.register(body.get('id'), body.get('name', 'Dock'), pose, place_id=body.get('place_id'),
                               index=body.get('index'), link=body.get('link'))
        return web.json_response({**entry, 'dock': public(entry['dock'])})

    def client_for(request):
        identity = request.match_info['dock']
        entry = docks.get(identity)
        client = clients.get(identity)
        if client is None:
            raise web.HTTPNotFound(text='Dock has no controller connection in this process')
        return entry, client

    async def status(request):
        entry, client = client_for(request)
        return web.json_response({'dock': public(entry['dock']), 'revision': entry['revision'], 'status': await client.status(),
                                  'landings': docks.landings(entry['dock']['id'], 10)}, headers={'Cache-Control': 'no-store'})

    async def mode(request):
        body = await request.json()
        if not isinstance(body, dict) or body.get('mode') not in MODES:
            raise ValueError('Mode must be off, charge or storage')
        entry, client = client_for(request)
        return web.json_response({'dock': entry['dock']['id'], 'status': await client.set_mode(body['mode'])})

    async def dock_mission(request):
        if runtime is None:
            raise web.HTTPNotFound(text='No mission runtime in this process')
        return web.json_response(await runtime.stop(dock=True))

    app.router.add_get('/api/docks', listing)
    app.router.add_post('/api/docks/register', register)
    app.router.add_get('/api/docks/{dock}/status', status)
    app.router.add_post('/api/docks/{dock}/mode', mode)
    app.router.add_post('/api/mission/dock', dock_mission)
    return clients
