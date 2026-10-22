"""Bounded indoor reconnaissance in a deterministic, ideal-pose kinematic sandbox.

Ground truth is used by the range-sensor/collision simulator and renderer only.
The route planner consumes an observed occupancy grid, never obstacle geometry.
"""
import asyncio
import json
import math
import time
import uuid

from app.recorder import RunRecorder
from app.navigation import ObservedMap, supervised_velocity, CELL, RADIUS, MARGIN, SPEED, BRAKE
from adapters.kinematic import KinematicVehicle
from sim.recon_world import world, clearance, WIDTH, DEPTH, SCENARIOS

NX, NY = int(WIDTH/CELL), int(DEPTH/CELL)
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




class Recon:
    def __init__(self, manager, runs):
        self.manager, self.runs = manager, runs
        self.vehicle = KinematicVehicle(world(137))
        self.navigation = ObservedMap()
        self.task = self.inference = None
        self.recorder = None
        self.state, self.reason, self.episode = "idle", "Ready for a virtual mission", None
        self.pose = [1.25, 1.25, 1.4, 0.0]
        self.grid = [0]*(NX*NY)  # 0 unknown, 1 observed free, 2 observed occupied
        self.route, self.trail, self.observations = [], [], []
        self.breadcrumbs, self.return_trace = [[1.25,1.25]], None
        self.ranges, self.speed = [], 0.
        self.ticket, self.frame = None, None
        self.sensor_frozen = False
        self.video_sequence, self.video_type, self.video_complete = 0, None, False
        self.client = None
        self.policy = "qwen"
        self.return_requested = False
        self.visited = set()
        self.minimum_clearance, self.distance, self.stops = 100., 0., 0
        self.mission = 'explore'
        self.checkpoint_index = 0
        self.current_view = None
        self.baseline = None
        self.frame_video_time = None
        self.unreached = []
        self.checkpoints = self.scene['checkpoints']
        self.task_context = None

    @property
    def scene(self): return self.vehicle.scene
    @scene.setter
    def scene(self, value): self.vehicle.scene = value
    @property
    def pose(self): return self.vehicle.pose
    @pose.setter
    def pose(self, value): self.vehicle.pose = value
    @property
    def speed(self): return self.vehicle.speed
    @speed.setter
    def speed(self, value): self.vehicle.speed = value
    @property
    def grid(self): return self.navigation.grid
    @grid.setter
    def grid(self, value): self.navigation.grid = value

    def cell(self, x, y): return self.navigation.cell(x, y)
    def center(self, cell): return self.navigation.center(cell)

    def configure(self, seed, scenario='room', variant='baseline', condition='nominal'):
        if self.state in ACTIVE or self.state == "paused":
            raise RuntimeError("End this mission before generating another room")
        if type(seed) is not int or not 0 <= seed <= 2**31-1:
            raise ValueError("Seed must be an integer from 0 through 2147483647")
        self.vehicle.reset(world(seed, scenario, variant, condition))
        self.checkpoints = self.scene['checkpoints']
        self.task_context = None
        self.navigation = ObservedMap()
        self.grid, self.route, self.trail = [0]*(NX*NY), [], []
        self.breadcrumbs, self.return_trace = [[1.25,1.25]], None

    async def start(self, policy, client, mission='explore', compare=True, *, checkpoint_ids=None, task_context=None):
        if self.state in ACTIVE or self.state == "paused":
            raise RuntimeError("A mission is already active")
        if self.task and not self.task.done():
            await self.task
        if policy not in ("qwen", "scripted"):
            raise ValueError("Select local Qwen or explicitly select the scripted demo")
        if mission not in ('explore', 'patrol') or (mission == 'patrol' and not self.scene['checkpoints']):
            raise ValueError('Select a workshop, warehouse or connected-room environment for a patrol')
        if not isinstance(client, str) or not 1 <= len(client) <= 80:
            raise ValueError("A browser client identifier is required")
        if policy == "qwen" and (not self.manager.ready or self.manager.status()["busy"]):
            raise RuntimeError("Start the local model and wait for model operations to finish")
        if checkpoint_ids is not None:
            available = {c['id'] for c in self.scene['checkpoints']}
            if (mission != 'patrol' or not isinstance(checkpoint_ids, list) or not checkpoint_ids
                or any(not isinstance(c, str) or c not in available for c in checkpoint_ids)
                or len(set(checkpoint_ids)) != len(checkpoint_ids)):
                raise ValueError('Invalid assigned inspection points')
        self.configure(self.scene['seed'], self.scene['scenario'], self.scene['variant'], self.scene.get('condition', 'nominal'))
        if checkpoint_ids is not None:
            self.checkpoints = [c for c in self.scene['checkpoints'] if c['id'] in checkpoint_ids]
        self.task_context = task_context
        self.mission, self.checkpoint_index, self.current_view = mission, 0, None
        self.unreached = []
        self.baseline = self.find_baseline() if compare and policy == 'qwen' and mission == 'patrol' else None
        self.inference = None
        self.policy, self.client, self.episode = policy, client, uuid.uuid4().hex
        self.recorder = RunRecorder(self.runs, self.episode, 1024**3, {
            "mode": "browser-kinematic-recon", "seed": self.scene["seed"], "policy": policy,
            "real_inference": policy == "qwen", "physical_transport": False,
            "real_flight_dynamics": False, "pose": "ideal simulated pose", "altitude_m": 1.4,
            "mission": mission, "scenario": self.scene['scenario'], "variant": self.scene['variant'],
            "camera": self.scene['camera'], "visual_revision": self.scene['visual_revision'],
            "condition": self.scene.get('condition', 'nominal'),
            "inspection_points": [c['id'] for c in self.checkpoints], "task_context": self.task_context,
            "baseline_episode": self.baseline['episode'] if self.baseline else None,
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
        self.ranges = self.vehicle.ranges(now)
        self.navigation.integrate(self.pose, self.ranges, now)

    def neighbors(self, cell): return self.navigation.neighbors(cell)
    def safe_cell(self, cell): return self.navigation.safe_cell(cell)
    def plan(self, returning=False):
        if self.mission == 'patrol' and not returning and self.checkpoint_index < len(self.checkpoints):
            goal = self.checkpoints[self.checkpoint_index]['position']
            route = self.navigation.plan(self.pose, self.visited, goal=goal)
            if route:
                return route
        return self.navigation.plan(self.pose, self.visited, returning)

    def find_baseline(self):
        from app.reports import list_runs
        for run in list_runs(self.runs):
            if (run.get('state') == 'complete' and run.get('policy') == 'qwen'
                and run.get('mission') == 'patrol' and run.get('scenario') == self.scene['scenario']
                and run.get('visual_revision', 'blocks-v1') == self.scene['visual_revision']
                and run.get('camera', {}).get('id', 'lean') == self.scene['camera']['id']
                and (self.scene['scenario'] != 'realism' or run.get('camera') == self.scene['camera'])
                and run.get('inspection_points', [c['id'] for c in self.scene['checkpoints']]) == [c['id'] for c in self.checkpoints]
                and run.get('seed') == self.scene['seed']):
                return run
        return None

    def begin_observation(self):
        self.state, self.speed = "observing", 0.
        self.ticket = uuid.uuid4().hex
        self.frame = None
        self.frame_video_time = None
        self.waiting_since = time.monotonic()
        self.reason = "Waiting for a fresh onboard camera image"

    def camera(self, episode, client, ticket, jpeg, video_time_s=None):
        if episode != self.episode or client != self.client or self.state not in ACTIVE | {"paused"}:
            raise ValueError("Camera belongs to another or completed mission")
        if len(jpeg) > 200_000 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            raise ValueError("Expected a bounded JPEG camera frame")
        if video_time_s is not None and (not math.isfinite(video_time_s) or
                not 0 <= video_time_s <= min(200, time.monotonic()-self.started+1)):
            raise ValueError('Invalid camera recording timestamp')
        self.last_browser = time.monotonic()
        if self.state == "observing" and ticket == self.ticket and self.frame is None:
            self.frame = (jpeg, time.monotonic(), list(self.pose))
            self.frame_video_time = video_time_s

    async def inspect(self):
        jpeg, captured, pose = self.frame
        ticket = self.ticket
        self.recorder._write(self.recorder.directory/f"{ticket}.jpg", jpeg)
        started = time.monotonic()
        reference = None
        allowed = ['continue', 'hold'] if self.relook else ['continue', 'look_left', 'look_right', 'hold']
        if self.mission == 'explore':
            allowed.append('finish')
        if self.baseline and self.current_view:
            reference = next((o for o in self.baseline.get('observations', [])
                              if o.get('view') == self.current_view), None)
        comparison_note = None
        if reference:
            from app.perception import aligned_views
            if not aligned_views(reference.get('pose'), pose):
                reference = None
                comparison_note = 'Previous camera pose differs; change was not assessed.'
        comparison = None
        perception = change = object_survey = None
        if self.policy == 'qwen':
            from app.perception import inspect, choose_action, compare, survey, VERSION, DETAIL_VERSION, PASSAGE_VERSION
            # Separate current-image evidence from control and historical comparison.
            # The small VLM confused images when all three jobs shared a prompt.
            detailed = self.scene['camera']['id'] in ('module3-720p', 'inspection-720p')
            checkpoint = next((c for c in self.checkpoints if c['id'] == self.current_view), {})
            inspection_task = checkpoint.get('inspection_task', 'center')
            if (self.task_context or {}).get('objective') == 'passage' and checkpoint.get('id') == 'passage':
                inspection_task = 'passage'
            version = PASSAGE_VERSION if inspection_task == 'passage' else DETAIL_VERSION if detailed else VERSION
            async with asyncio.timeout(18 if detailed else 10):
                perception = await inspect(self.manager.image, jpeg, detailed=detailed, task=inspection_task)
                if reference:
                    from app.reports import evidence_image
                    previous = reference.get('perception')
                    if not previous or previous.get('version') != version:
                        path = evidence_image(self.runs, self.baseline['episode'], reference['image'])
                        previous = await inspect(self.manager.image, path.read_bytes(), detailed=detailed, task=inspection_task)
                    change = compare(previous, perception)
                    comparison = {'episode': self.baseline['episode'], 'image': reference['image']}
                action = await choose_action(self.manager.text, perception, allowed)
                if detailed:
                    object_survey = await survey(self.manager.image, jpeg, focus=(self.task_context or {}).get('focus', ''))
            result = {'action': action, 'observation': perception['visible_evidence']}
        else:
            result = {'action': 'continue', 'observation': 'Scripted demo: no model perception performed.'}
        observation = {**result, 'image': f'{ticket}.jpg', 'pose': pose, 'view': self.current_view,
                       'received_monotonic': captured, 'elapsed_s': captured-self.started,
                       'video_time_s': self.frame_video_time, 'comparison': comparison,
                       'perception': perception, 'change': change,
                       'survey': object_survey,
                       'comparison_note': comparison_note,
                       'latency_s': time.monotonic()-started}
        self.recorder.record('observation', **observation)
        self.observations.append(observation)
        self.ticket, self.frame = None, None
        self.last_observe = time.monotonic()
        if result['action'] == 'hold':
            await self.finish("paused", "Model requested a hold; end mission before restarting")
        elif result['action'] in ('look_left', 'look_right') and not self.relook and not self.return_requested:
            self.vehicle.look(self.pose[3] + math.pi/2 * (1 if result['action'] == 'look_left' else -1))
            self.relook = True
            if self.current_view:
                self.current_view += ':'+result['action']
            self.begin_observation()
        else:
            self.relook = False
            if self.mission == 'patrol':
                self.checkpoint_index += 1
                self.current_view = None
            self.return_requested |= result['action'] == 'finish' or len(self.observations) >= 12
            self.return_requested |= self.mission == 'patrol' and self.checkpoint_index >= len(self.checkpoints)
            self.state = 'returning' if self.return_requested else 'exploring'
            self.reason = 'Returning through the observed map' if self.return_requested else 'Exploring observed free space'
            self.route = []

    def move(self, dt, now):
        if now-self.sensor_time > .35:
            raise RuntimeError("Range sensors stale: motion stopped")
        if self.return_trace is None and self.route and not self.safe_cell(self.route[0]):
            self.route = []
            self.vehicle.hold()
            self.stops += 1
            return True
        if self.return_trace is None and not self.route:
            self.route = self.plan(self.return_requested)
            if not self.route:
                if (not self.return_requested or len(self.breadcrumbs) < 2 or
                    math.dist(self.pose[:2],self.breadcrumbs[-1]) > .01):
                    return False
                # A coarse occupancy grid can disconnect a path already flown.
                # Retrace only recorded segments; every step still needs fresh
                # swept-disc range clearance. Never jump directly toward home.
                self.return_trace = list(reversed(self.breadcrumbs))
                self.reason = 'Returning along the recorded path with fresh range checks'
        if self.return_trace is not None:
            while self.return_trace and math.dist(self.pose[:2],self.return_trace[0]) < .001:
                self.return_trace.pop(0)
            if not self.return_trace:
                return False
        target = self.return_trace[0] if self.return_trace is not None else self.center(self.route[0])
        command = supervised_velocity(self.pose, self.speed, target, self.ranges, dt, now)
        if command is None:
            self.vehicle.hold()
            self.stops += 1
            if self.return_trace is not None:
                raise RuntimeError('Recorded return path blocked by fresh range; motion stopped')
            self.visited.add(self.route[0])
            self.navigation.blocked.add(self.route[0])
            self.route = []
            if self.stops > 20:
                raise RuntimeError("Too many obstacle stops; mission ended")
            return True
        before = list(self.pose[:2])
        self.vehicle.advance(command, dt)
        self.minimum_clearance = self.vehicle.minimum_clearance
        self.distance += math.dist(before, self.pose[:2])
        self.visited.add(self.cell(*self.pose[:2]))
        if math.dist(target, self.pose[:2]) < .001:
            (self.return_trace if self.return_trace is not None else self.route).pop(0)
        if self.return_trace is None:
            point=list(self.pose[:2])
            if len(self.breadcrumbs) >= 2:
                a=[self.breadcrumbs[-1][i]-self.breadcrumbs[-2][i] for i in (0,1)]
                b=[point[i]-self.breadcrumbs[-1][i] for i in (0,1)]
                if abs(a[0]*b[1]-a[1]*b[0]) < 1e-9 and a[0]*b[0]+a[1]*b[1] > 0:
                    self.breadcrumbs.pop()
            self.breadcrumbs.append(point)
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
                elif (not self.return_requested and self.mission == 'patrol' and
                      math.dist(self.pose[:2], self.checkpoints[self.checkpoint_index]['position']) < .001):
                    checkpoint = self.checkpoints[self.checkpoint_index]
                    self.vehicle.look(checkpoint['yaw'])
                    self.current_view = checkpoint['id']
                    self.begin_observation()
                elif not self.return_requested and self.mission == 'explore' and now-self.last_observe >= 5:
                    self.begin_observation()
                elif not self.return_requested and now-self.started > 110:
                    self.return_requested, self.state, self.route = True, 'returning', []
                elif self.return_requested and math.dist(self.pose[:2], [1.25,1.25]) < .1:
                    partial = self.mission == 'patrol' and self.checkpoint_index < len(self.checkpoints)
                    await self.finish('partial' if partial else 'complete',
                        'Returned home; some inspection points were not reached' if partial else 'Returned home; reconnaissance complete')
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
            self.minimum_clearance = self.vehicle.minimum_clearance
            self.unreached = ([c['id'] for c in self.checkpoints[self.checkpoint_index:]]
                              if self.mission == 'patrol' else [])
            self.recorder.finish(state=state, reason=reason, distance_m=self.distance,
                minimum_clearance_m=None if self.minimum_clearance == 100 else self.minimum_clearance,
                obstacle_stops=self.stops, observations=self.observations,
                duration_s=time.monotonic()-self.started, trail=self.trail, unreached=self.unreached,
                return_recovery_used=self.return_trace is not None,
                grid=self.grid, grid_width=NX, cell_size=CELL,
                camera_coverage='unmeasured', video_clock='browser elapsed time; approximate frame alignment',
                observed_fraction=sum(v != 0 for v in self.grid)/len(self.grid),
                video={"chunks": self.video_sequence, "mime": self.video_type, "complete": self.video_complete})

    async def pause(self):
        if self.state in ACTIVE:
            await self.finish("paused", "Operator paused; end mission before restarting")

    def return_home(self):
        if self.state not in ACTIVE:
            raise RuntimeError('No active flight to return')
        self.return_requested, self.route = True, []
        # Let any in-flight inference finish; cancelling HTTP quarantines the model.
        if self.state != 'observing':
            self.state = 'returning'
        self.reason = 'Operator requested return; finishing any current observation'

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
            "client": self.client, "inspection_points": [c['id'] for c in self.checkpoints], "task_context": self.task_context,
            "scene": self.scene, "pose": self.pose, "grid": self.grid, "grid_width": NX, "cell_size": CELL,
            "route": [self.center(c) for c in self.route], "trail": self.trail, "ticket": self.ticket,
            "speed": self.speed, "sensor_frozen": self.sensor_frozen, "observations": self.observations,
            "observed_fraction": sum(v != 0 for v in self.grid)/len(self.grid), "distance_m": self.distance,
            "video_chunks": self.video_sequence, "video_complete": self.video_complete, "video_type": self.video_type,
            "report": f"/reports/{self.episode}/summary.json" if self.episode and self.state not in ACTIVE else None,
            "model": self.manager.status(), "mode": "browser-kinematic-recon",
            "mission": self.mission, "baseline_episode": self.baseline['episode'] if self.baseline else None,
            "report_page": f"/reports/{self.episode}/report.html" if self.episode and self.state not in ACTIVE else None}

    async def close(self):
        await self.land()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
