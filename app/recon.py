"""Bounded indoor reconnaissance in a deterministic, ideal-pose kinematic sandbox.

Ground truth is used by the range-sensor/collision simulator and renderer only.
The route planner consumes an observed occupancy grid, never obstacle geometry.
"""
import asyncio
from collections import deque
import json
import math
import random
import time
import uuid

from app.recorder import RunRecorder

WIDTH, DEPTH, CELL = 12.0, 10.0, .5
NX, NY = int(WIDTH/CELL), int(DEPTH/CELL)
RADIUS, MARGIN, SPEED, BRAKE = .18, .12, .6, 1.0
ACTIVE = {"exploring", "observing", "returning"}
SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["continue", "look_left", "look_right", "finish", "hold"]},
    "observation": {"type": "string", "maxLength": 300}},
    "required": ["action", "observation"], "additionalProperties": False}


def decision(raw):
    if not isinstance(raw, str) or len(raw.encode()) > 4096:
        raise ValueError("Oversized or non-text reconnaissance decision")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate reconnaissance decision field")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {"action", "observation"}:
        raise ValueError("Invalid reconnaissance decision fields")
    if value["action"] not in SCHEMA["properties"]["action"]["enum"]:
        raise ValueError("Invalid reconnaissance action")
    if not isinstance(value["observation"], str) or len(value["observation"]) > 300:
        raise ValueError("Invalid reconnaissance observation")
    return value


def world(seed):
    rng = random.Random(seed)
    obstacles = []
    for _ in range(8):
        x, y = rng.uniform(2.8, 10.2), rng.uniform(1.3, 8.6)
        sx, sy = rng.uniform(.6, 1.4), rng.uniform(.6, 1.4)
        if any(abs(x-b['x']) < (sx+b['sx'])/2+.8 and abs(y-b['y']) < (sy+b['sy'])/2+.8 for b in obstacles):
            continue
        obstacles.append(dict(x=x, y=y, sx=sx, sy=sy, height=rng.uniform(1.6, 2.5)))
    return {"seed": seed, "width": WIDTH, "depth": DEPTH, "height": 3, "obstacles": obstacles}


def clearance(scene, x, y):
    value = min(x, y, WIDTH-x, DEPTH-y)
    for b in scene["obstacles"]:
        dx, dy = abs(x-b['x'])-b['sx']/2, abs(y-b['y'])-b['sy']/2
        distance = math.hypot(max(0, dx), max(0, dy)) if dx > 0 or dy > 0 else max(dx, dy)
        value = min(value, distance)
    return value


