"""Dock A in the simulated room: placement, the dock electronics, a tag camera and two vehicles.

Everything here is privileged simulation (it knows the true pose). The docking controller in
app/docking.py only receives frames, estimates, dock status and commands.
"""
import asyncio
import math
import time

import numpy as np

from app.dock_tags import TagRenderer, body_rotation, extrinsics, optics_from_scene_camera, rot_z


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


class DockWorld:
    """Where the dock stands: origin and forward direction in the room frame, plus the tag column."""
    def __init__(self, geometry, index=0, origin=(1.25, 1.25, 0.), yaw=0.):
        self.geometry, self.index = geometry, index
        self.origin, self.yaw = np.asarray(origin, float), float(yaw)
        self.f = np.array([math.cos(yaw), math.sin(yaw), 0.]); self.l = np.array([-math.sin(yaw), math.cos(yaw), 0.]); self.u = np.array([0., 0., 1.])

    def to_dock(self, position, yaw):
        d = np.asarray(position, float) - self.origin
        return np.array([d @ self.f, d @ self.l, d @ self.u]), wrap(yaw - self.yaw)

    def to_world(self, position_d, yaw_d):
        p = np.asarray(position_d, float)
        return self.origin + p[0]*self.f + p[1]*self.l + p[2]*self.u, wrap(self.yaw + yaw_d)

    def stand_contact(self, position):
        """Guard sphere against the tag stand's plate box."""
        g = self.geometry; p, _ = self.to_dock(position, 0.)
        s = g['stand']; r = g['aircraft']['guard_radius_m']
        gap = np.array([max(s['f_m'][0]-p[0], p[0]-s['f_m'][1], 0.), max(abs(p[1])-s['l_half_m'], 0.), max(-p[2], p[2]-s['height_m'], 0.)])
        return float(np.linalg.norm(gap)) < r

    def pose_record(self):
        return {'x': float(self.origin[0]), 'y': float(self.origin[1]), 'z': float(self.origin[2]), 'yaw': self.yaw}


class DockController:
    """The dock's own electronics: 5 V switch, pin current, pad temperature, faults, contact detection."""
    def __init__(self, world, policy, charge_current_ma=450., contact_current_ma=150.):
        self.world, self.policy = world, policy
        self.mode, self.fault, self.supply_v = 'off', None, 5.
        self.pin_current_ma, self.pad_temp_c, self.contact = 0., 22., False
        self.charge_current_ma, self.contact_current_ma = charge_current_ma, contact_current_ma
        self.started, self.now, self.charge_since = 0., 0., None
        self.cell_v = 3.9
        self.centred = None     # true touchdown error, privileged
        self.events = []

    def five_volts_on(self):
        if self.fault or self.mode == 'off':
            return False
        if self.mode == 'storage':
            return self.cell_v < self.policy['storage_low_v'] or (self.cell_v < self.policy['storage_high_v'] and self.pin_current_ma > 0)
        return True

    def observe(self, position, yaw, landed, now):
        """Physical contact from the true pose: inside the capture square, on the floor, facing the stand."""
        self.now = now
        p, yaw_d = self.world.to_dock(position, yaw)
        g = self.world.geometry
        centred = landed and abs(p[0]) <= g['capture_m'] and abs(p[1]) <= g['capture_m'] and abs(wrap(yaw_d)) <= math.radians(45)
        self.centred = {'f_m': float(p[0]), 'l_m': float(p[1]), 'yaw_deg': math.degrees(yaw_d), 'landed': bool(landed), 'centred': bool(centred)}
        on = self.five_volts_on()
        self.contact = bool(centred and on)
        self.pin_current_ma = (self.charge_current_ma if self.cell_v < self.policy['full_v'] else self.contact_current_ma) if self.contact else 0.
        if self.contact and self.mode == 'charge':
            self.charge_since = self.charge_since or now
            if now - self.charge_since > self.policy['max_charge_s']:
                self.trip('charge timeout')
        if self.pin_current_ma > self.policy['max_current_a']*1000:
            self.trip('overcurrent')
        if self.pad_temp_c > self.policy['max_pad_c']:
            self.trip('pad overtemperature')
        return self.status()

    def trip(self, cause):
        self.fault, self.contact, self.pin_current_ma = cause, False, 0.
        self.events.append({'at': self.now, 'fault': cause})

    def set_mode(self, mode):
        if mode not in ('off', 'charge', 'storage'):
            raise ValueError('Mode must be off, charge or storage')
        self.mode, self.fault = mode, None
        if mode != 'charge':
            self.charge_since = None
        self.events.append({'at': self.now, 'mode': mode})
        return self.status()

    def status(self):
        return {'mode': self.mode, 'supply_v': self.supply_v if self.five_volts_on() else 0., 'pin_current_ma': self.pin_current_ma,
                'pad_temp_c': self.pad_temp_c, 'contact': self.contact, 'fault': self.fault, 'uptime_s': self.now - self.started}


