"""Service-owned microquad physics. Browser/operator lifetimes do not own flight."""
import asyncio
import json
import math
from pathlib import Path
import time

from app.mission_navigation import flight_path, clearance

ROOT = Path(__file__).resolve().parents[1]


class RapierDrone:
    def __init__(self, assembly, scene, folder, seed=137):
        self.assembly, self.scene, self.folder, self.seed = assembly, scene, folder, seed
        self.process = self.pump = None
        self.lock = asyncio.Lock()
        self.latest = None
        self.goal = None
        self.phase = 'ready'
        self.message = 'Preparing service-owned simulation'
        self.error = None
        self.interrupt = None
        self.samples = []
        self.last_received = 0
        self.landed = False
        self.distance = 0
        self.minimum_clearance = float('inf')
        self.envelope_violations = 0
        self.radius = .35  # Preserve the earlier hard-suite conservative envelope.
        # Navigation sees geometry only. Object identities and target truth are absent.
        self.map = {k: scene[k] for k in ('width', 'depth', 'moving_actor')}
        self.map.update({key: [{k: b[k] for k in ('x', 'y', 'sx', 'sy', 'height', 'bottom') if k in b}
                              for b in scene.get(key, [])] for key in ('obstacles', 'fixtures')})

    async def start(self):
        path = self.folder/'physics-input.json'
        path.write_text(json.dumps({'assembly': self.assembly, 'scene': self.scene, 'seed': self.seed}))
        self.log = (self.folder/'physics.log').open('wb')
        self.process = await asyncio.create_subprocess_exec('node', 'scripts/mission-transport.cjs', str(path),
            cwd=ROOT, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.log)
        self.latest = await self.call('status')
        self.last_received = time.monotonic()
        self.pump = asyncio.create_task(self.run())

    async def call(self, operation, **body):
        async with self.lock:
            if self.process.returncode is not None:
                raise RuntimeError('Physics worker exited')
            self.process.stdin.write((json.dumps({'op': operation, **body})+'\n').encode())
            await self.process.stdin.drain()
            line = await asyncio.wait_for(self.process.stdout.readline(), 3)
            if not line:
                raise RuntimeError('Physics worker closed its telemetry stream')
            result = json.loads(line)
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result

    async def run(self):
        try:
            with (self.folder/'telemetry.jsonl').open('w') as output:
                while True:
                    packet = await self.call('command', target=self.goal) if self.goal else await self.call('status')
                    old = self.latest
                    self.latest, self.last_received = packet, time.monotonic()
                    if old and self.goal:
                        self.distance += math.dist(old['position'], packet['position'])
                    if self.goal and packet['position'][2] > .1:
                        separation = clearance(self.map, packet['position'])
                        self.minimum_clearance = min(self.minimum_clearance, separation)
                        self.envelope_violations += int(separation < self.radius)
                    sample = self.snapshot(include_trail=False)
                    output.write(json.dumps(sample)+'\n')
                    self.samples.append(sample)
                    if len(self.samples) > 8000:
                        self.samples.pop(0)
                    await asyncio.sleep(.05)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'

    def snapshot(self, include_trail=True):
        p = self.latest
        if not p:
            return {'truth': None}
        estimate = {'position': p['position'], 'quaternion': p['quaternion']}
        # The renderer is privileged; the vision policy receives estimated pose
        # and pixels only. This reference is ideal, explicitly not real indoor VIO.
        return {'truth': {**estimate, 'sim_time': p['time_s'], 'cart_position': p['cart_position']},
                'estimated': estimate, 'wall_time': time.time(), 'speed': p['speed'],
                'angular_speed': p['angular_speed'], 'phase': self.phase, 'message': self.message,
                **({'trail': [s['estimated']['position'] for s in self.samples[::10]][-500:]} if include_trail else {}),
                'telemetry': p, 'position_source': 'ideal external reference; not a hardware estimator'}

    def check(self):
        if self.interrupt:
            raise RuntimeError(self.interrupt)
        if self.error:
            raise RuntimeError(self.error)
        if time.monotonic()-self.last_received > .5:
            raise RuntimeError('Stale vehicle telemetry')
        if self.latest.get('transport', {}).get('sample_age_s', 0) > .5:
            raise RuntimeError('Ground transport has stale aircraft telemetry')
        if self.latest['contacts'] or self.envelope_violations:
            raise RuntimeError('Vehicle violated the collision/separation envelope')
        if self.latest['tripped'] or self.latest['failsafe']:
            raise RuntimeError('Aircraft power/command watchdog fault')
        if self.latest['max_tilt_deg'] >= 35:
            raise RuntimeError('Aircraft exceeded the component-test attitude limit')

    async def check_fresh(self):
        # CPU work may finish before the periodic reader gets its next turn.
        # Hold the current bounded setpoint while requesting fresh telemetry;
        # an old local cache must not be mistaken for an expired aircraft link.
        if time.monotonic()-self.last_received > .3:
            packet = await asyncio.wait_for(self.call('status'), .5)
            self.latest, self.last_received = packet, time.monotonic()
        self.check()

    async def settle(self, target, timeout=40):
        # Reject before publishing to the radio pump so an invalid planner
        # output cannot terminate telemetry or prevent a controlled landing.
        if (len(target) != 4 or not all(math.isfinite(v) for v in target)
                or not .2 <= target[0] <= 11.8 or not .2 <= target[1] <= 9.8
                or not 0 <= target[2] <= 1.8):
            raise ValueError('Invalid bounded flight setpoint')
        await self.check_fresh()
        self.goal = list(target)
        since = None
        async with asyncio.timeout(timeout):
            while True:
                await self.check_fresh()
                if self.latest['arrived'] and self.latest['goal'] == self.goal:
                    since = since or time.monotonic()
                    if time.monotonic()-since >= .6:
                        return
                else:
                    since = None
                await asyncio.sleep(.1)

    async def takeoff(self):
        self.phase = 'takeoff'
        await self.settle([*self.scene['home'], 1.5, 0], 20)

    def can_inspect(self, pose):
        return .9 <= pose[2] <= 1.8 and clearance(self.map, pose) >= .61

    async def fly(self, pose):
        self.phase = 'transit'
        points = await asyncio.to_thread(flight_path, self.map, self.latest['position'], pose)
        for xyz in points:
            await self.settle([*xyz, pose[3]])
        self.phase = 'inspection'
        await self.settle(pose)
        await asyncio.sleep(.35)  # Let the delayed camera packet settle too.

    async def land(self):
        self.phase = 'landing'
        p = self.latest['position']
        self.goal = [p[0], p[1], 0, self.latest['yaw']]
        async with asyncio.timeout(20):
            while self.latest['position'][2] >= .05 or self.latest['speed'] >= .15:
                if self.error:
                    raise RuntimeError(self.error)
                await asyncio.sleep(.1)
        self.phase, self.landed = 'landed', True

    async def return_land(self):
        await self.fly([*self.scene['home'], 1.5, 0])
        await self.land()

    async def watchdog_land(self):
        """Latch radio silence and observe the aircraft's own expiry landing.

        Retain the original error and failed mission status. This recovery is
        evidence of landing, never a substitute for a successful task.
        """
        if self.pump:
            self.pump.cancel()
            await asyncio.gather(self.pump, return_exceptions=True)
        self.phase, self.goal = 'failsafe-landing', None
        await self.call('failsafe')
        async with asyncio.timeout(20):
            with (self.folder/'telemetry.jsonl').open('a') as output:
                while True:
                    old = self.latest
                    self.latest = await self.call('status')
                    self.last_received = time.monotonic()
                    if old:
                        self.distance += math.dist(old['position'], self.latest['position'])
                    if self.latest['position'][2] > .1:
                        separation = clearance(self.map, self.latest['position'])
                        self.minimum_clearance = min(self.minimum_clearance, separation)
                        self.envelope_violations += int(separation < self.radius)
                    output.write(json.dumps(self.snapshot(include_trail=False))+'\n')
                    if (self.latest['transport']['sample_age_s'] < .5
                            and self.latest['position'][2] < .05 and self.latest['speed'] < .15):
                        self.phase, self.landed = 'landed', True
                        return
                    await asyncio.sleep(.1)

    def metrics(self):
        p = self.latest or {}
        return {'engine': 'Rapier 0.21.0 / unchanged micro-physics plant', 'dt_s': .004,
                'distance_m': self.distance, 'minimum_clearance_m': self.minimum_clearance if math.isfinite(self.minimum_clearance) else None,
                'envelope_violations': self.envelope_violations, 'envelope_radius_m': self.radius,
                'clearance_metric': '3D signed distance to obstacle boxes, walls, ceiling and cart swept bounds; controlled floor contact excluded',
                'landed': self.landed, 'telemetry': p, 'error': self.error,
                'physical_enabled': False, 'position_source': 'ideal external reference'}

    async def close(self):
        if self.pump:
            self.pump.cancel()
            await asyncio.gather(self.pump, return_exceptions=True)
        if self.process and self.process.returncode is None:
            try:
                await self.call('close')
                await asyncio.wait_for(self.process.wait(), 3)
            except Exception:
                self.process.kill()
                await self.process.wait()
        if hasattr(self, 'log'):
            self.log.close()