class Recon:
    def __init__(self, manager, runs):
        self.manager, self.runs = manager, runs
        self.scene = world(137)
        self.task = self.inference = None
        self.recorder = None
        self.state, self.reason, self.episode = "idle", "Ready for a virtual mission", None
        self.pose = [1.25, 1.25, 1.4, 0.0]
        self.grid = [0]*(NX*NY)  # 0 unknown, 1 observed free, 2 observed occupied
        self.route, self.trail, self.observations = [], [], []
        self.ranges, self.speed = [], 0.
        self.ticket, self.frame = None, None
        self.sensor_frozen = False
        self.video_sequence, self.video_type, self.video_complete = 0, None, False
        self.client = None
        self.policy = "qwen"
        self.return_requested = False
        self.visited = set()
        self.minimum_clearance, self.distance, self.stops = 100., 0., 0

    def cell(self, x, y):
        return int(y/CELL)*NX+int(x/CELL)

    def center(self, cell):
        return ((cell % NX+.5)*CELL, (cell//NX+.5)*CELL)

    def configure(self, seed):
        if self.state in ACTIVE or self.state == "paused":
            raise RuntimeError("End this mission before generating another room")
        if type(seed) is not int or not 0 <= seed <= 2**31-1:
            raise ValueError("Seed must be an integer from 0 through 2147483647")
        self.scene = world(seed)
        self.pose = [1.25, 1.25, 1.4, 0.]
        self.grid, self.route, self.trail = [0]*(NX*NY), [], []

    async def start(self, policy, client):
        if self.state in ACTIVE or self.state == "paused":
            raise RuntimeError("A mission is already active")
        if self.task and not self.task.done():
            await self.task
        if policy not in ("qwen", "scripted"):
            raise ValueError("Select local Qwen or explicitly select the scripted demo")
        if not isinstance(client, str) or not 1 <= len(client) <= 80:
            raise ValueError("A browser client identifier is required")
        if policy == "qwen" and (not self.manager.ready or self.manager.status()["busy"]):
            raise RuntimeError("Start the local model and wait for model operations to finish")
        self.configure(self.scene["seed"])
        self.inference = None
        self.policy, self.client, self.episode = policy, client, uuid.uuid4().hex
        self.recorder = RunRecorder(self.runs, self.episode, 1024**3, {
            "mode": "browser-kinematic-recon", "seed": self.scene["seed"], "policy": policy,
            "real_inference": policy == "qwen", "physical_transport": False,
            "real_flight_dynamics": False, "pose": "ideal simulated pose", "altitude_m": 1.4,
            "range_sensors": "ideal simulated planar lidar", "mac_acceptance": "unverified"})
        self.recorder._write(self.recorder.directory/"world.json", json.dumps(self.scene).encode())
        self.observations, self.visited = [], set()
        self.minimum_clearance, self.distance, self.stops = 100., 0., 0
        self.video_sequence, self.video_type, self.video_complete = 0, None, False
        self.sensor_frozen = False
        self.started = self.last_browser = self.sensor_time = time.monotonic()
        self.last_telemetry = self.started
        self.last_observe, self.speed, self.frame = self.started-10, 0., None
        self.return_requested, self.relook = False, False
        self.state, self.reason = "exploring", "Scanning the room"
        self.sense(self.started)
        self.task = asyncio.create_task(self.run())

    def sense(self, now):
        if self.sensor_frozen:
            return
        self.sensor_time = now
        x, y = self.pose[:2]
        self.grid[self.cell(x, y)] = 1
        self.ranges = []
        for i in range(72):
            angle = i*2*math.pi/72
            hit, distance = False, 3.
            for step in range(1, 76):
                distance = step*.04
                px, py = x+math.cos(angle)*distance, y+math.sin(angle)*distance
                if not (0 <= px < WIDTH and 0 <= py < DEPTH):
                    hit = True
                    break
                index = self.cell(px, py)
                if clearance(self.scene, px, py) <= 0:
                    self.grid[index] = 2
                    hit = True
                    break
                # Do not clear previously observed obstacles from a sparse ray.
                if self.grid[index] == 0:
                    self.grid[index] = 1
            self.ranges.append({"angle": angle, "distance": distance, "hit": hit,
                                "valid": True, "time": now, "max_range": 3.})

    def neighbors(self, cell):
        x, y = cell % NX, cell//NX
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            if 0 <= x+dx < NX and 0 <= y+dy < NY:
                yield (y+dy)*NX+x+dx

    def safe_cell(self, cell):
        x, y = cell % NX, cell//NX
        if x < 1 or y < 1 or x >= NX-1 or y >= NY-1 or self.grid[cell] != 1:
            return False
        return all(self.grid[(y+dy)*NX+x+dx] != 2 for dx in (-1,0,1) for dy in (-1,0,1))

    def plan(self, returning=False):
        start = self.cell(*self.pose[:2])
        home = self.cell(1.25, 1.25)
        queue, parent = deque([start]), {start: None}
        candidates = []
        while queue:
            current = queue.popleft()
            if returning and current == home:
                candidates = [current]
                break
            if not returning and current not in self.visited and current != start:
                unknown = sum(self.grid[n] == 0 for n in self.neighbors(current))
                # Prefer a nearby frontier, then an unvisited observed cell.
                candidates.append((unknown, current))
            for neighbor in self.neighbors(current):
                if neighbor not in parent and self.safe_cell(neighbor):
                    parent[neighbor] = current
                    queue.append(neighbor)
        if returning:
            target = home if home in parent else None
        else:
            frontiers = [c for unknown, c in candidates if unknown]
            target = (frontiers or [c for _, c in candidates] or [None])[0]
        if target is None:
            return []
        path = []
        while target != start:
            path.append(target)
            target = parent[target]
        return list(reversed(path))

    def begin_observation(self):
        self.state, self.speed = "observing", 0.
        self.ticket = uuid.uuid4().hex
        self.frame = None
        self.waiting_since = time.monotonic()
        self.reason = "Waiting for a fresh onboard camera image"

    def camera(self, episode, client, ticket, jpeg):
        if episode != self.episode or client != self.client or self.state not in ACTIVE | {"paused"}:
            raise ValueError("Camera belongs to another or completed mission")
        if len(jpeg) > 200_000 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            raise ValueError("Expected a bounded JPEG camera frame")
        self.last_browser = time.monotonic()
        if self.state == "observing" and ticket == self.ticket and self.frame is None:
            self.frame = (jpeg, time.monotonic(), list(self.pose))

    async def inspect(self):
        jpeg, captured, pose = self.frame
        ticket = self.ticket
        self.recorder._write(self.recorder.directory/f"{ticket}.jpg", jpeg)
        started = time.monotonic()
        if self.policy == "qwen":
            raw = await self.manager.image(jpeg,
                "Survey this indoor camera image. Briefly describe visible objects or obstructions. "
                "Choose continue to explore, look_left or look_right for one extra view, hold if unsafe, "
                "or finish to return home. Do not invent unseen objects. Return only the required JSON.", SCHEMA)
            result = decision(raw)
        else:
            result = {"action": "continue", "observation": "Scripted demo: no model perception performed."}
        self.recorder.record("observation", image=f"{ticket}.jpg", pose=pose, captured_monotonic=captured,
                             latency_s=time.monotonic()-started, **result)
        self.observations.append({**result, "image": f"{ticket}.jpg", "pose": pose})
        self.ticket, self.frame = None, None
        self.last_observe = time.monotonic()
        if result['action'] == 'hold':
            await self.finish("paused", "Model requested a hold; end mission before restarting")
        elif result['action'] in ('look_left', 'look_right') and not self.relook:
            self.pose[3] += math.pi/2 * (1 if result['action'] == 'look_left' else -1)
            self.relook = True
            self.begin_observation()
        else:
            self.relook = False
            self.return_requested |= result['action'] == 'finish' or len(self.observations) >= 12
            self.state = 'returning' if self.return_requested else 'exploring'
            self.reason = 'Returning through the observed map' if self.return_requested else 'Exploring observed free space'
            self.route = []

    def move(self, dt, now):
        if now-self.sensor_time > .35:
            raise RuntimeError("Range sensors stale: motion stopped")
        if not self.route:
            self.route = self.plan(self.return_requested)
            if not self.route:
                return False
        tx, ty = self.center(self.route[0])
        dx, dy = tx-self.pose[0], ty-self.pose[1]
        distance = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)
        needed = RADIUS+MARGIN+self.speed*.2+self.speed*self.speed/(2*BRAKE)
        forward = [r for r in self.ranges if abs(math.atan2(math.sin(r['angle']-angle), math.cos(r['angle']-angle))) < .3]
        if not forward or any(not r['valid'] or now-r['time'] > .35 for r in forward):
            raise RuntimeError("Forward range unavailable: motion stopped")
        if min(r['distance'] for r in forward) <= needed:
            self.speed = 0.
            self.stops += 1
            self.visited.add(self.route[0])
            self.route = []
            if self.stops > 20:
                raise RuntimeError("Too many obstacle stops; mission ended")
            return True
        self.speed = min(SPEED, self.speed+BRAKE*dt, math.sqrt(max(0, 2*BRAKE*distance)))
        travel = min(distance, self.speed*dt)
        x, y = self.pose[0]+math.cos(angle)*travel, self.pose[1]+math.sin(angle)*travel
        gap = clearance(self.scene, x, y)-RADIUS
        self.minimum_clearance = min(self.minimum_clearance, gap)
        if gap < MARGIN:
            raise RuntimeError("Simulator collision guard intervened; mission failed")
        self.pose[:2], self.pose[3] = [x, y], angle
        self.distance += travel
        self.visited.add(self.cell(x, y))
        if distance <= travel+.001:
            self.route.pop(0)
        if not self.trail or math.dist(self.trail[-1], self.pose[:2]) >= .2:
            self.trail.append(list(self.pose[:2]))
        return True

    async def run(self):
        previous = time.monotonic()
        try:
            while self.state in ACTIVE:
                now = time.monotonic()
                dt, previous = min(.15, now-previous), now
                if now-self.last_browser > 2:
                    raise RuntimeError("Camera/browser connection lost: mission stopped")
                if now-self.started > 180:
                    raise RuntimeError("180 second mission deadline reached")
                self.sense(now)
                if now-self.last_telemetry >= 1:
                    self.recorder.record("telemetry", elapsed_s=now-self.started, pose=list(self.pose), speed=self.speed, state=self.state)
                    self.last_telemetry = now
                if now-self.sensor_time > .35:
                    raise RuntimeError("Range sensors stale: motion stopped")
                if self.state == "observing":
                    if self.inference and self.inference.done():
                        await self.inference
                        self.inference = None
                    elif not self.inference and self.frame:
                        self.reason = "Inspecting image with local Qwen" if self.policy == "qwen" else "Recording scripted observation"
                        self.inference = asyncio.create_task(self.inspect())
                    elif not self.inference and now-self.waiting_since > 2:
                        raise RuntimeError("Fresh observation camera frame unavailable")
                elif not self.return_requested and now-self.last_observe >= 5:
                    self.begin_observation()
                elif self.return_requested and math.dist(self.pose[:2], [1.25,1.25]) < .1:
                    await self.finish("complete", "Returned home; reconnaissance complete")
                elif not self.move(dt, now):
                    if self.return_requested:
                        raise RuntimeError("No observed safe return route")
                    self.return_requested, self.state = True, "returning"
                await asyncio.sleep(.1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.finish("failed", str(exc))

    async def finish(self, state, reason):
        self.state, self.reason, self.speed, self.ticket = state, reason, 0., None
        current = asyncio.current_task()
        if self.inference and self.inference is not current and not self.inference.done():
            self.inference.cancel()
            await asyncio.gather(self.inference, return_exceptions=True)
        if self.recorder:
            self.recorder.finish(state=state, reason=reason, distance_m=self.distance,
                minimum_clearance_m=None if self.minimum_clearance == 100 else self.minimum_clearance,
                obstacle_stops=self.stops, observations=self.observations,
                observed_fraction=sum(v != 0 for v in self.grid)/len(self.grid),
                video={"chunks": self.video_sequence, "mime": self.video_type, "complete": self.video_complete})

    async def pause(self):
        if self.state in ACTIVE:
            await self.finish("paused", "Operator paused; end mission before restarting")

    async def land(self):
        if self.state in ACTIVE | {"paused"}:
            await self.finish("ended", "Operator ended virtual mission")

    async def video(self, episode, client, sequence, mime, data):
        if episode != self.episode or client != self.client or not self.recorder:
            raise ValueError("Video belongs to another mission")
        if sequence != self.video_sequence or self.video_complete:
            raise ValueError("Video chunk out of order or stream finalized")
        if mime not in ("video/webm", "video/mp4") or (self.video_type and mime != self.video_type):
            raise ValueError("Unsupported or changed video container")
        if not 0 < len(data) <= 1024*1024:
            raise ValueError("Video chunk exceeds 1 MiB limit")
        self.video_type = mime
        try:
            self.recorder._write(self.recorder.directory/("onboard.webm" if mime == "video/webm" else "onboard.mp4"), data, append=True)
            self.recorder.record("video_chunk", sequence=sequence, bytes=len(data), mime=mime,
                                 clock="host receipt; not exact exposure time")
            self.video_sequence += 1
        except Exception:
            await self.finish("failed", "Recording failed; storage budget may be exhausted")
            raise

    async def finalize_video(self, episode, client):
        if episode != self.episode or client != self.client:
            raise ValueError("Video belongs to another mission")
        self.video_complete = bool(self.video_sequence)
        if self.state not in ACTIVE:
            await self.finish(self.state, self.reason)

    def snapshot(self):
        return {"state": self.state, "reason": self.reason, "episode": self.episode, "policy": self.policy,
            "scene": self.scene, "pose": self.pose, "grid": self.grid, "grid_width": NX, "cell_size": CELL,
            "route": [self.center(c) for c in self.route], "trail": self.trail, "ticket": self.ticket,
            "speed": self.speed, "sensor_frozen": self.sensor_frozen, "observations": self.observations,
            "observed_fraction": sum(v != 0 for v in self.grid)/len(self.grid), "distance_m": self.distance,
            "video_chunks": self.video_sequence, "video_complete": self.video_complete, "video_type": self.video_type,
            "report": f"/reports/{self.episode}/summary.json" if self.episode and self.state not in ACTIVE else None,
            "model": self.manager.status(), "mode": "browser-kinematic-recon"}

    async def close(self):
        await self.land()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
