"""Manual stick control routes: local, same-origin, refused while a mission flies."""
import asyncio
import ipaddress

from aiohttp import ClientError, web

from hardware.esp32.link_protocol import ProtocolError
from hardware.esp32.manual_control import ManualSession


def install(app, connections, *, mission_busy=lambda: False):
    sessions = {}

    def local(request):
        try:
            if not ipaddress.ip_address(request.remote or '').is_loopback:
                raise ValueError()
        except ValueError:
            raise web.HTTPForbidden(text='Manual control requires a local connection')
        if request.host.split(':')[0] not in ('localhost', '127.0.0.1'):
            raise web.HTTPForbidden(text='Local host required')
        origin = request.headers.get('Origin')
        if origin and origin != 'http://' + request.host:
            raise web.HTTPForbidden(text='Same-origin request required')
        if request.method != 'GET' and request.headers.get('X-Drone137-Control') != 'local':
            raise web.HTTPForbidden(text='Local control header required')

    def response(value):
        return web.json_response(value, headers={'Cache-Control': 'no-store'})

    async def guarded(request, action):
        local(request)
        try:
            return await action(request)
        except (ValueError, RuntimeError) as exc:
            return web.json_response({'error': str(exc)[:200]}, status=getattr(exc, 'status', 409), headers={'Cache-Control': 'no-store'})
        except (TimeoutError, OSError, ClientError):
            return web.json_response({'error': 'Aircraft is unreachable; check Wi-Fi and pairing'}, status=503, headers={'Cache-Control': 'no-store'})

    async def body(request):
        if request.content_length is None or request.content_length > 1024:
            raise web.HTTPRequestEntityTooLarge(max_size=1024, actual_size=request.content_length or 0)
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value

    def session_for(identity, create=False):
        session = sessions.get(identity)
        if session is None or (create and not session.active):
            connection = connections.get(identity)
            if connection is None or connection.state != 'connected':
                raise ProtocolError('Connect the aircraft first', 409)
            if not create:
                raise ProtocolError('Manual control is not active', 409)
            session = sessions[identity] = ManualSession(connection, mission_busy=mission_busy)
        return session

    async def start(request):
        identity = request.match_info['aircraft']
        if await body(request):
            raise ValueError('Start takes no parameters')
        if any(s.active and i != identity for i, s in sessions.items()):
            raise ProtocolError('Another aircraft is under manual control', 409)
        return response(await session_for(identity, create=True).start())

    async def stick(request):
        identity = request.match_info['aircraft']
        return response(session_for(identity).input(await body(request)))

    async def land(request):
        identity = request.match_info['aircraft']
        if await body(request):
            raise ValueError('Land takes no parameters')
        return response(await session_for(identity).land())

    async def status(request):
        identity = request.match_info['aircraft']
        session = sessions.get(identity)
        return response(session.snapshot() if session else {'state': 'idle', 'error': None})

    for method, route, handler in (('POST', '/api/aircraft/{aircraft}/manual/start', start),
                                   ('POST', '/api/aircraft/{aircraft}/manual/input', stick),
                                   ('POST', '/api/aircraft/{aircraft}/manual/land', land),
                                   ('GET', '/api/aircraft/{aircraft}/manual', status)):
        async def wrapped(request, handler=handler):
            return await guarded(request, handler)
        app.router.add_route(method, route, wrapped)

    async def cleanup(app):
        await asyncio.gather(*(s.close() for s in sessions.values()), return_exceptions=True)
    app.on_cleanup.append(cleanup)
    return sessions
