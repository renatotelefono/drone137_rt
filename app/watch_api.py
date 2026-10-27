"""Perched-watch routes: start and stop a watch on a connected aircraft, read events, acknowledge, fetch evidence."""
import asyncio
import re

from aiohttp import web

from app.watch_events import DATA, EventStore, PerchedWatch


def install(app, connections, *, model=None, store=None, folder=None):
    store = store or EventStore()
    folder = folder or DATA/'watch'
    watches = {}
    model_lock = asyncio.Lock()   # one local model, one question at a time; watches queue on it

    def frames_for(identity):
        def frames():
            connection = connections.get(identity)
            if connection is None or connection.state != 'connected':
                return None
            try:
                image = connection.latest_frame()
            except Exception:
                return None
            return image['jpeg'], image['sequence'], image['capture_time_us']/1e6
        return frames

    async def status(request):
        return web.json_response({'watches': [w.status() for w in watches.values()], 'alerts': store.alerts()}, headers={'Cache-Control': 'no-store'})

    async def start(request):
        identity = request.match_info['aircraft']
        connection = connections.get(identity)
        if connection is None or connection.state != 'connected':
            raise RuntimeError('Connect the aircraft first')
        watch = watches.get(identity)
        if watch and watch.state == 'watching':
            raise RuntimeError('Already watching this aircraft')
        watch = watches[identity] = PerchedWatch(identity, frames_for(identity), store, folder/identity, model, model_lock=model_lock)
        await watch.start()
        return web.json_response(watch.status())

    async def stop(request):
        identity = request.match_info['aircraft']
        watch = watches.get(identity)
        if watch is None:
            raise RuntimeError('No watch on this aircraft')
        await watch.stop()
        return web.json_response(watch.status())

    async def events(request):
        try:
            since = float(request.query.get('since', 0)); limit = int(request.query.get('limit', 50))
        except ValueError:
            raise ValueError('since and limit must be numbers')
        return web.json_response(store.list(since, max(1, min(200, limit))), headers={'Cache-Control': 'no-store'})

    async def acknowledge(request):
        return web.json_response(store.acknowledge(request.match_info['event']))

    async def evidence(request):
        identity, name = request.match_info['event'], request.match_info['name']
        if not re.fullmatch('[a-f0-9]{32}', identity):
            raise web.HTTPNotFound()
        event = store.get(identity)
        path = folder/event['aircraft']/identity/name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'no-store'})

    app.router.add_get('/api/watch', status)
    app.router.add_post('/api/watch/{aircraft}/start', start)
    app.router.add_post('/api/watch/{aircraft}/stop', stop)
    app.router.add_get('/api/watch/events', events)
    app.router.add_post('/api/watch/events/{event}/ack', acknowledge)
    app.router.add_get('/api/watch/events/{event}/{name:before.jpg|after.jpg|composite.jpg}', evidence)

    async def cleanup(app):
        for watch in watches.values():
            await watch.stop()
    app.on_cleanup.append(cleanup)
    return watches, store