class SimulatedDockClient:
    """What the docking controller sees of a simulated dock: the same two calls as the real link."""
    def __init__(self, controller):
        self.controller = controller

    async def status(self):
        return self.controller.status()

    async def set_mode(self, mode):
        return self.controller.set_mode(mode)

    async def close(self):
        pass


class DockCamera:
    """Renders the tag column from the true aircraft pose with the scene camera's optics, latency and drops.
    Other docks in the room are drawn too, farthest first, with their own tags: the controller must ignore them."""
    def __init__(self, world, scene_camera, seed=0, others=()):
        self.world = world
        self.optics = optics_from_scene_camera(scene_camera)
        self.renderer = TagRenderer(world.geometry, world.index, self.optics, scene_camera.get('effects'), seed)
        self.others = [(other, TagRenderer(other.geometry, other.index, self.optics, scene_camera.get('effects'), seed + 1 + i))
                       for i, other in enumerate(others)]
        self.jpeg_quality = scene_camera.get('jpeg_quality', .72)
        self.latency_s = scene_camera.get('latency_ms', 0)/1000
        self.drop_every_n = scene_camera.get('drop_every_n', 0)
        self.sequence = 0
        self.period_s = world.geometry['procedure']['frame_period_s']

    def views(self, position, yaw, quaternion_rotation=None):
        """(renderer, R_cd, t) for this dock and the others, farthest first."""
        p, yaw_d = self.world.to_dock(position, yaw)
        R_db = quaternion_rotation if quaternion_rotation is not None else body_rotation(yaw_d)
        views = [(self.renderer, *extrinsics(p, R_db, self.world.geometry['aircraft']))]
        for other, renderer in self.others:
            p2, _ = other.to_dock(position, yaw)
            views.append((renderer, *extrinsics(p2, rot_z(self.world.yaw - other.yaw) @ R_db, other.geometry['aircraft'])))
        return sorted(views, key=lambda v: -float(np.linalg.norm(v[2])))

    def render(self, position, yaw, quaternion_rotation=None):
        canvas = self.renderer.blank()
        for renderer, R_cd, t in self.views(position, yaw, quaternion_rotation):
            renderer.draw(canvas, R_cd, t)
        return self.renderer.finish(canvas, jpeg_quality=self.jpeg_quality)

    def capture(self, history, now):
        """One frame from the pose latency_s ago; every nth frame is dropped, as the benchmark camera does."""
        self.sequence += 1
        if self.drop_every_n and self.sequence % self.drop_every_n == 0:
            return None, {'sequence': self.sequence, 'dropped': True, 'time': now}
        target = now - self.latency_s
        pose = history[0]
        for h in history:
            if h[0] <= target:
                pose = h
        return self.render(pose[1], pose[2]), {'sequence': self.sequence, 'dropped': False, 'time': now, 'captured': pose[0]}


class Estimator:
    """The navigation estimate as the controller sees it: truth plus a constant offset and a slow random walk."""
    def __init__(self, offset=(0., 0., 0., 0.), drift_m_s=.002, seed=0):
        self.offset = np.asarray(offset, float); self.drift = np.zeros(3); self.drift_m_s = drift_m_s
        self.rng = np.random.default_rng(seed); self.last = None

    def advance(self, now):
        if self.last is not None and now > self.last:
            self.drift += self.rng.normal(0, self.drift_m_s*math.sqrt(now - self.last), 3)
        self.last = now

    def estimate(self, position, yaw):
        p = np.asarray(position, float) + self.offset[:3] + self.drift
        return p, wrap(yaw + self.offset[3])

    def to_truth(self, goal):
        """Where the aircraft really ends up when it flies its estimate to this goal."""
        return [goal[0]-self.offset[0]-self.drift[0], goal[1]-self.offset[1]-self.drift[1], goal[2]-self.offset[2]-self.drift[2], wrap(goal[3]-self.offset[3])]

    def reset(self, truth_position, truth_yaw, known_position, known_yaw):
        """Re-anchor so that the estimate of the current pose equals the known pose."""
        self.offset = np.array([*(np.asarray(known_position, float) - np.asarray(truth_position, float)), wrap(known_yaw - truth_yaw)])
        self.drift[:] = 0.


