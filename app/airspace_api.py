"""Airspace routes: what is in the air, how far apart, who is holding; the mission runtime's flight reports into it."""
import asyncio
import time

from aiohttp import web

from app.airspace import Airspace

MISSION_AIRCRAFT = 'mission-aircraft'


def install(app, runtime=None, airspace=None, *, aircraft=MISSION_AIRCRAFT, period_s=.2):
    airspace = airspace or Airspace()

    async def status(request):
        return web.json_response(airspace.status(time.monotonic()), headers={'Cache-Control': 'no-store'})

    app.router.add_get('/api/airspace', status)

    async def feed():
        """The runtime's active flight, reported at 5 Hz; declared landed when the mission is over."""
        while True:
            try:
                pose = runtime.current_pose() if runtime is not None else None
                if pose is not None and runtime.busy:
                    airspace.report(aircraft, (pose['x'], pose['y'], pose['z']), pose['yaw'], time.monotonic(), state='flying' if pose['z'] > .1 else 'ground')
                elif airspace.flights.get(aircraft, {}).get('state') == 'flying':
                    airspace.landed(aircraft, time.monotonic())
            except Exception:
                pass
            await asyncio.sleep(period_s)

    async def lifecycle(app):
        task = asyncio.create_task(feed())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    app.cleanup_ctx.append(lifecycle)
    return airspace
