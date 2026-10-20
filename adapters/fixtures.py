import asyncio
import json
import math
import time
import uuid
from pathlib import Path

from app.contracts import Frame, Telemetry


class LatestFrameBuffer:
    """A single slot; previous JPEG bytes are released when replaced."""
    def __init__(self):
        self.frame = None

    def put(self, frame):
        self.frame = frame

    def latest(self):
        return self.frame

    def clear(self):
        self.frame = None


class ReplayCamera(LatestFrameBuffer):
    """Explicit prerecorded JPEG replay, with host receipt timestamps."""
    def __init__(self, paths: list[Path], fps=2):
        super().__init__()
        if not paths:
            raise ValueError("replay requires images")
        self.paths, self.interval = paths, 1 / fps
        self.episode, self.task = "", None

    def begin_episode(self, episode):
        self.episode = episode
        self.clear()
        self._publish(0)

    def _publish(self, index):
        data = self.paths[index % len(self.paths)].read_bytes()
        if len(data) > 2_000_000 or not data.startswith(b"\xff\xd8"):
            raise ValueError("replay requires a JPEG below 2 MB")
        self.put(Frame(uuid.uuid4().hex, self.episode, data, time.monotonic(),
                       camera_id="fixture-replay"))

    async def start(self):
        async def produce():
            index = 0
            while True:
                self._publish(index)
                index += 1
                await asyncio.sleep(self.interval)
        self.task = asyncio.create_task(produce())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


class FakeDrone:
    """Kinematic fixture. No real flight dynamics or aircraft connection."""
    def __init__(self, speed=12):
        self.position = (0.0, 0.0, 0.0)
        self.speed, self.velocity = speed, 0.0
        self.healthy, self.in_air = True, False
        self.commands = []
        self.motion = None

    async def connect(self):
        pass

    def telemetry(self):
        return Telemetry(self.position, self.velocity, time.monotonic(),
                         self.healthy, self.in_air)

    async def _move(self, position):
        await self.hold()
        async def animate():
            try:
                while math.dist(self.position, position) > .005:
                    delta = tuple(b-a for a,b in zip(self.position, position))
                    distance = math.dist(self.position, position)
                    fraction = min(1, self.speed * .02 / distance)
                    self.velocity = self.speed
                    self.position = tuple(a+d*fraction for a,d in zip(self.position, delta))
                    await asyncio.sleep(.02)
                self.position = tuple(position)
            finally:
                self.velocity = 0
        self.motion = asyncio.create_task(animate())

    async def takeoff(self, height):
        self.commands.append(("takeoff", height))
        self.in_air = True
        await self._move((0, 0, height))

    async def goto(self, position, yaw=0):
        self.commands.append(("goto", tuple(position)))
        await self._move(position)

    async def hold(self):
        if self.motion:
            self.motion.cancel()
            await asyncio.gather(self.motion, return_exceptions=True)
            self.motion = None
        self.velocity = 0

    async def land(self):
        self.commands.append(("land",))
        await self._move((*self.position[:2], 0))
        await self.motion
        self.in_air = False

    async def close(self):
        await self.hold()


class ScriptedPolicy:
    """A route fixture; intentionally makes no visual classification claim."""
    identity = "scripted-fixture"

    async def infer(self, observation):
        action = "recheck" if observation.allowed_views else "continue"
        return json.dumps({
            "observation": "uncertain", "action": action,
            "target_view": observation.allowed_views[0] if action == "recheck" else None,
            "reason": "Deterministic integration policy; no image inference performed.",
        })

    async def close(self):
        pass