class KinematicDockVehicle:
    """First-order aircraft for fast tests: bounded speed, command latency, no real time."""
    def __init__(self, world, start, estimator, *, tau_s=.5, latency_s=.1, max_speed=.35, max_yaw_rate=.8, step_s=.02):
        self.world, self.estimator = world, estimator
        self.position, self.yaw = np.asarray(start[:3], float), float(start[3])
        self.velocity = np.zeros(3); self.goal = None; self.pending = []
        self.tau, self.latency, self.max_speed, self.max_yaw_rate, self.step_s = tau_s, latency_s, max_speed, max_yaw_rate, step_s
        self.t = 0.; self.history = [(0., self.position.copy(), self.yaw)]
        self.stand_contacts = 0; self.distance = 0.; self.landed = start[2] <= .01
        self.commands = 0

    def now(self):
        return self.t

    def truth(self):
        return self.position.copy(), self.yaw

    def estimate(self):
        self.estimator.advance(self.t)
        return self.estimator.estimate(self.position, self.yaw)

    def speed(self):
        return float(np.linalg.norm(self.velocity))

    async def command(self, goal):
        goal = [float(v) for v in goal]
        if len(goal) != 4 or not all(math.isfinite(v) for v in goal) or not -1. <= goal[2] <= 3.:
            raise ValueError('Invalid docking setpoint')
        self.estimator.advance(self.t)
        truth_goal = self.estimator.to_truth(goal); truth_goal[2] = max(0., truth_goal[2])
        self.pending.append((self.t + self.latency, truth_goal)); self.commands += 1

    async def wait(self, seconds):
        end = self.t + seconds
        while self.t < end - 1e-9:
            self.step(min(self.step_s, end - self.t))

    def step(self, dt):
        self.t += dt
        while self.pending and self.pending[0][0] <= self.t:
            self.goal = self.pending.pop(0)[1]
        if self.goal is not None:
            target = np.array(self.goal[:3]); error = target - self.position
            if self.landed and target[2] <= .005:
                self.velocity[:] = 0.
            else:
                self.landed = False
                desired = error/self.tau
                n = np.linalg.norm(desired)
                if n > self.max_speed:
                    desired *= self.max_speed/n
                self.velocity += (desired - self.velocity)*min(1., dt/self.tau)
                move = self.velocity*dt
                self.distance += float(np.linalg.norm(move)); self.position += move
                if self.position[2] <= 0.:
                    self.position[2] = 0.; self.velocity[:] = 0.
                    if target[2] <= .005:
                        self.landed = True
                turn = wrap(self.goal[3] - self.yaw)
                self.yaw = wrap(self.yaw + max(-self.max_yaw_rate*dt, min(self.max_yaw_rate*dt, turn)))
        if any(w.stand_contact(self.position) for w in (self.world, *getattr(self, 'obstacles', ()))):
            self.stand_contacts += 1
        self.history.append((self.t, self.position.copy(), self.yaw))
        if len(self.history) > 200:
            self.history.pop(0)

    def reset_estimate(self, known_position, known_yaw):
        self.estimator.reset(self.position, self.yaw, known_position, known_yaw)

    def check(self):
        pass

    async def close(self):
        pass


class RapierDockVehicle:
    """The service-owned Rapier plant seen through the same interface, in real time."""
    def __init__(self, flight, world, estimator):
        self.flight, self.world, self.estimator = flight, world, estimator
        self.started = time.monotonic(); self.history = []; self.stand_contacts = 0; self.commands = 0

    def now(self):
        return time.monotonic() - self.started

    def truth(self):
        p = self.flight.latest
        return np.array(p['position'], float), float(p['yaw'])

    def estimate(self):
        self.estimator.advance(self.now())
        return self.estimator.estimate(*self.truth())

    def speed(self):
        return float(self.flight.latest['speed'])

    @property
    def landed(self):
        p = self.flight.latest
        return p['position'][2] < .03 and p['speed'] < .15

    async def command(self, goal):
        goal = [float(v) for v in goal]
        if len(goal) != 4 or not all(math.isfinite(v) for v in goal) or not -1. <= goal[2] <= 2.:
            raise ValueError('Invalid docking setpoint')
        await self.flight.check_fresh()
        self.estimator.advance(self.now())
        truth_goal = self.estimator.to_truth(goal)
        truth_goal[2] = min(1.8, max(0., truth_goal[2]))
        if not .2 <= truth_goal[0] <= 11.8 or not .2 <= truth_goal[1] <= 9.8:
            raise ValueError('Invalid bounded flight setpoint')
        self.flight.goal = truth_goal; self.commands += 1

    async def wait(self, seconds):
        end = time.monotonic() + seconds
        while True:
            self.flight.check()
            position, yaw = self.truth()
            self.history.append((self.now(), position, yaw))
            if len(self.history) > 200:
                self.history.pop(0)
            if any(w.stand_contact(position) for w in (self.world, *getattr(self, 'obstacles', ()))):
                self.stand_contacts += 1
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(.05, remaining))

    def reset_estimate(self, known_position, known_yaw):
        self.estimator.reset(*self.truth(), known_position, known_yaw)

    def check(self):
        self.flight.check()

    async def close(self):
        pass


