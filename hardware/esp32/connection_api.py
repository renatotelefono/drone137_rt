"""Local pairing and connection routes. No mission launch or motor API here."""
import asyncio
import ipaddress

from aiohttp import ClientError, web

from hardware.esp32.connection import AircraftConnection
from hardware.esp32.device_store import DeviceStore
from hardware.esp32.link_protocol import ProtocolError


def install(app, path, components):
    store = DeviceStore(path)
    connections = {}
    operation_locks = {}
    pairing_lock = asyncio.Lock()
    pending_connections = set()

    def local(request):
        try:
            if not ipaddress.ip_address(request.remote or '').is_loopback:
                raise ValueError()
        except ValueError:
            raise web.HTTPForbidden(text='Aircraft pairing requires a local connection')
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
            return response_error(str(exc), getattr(exc, 'status', 409))
        except (TimeoutError, OSError, ClientError):
            return response_error('Aircraft is unreachable; check Wi-Fi and pairing', 503)

    def response_error(message, status):
        return web.json_response({'error': message[:200]}, status=status,
                                 headers={'Cache-Control': 'no-store'})

    async def body(request):
        if request.content_length is None or request.content_length > 4096:
            raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=request.content_length or 0)
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value

    async def listing(request):
        return response({'aircraft': [dict(r, **(connections[r['id']].snapshot()
                         if r['id'] in connections else {'connection': 'disconnected', 'mission_ready': False}))
                                      for r in store.list()]})

    async def pairing(request):
        value = await body(request)
        if set(value) != {'profile', 'address', 'name', 'assembly'}:
            raise ValueError('Expected pairing profile, address, name and assembly')
        components.get('configuration', value['assembly'])
        # Validate and verify identity before saving the pairing credential.
        from hardware.esp32.link_client import AircraftLink
        profile = value['profile']
        if not isinstance(profile, dict):
            raise ValueError('Invalid pairing profile')
        link = AircraftLink(value['address'], profile.get('certificate_sha256'),
                            profile.get('credential'), 'drone137-pairing')
        async with pairing_lock:
            try:
                if len(store.list()) >= 32:
                    raise ValueError('The local registry supports up to 32 paired aircraft')
                hello = await link.start()
                if hello.get('device_id') != profile.get('device_id') or hello.get('kind') != profile.get('kind'):
                    raise ProtocolError('Aircraft identity differs from pairing profile', 409)
                record = store.add(**value)
            finally:
                await link.close()
        return response(record)

    async def control(request):
        identity = request.match_info['aircraft']
        operation = request.match_info['operation']
        record = store.get(identity, private=True)
        if await body(request):
            raise ValueError('This connection action takes no parameters')
        # Emergency is never queued behind connect/disconnect or model work.
        if operation in ('land', 'disarm'):
            connection = connections.get(identity) or AircraftConnection(record)
            return response(await connection.stop(operation))
        lock = operation_locks.setdefault(identity, asyncio.Lock())
        async with lock:
            if operation == 'connect':
                occupied = pending_connections | {i for i, c in connections.items()
                                                   if c.state in ('connecting', 'connected')}
                if len(occupied) >= 4 and identity not in occupied:
                    raise ProtocolError('Four sensor connections are already active', 409)
                connection = connections.setdefault(identity, AircraftConnection(record))
                pending_connections.add(identity)
                try:
                    return response(await connection.connect())
                finally:
                    pending_connections.discard(identity)
            if operation == 'disconnect':
                if identity in connections:
                    await connections[identity].close()
                return response({'id': identity, 'connection': 'disconnected'})
            if identity in connections and connections[identity].state not in ('disconnected', 'fault'):
                raise ProtocolError('Disconnect the aircraft before forgetting it', 409)
            if identity in connections:
                await connections.pop(identity).close()
            store.remove(identity)
            return response({'removed': identity})

    async def frame(request):
        identity = request.match_info['aircraft']
        if identity not in connections:
            raise ProtocolError('Aircraft is not connected', 409)
        image = connections[identity].latest_frame()
        return web.Response(body=image['jpeg'], content_type='image/jpeg', headers={
            'Cache-Control': 'no-store', 'X-Frame-Id': str(image['sequence']),
            'X-Capture-Time-Us': str(image['capture_time_us'])})

    for method, route, handler in (
        ('GET', '/api/aircraft', listing),
        ('POST', '/api/aircraft/pair', pairing),
        ('POST', '/api/aircraft/{aircraft}/{operation:connect|disconnect|forget|land|disarm}', control),
        ('GET', '/api/aircraft/{aircraft}/frame', frame),
    ):
        async def wrapped(request, handler=handler):
            return await guarded(request, handler)
        app.router.add_route(method, route, wrapped)

    async def cleanup(app):
        await asyncio.gather(*(c.close() for c in connections.values()))
    app.on_cleanup.append(cleanup)
    return store, connections
