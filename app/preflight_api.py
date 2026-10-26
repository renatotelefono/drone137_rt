"""Pre-flight memory routes: the estimate is instant, the measured preflight takes seconds."""
import asyncio

from aiohttp import web

from app import memory_budget


def install(app):
    lock = asyncio.Lock()

    async def estimate(request):
        profile = request.query.get('profile', 'mission-simulation')
        report = memory_budget.assess(profile)
        return web.json_response({**memory_budget.summary({**report, 'measured': [], 'unknown': report['unknown']}), 'components_detail': report['components'],
                                  'verdict': report['verdict']}, headers={'Cache-Control': 'no-store'}, dumps=lambda v: __import__('json').dumps(v, default=float))

    async def measure(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        seconds = body.get('seconds', 10)
        if type(seconds) not in (int, float) or not 1 <= seconds <= 30:
            raise ValueError('seconds must be between 1 and 30')
        if lock.locked():
            raise RuntimeError('A measured preflight is already running')
        async with lock:
            report = await memory_budget.measure(body.get('profile', 'mission-simulation'), seconds, verifier=body.get('verifier', True) is not False)
        return web.json_response({**memory_budget.summary(report), 'host_before': report['host_before'], 'host_after': report['host_after'], 'verdict': report['verdict']},
                                 headers={'Cache-Control': 'no-store'}, dumps=lambda v: __import__('json').dumps(v, default=float))

    app.router.add_get('/api/preflight/memory', estimate)
    app.router.add_post('/api/preflight/memory', measure)
