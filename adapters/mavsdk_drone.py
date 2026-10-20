import asyncio
import math
import time

from app.contracts import Telemetry, enu_to_global


class MavsdkDrone:
    """Native external SDK client for loopback SITL only.

    The launcher owns mavsdk_server, bound to udpin://127.0.0.1:14540.
    Physical transports are deliberately absent.
    """
    def __init__(self, port=50051, speed_limit=1):
        from mavsdk import System
        self.system = System(mavsdk_server_address="127.0.0.1", port=port)
        self.speed_limit = speed_limit
        self.home = None
        self.pose = None
        self.healthy = False
        self.health_at = 0
        self.in_air = False
        self.air_at = 0
        self.tasks = []

    async def connect(self):
        async with asyncio.timeout(30):
            await self.system.connect()

        async def position():
            async for value in self.system.telemetry.position_velocity_ned():
                p, v = value.position, value.velocity
                self.pose = ((p.east_m, p.north_m, -p.down_m),
                             math.sqrt(v.north_m_s**2 + v.east_m_s**2 + v.down_m_s**2),
                             time.monotonic())

        async def health():
            async for value in self.system.telemetry.health():
                self.healthy = value.is_global_position_ok and value.is_home_position_ok
                self.health_at = time.monotonic()

        async def home():
            async for value in self.system.telemetry.home():
                # Fix origin for the entire session; do not shift it during movement.
                if self.home is None:
                    self.home = (value.latitude_deg, value.longitude_deg, value.absolute_altitude_m)

        async def airborne():
            async for value in self.system.telemetry.in_air():
                self.in_air = value
                self.air_at = time.monotonic()

        self.tasks = [asyncio.create_task(fn()) for fn in (position, health, home, airborne)]
        async with asyncio.timeout(30):
            while self.home is None or not self.telemetry().healthy:
                for task in self.tasks:
                    if task.done():
                        task.result()
                        raise RuntimeError("telemetry stream ended")
                await asyncio.sleep(.1)
        if math.dist(self.pose[0], (0, 0, 0)) > 1:
            raise RuntimeError("SITL must start on the configured origin/pad")
        await self.system.action.set_maximum_speed(self.speed_limit)

    def telemetry(self):
        if self.pose is None:
            return Telemetry((0, 0, 0), 0, 0, False, self.in_air)
        p, v, received = self.pose
        valid = (self.healthy and time.monotonic() - self.health_at < 3
                 and time.monotonic() - self.air_at < 3
                 and all(not task.done() for task in self.tasks))
        return Telemetry(p, v, received, valid, self.in_air)

    async def takeoff(self, height):
        await self.system.action.set_takeoff_altitude(height)
        await self.system.action.arm()
        await self.system.action.takeoff()

    async def goto(self, position, yaw=0):
        if self.home is None:
            raise RuntimeError("home reference unavailable")
        lat, lon, altitude = enu_to_global(position, self.home)
        await self.system.action.goto_location(lat, lon, altitude, yaw)

    async def hold(self):
        await self.system.action.hold()

    async def land(self):
        await self.system.action.land()
        async with asyncio.timeout(35):
            while self.in_air:
                telemetry = self.telemetry()
                if not telemetry.healthy or time.monotonic() - telemetry.received_monotonic > 2:
                    raise RuntimeError("landing completion unavailable: telemetry lost")
                await asyncio.sleep(.1)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