class DockSimulation:
    """Wires a dock, its camera and electronics to a vehicle; hands the controller only what it may see."""
    def __init__(self, geometry, scene_camera, vehicle_factory, estimator, *, origin=(1.25, 1.25, 0.), yaw=0., index=0, seed=0, others=()):
        """others: (origin, yaw, index) of the room's other docks; they show in the camera with their own tags and their stands are solid."""
        self.geometry = geometry
        self.world = DockWorld(geometry, index, origin, yaw)
        self.others = [DockWorld(geometry, i, o, y) for o, y, i in others]
        self.controller = DockController(self.world, geometry['charge_policy'])
        self.camera = DockCamera(self.world, scene_camera, seed, self.others)
        self.estimator = estimator
        self.vehicle = vehicle_factory(self.world, estimator)
        self.vehicle.obstacles = self.others
        simulation = self

        class Client(SimulatedDockClient):
            async def status(self):
                simulation.observe()
                return self.controller.status()
        self.client = Client(self.controller)
        self.record = {'id': f'sim-dock-{index}', 'name': 'Simulated dock A', 'index': index, 'pose': self.world.pose_record()}

    def observe(self):
        position, yaw = self.vehicle.truth()
        return self.controller.observe(position, yaw, self.vehicle.landed and self.vehicle.speed() < .15, self.vehicle.now())

    async def frames(self):
        self.observe()
        history = self.vehicle.history or [(self.vehicle.now(), *self.vehicle.truth())]
        return self.camera.capture(history, self.vehicle.now())

    def phase(self, log=None):
        from app.docking import DockPhase
        return DockPhase(self.geometry, self.record, self.vehicle, self.frames, self.client, self.camera.optics, log=log)

    def truth(self):
        """Privileged summary for scoring: where the aircraft really is relative to the dock."""
        position, yaw = self.vehicle.truth()
        p, yaw_d = self.world.to_dock(position, yaw)
        others = []
        for w in self.others:
            q, _ = w.to_dock(position, yaw)
            others.append({'index': w.index, 'f_m': float(q[0]), 'l_m': float(q[1]), 'distance_m': float(math.hypot(q[0], q[1]))})
        return {'f_m': float(p[0]), 'l_m': float(p[1]), 'u_m': float(p[2]), 'yaw_deg': math.degrees(yaw_d), 'landed': bool(self.vehicle.landed),
                'centred': self.controller.centred, 'stand_contacts': self.vehicle.stand_contacts, 'other_docks': others}


def return_gate_start(rng, geometry, max_error_m=.4, max_yaw_error_deg=15.):
    """A navigation error drawn from the return gate: the estimate is off by up to 0.4 m and 15 degrees."""
    r = max_error_m*math.sqrt(rng.uniform(0, 1)); a = rng.uniform(0, 2*math.pi)
    return np.array([r*math.cos(a), r*math.sin(a), rng.uniform(-.08, .08), math.radians(rng.uniform(-max_yaw_error_deg, max_yaw_error_deg))])


def kinematic_docking(seed, geometry, scene_camera, *, origin=(1.25, 1.25, 0.), yaw=0., start_d=(-1.6, .6, .9), index=0, others=(), **vehicle_options):
    """One docking of the first-order vehicle, starting away from the dock with a drawn navigation error."""
    rng = np.random.default_rng(seed)
    error = return_gate_start(rng, geometry)
    estimator = Estimator(offset=(error[0], error[1], error[2], error[3]), seed=seed)
    world = DockWorld(geometry, index, origin, yaw)
    start_w, start_yaw = world.to_world(start_d, 0.)
    factory = lambda w, e: KinematicDockVehicle(w, [*start_w, start_yaw], e, **vehicle_options)
    return DockSimulation(geometry, scene_camera, factory, estimator, origin=origin, yaw=yaw, index=index, seed=seed, others=others), error


def beside(world, left_m=.6, index=None):
    """(origin, yaw, index) of a second dock standing left_m to the left of this one, facing the same way."""
    origin, yaw = world.to_world((0., left_m, 0.), 0.)
    return tuple(float(v) for v in origin), float(yaw), (1 - world.index) if index is None else index
