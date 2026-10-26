"""The dock mission phase: return, acquire, align, descend, settle, docked.

The controller sees frames, a navigation estimate, dock status and a setpoint interface.
It never sees simulation truth. Height, lateral position and yaw during the final approach
come from the tag solution; the estimate only bridges frames.
"""
import math
import time

import cv2
import numpy as np

from app.dock_tags import TagDetector, load_geometry


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


class DockPhase:
    def __init__(self, geometry, dock, vehicle, frames, dock_client, optics, *, log=None, clock=None):
        """dock: registry record with pose {x,y,z,yaw} in the vehicle's frame and index; frames: async () -> (jpeg|None, meta)."""
        self.g, self.p = geometry, geometry['procedure']
        self.dock, self.vehicle, self.frames, self.client = dock, vehicle, frames, dock_client
        self.detector = TagDetector(geometry, dock['index'], optics, self.p['max_reprojection_px'])
        self.mount = geometry['aircraft']
        yaw = dock['pose']['yaw']
        self.origin = np.array([dock['pose']['x'], dock['pose']['y'], dock['pose']['z']], float)
        self.f = np.array([math.cos(yaw), math.sin(yaw), 0.]); self.l = np.array([-math.sin(yaw), math.cos(yaw), 0.]); self.dock_yaw = yaw
        self.log = log if log is not None else []
        self.events = []
        self.frames_seen = self.detections = 0
        self.last_measurement = None
        self.anchor = None   # estimate - tag-measured pose, in the navigation frame, from the last good measurement
        self.bias = np.zeros(2)   # integral of the lateral error (forward, left): cancels a steady plant offset such as a draft

    # Frames: dock (forward, left, up) <-> navigation frame.
    def to_world(self, d, yaw_d):
        return self.origin + d[0]*self.f + d[1]*self.l + np.array([0., 0., d[2]]), wrap(self.dock_yaw + yaw_d)

    def to_dock(self, position, yaw):
        d = np.asarray(position, float) - self.origin
        return np.array([d @ self.f, d @ self.l, d[2]]), wrap(yaw - self.dock_yaw)

    def note(self, state, **fields):
        entry = {'t': round(self.vehicle.now(), 3), 'state': state, **fields}
        self.log.append(entry)
        if len(self.log) > 5000:
            self.log.pop(0)

    async def measure(self):
        """Next frame: the body pose in the dock frame from the tags, or None."""
        jpeg, meta = await self.frames()
        self.frames_seen += 1
        if jpeg is None:
            return None, meta
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        m = self.detector.measure(image, self.mount)
        if m['pose'] is None:
            return None, meta
        self.detections += 1
        self.last_measurement = m
        est_p, est_yaw = self.vehicle.estimate()
        measured_w, measured_yaw = self.to_world(m['pose']['position_m'], m['pose']['yaw_rad'])
        self.anchor = (est_p - measured_w, wrap(est_yaw - measured_yaw))
        return m, meta

    def corrected(self, target_d, yaw_d=0.):
        """A dock-frame target as a navigation goal, using the last tag measurement to cancel the estimate's offset."""
        goal, yaw = self.to_world(target_d, yaw_d)
        if self.anchor is not None:
            goal = goal + self.anchor[0]; yaw = wrap(yaw + self.anchor[1])
        return [*goal, yaw]

    async def goto(self, goal_d, yaw_d, tolerance=.05, timeout=20.):
        """Fly by the navigation estimate alone to a point in the dock frame (no tags needed)."""
        goal, yaw = self.to_world(goal_d, yaw_d)
        await self.vehicle.command([*goal, yaw])
        start = self.vehicle.now()
        while self.vehicle.now() - start < timeout:
            await self.vehicle.wait(.1)
            p, y = self.vehicle.estimate()
            if np.linalg.norm(p - goal) <= tolerance and abs(wrap(y - yaw)) <= math.radians(8) and self.vehicle.speed() < .08:
                return True
        return False

    def step_toward(self, measured, target_d, yaw_target=0., max_step=None, max_turn=None, integrate=False):
        """One bounded move from the measured pose toward a target, issued relative to the estimate."""
        max_step = self.p['max_lateral_speed_m_s']*self.p['frame_period_s'] if max_step is None else max_step
        max_turn = self.p['max_yaw_rate_rad_s']*self.p['frame_period_s'] if max_turn is None else max_turn
        pose = measured['pose']
        measured_p = np.array(pose['position_m']); error = np.asarray(target_d, float) - measured_p
        n = np.linalg.norm(error)
        step = error if n <= max_step else error*max_step/n
        turn = max(-max_turn, min(max_turn, wrap(yaw_target - pose['yaw_rad'])))
        if integrate:
            limit = self.p['integral_limit_m']
            self.bias = np.clip(self.bias + self.p['integral_gain_per_s']*self.p['frame_period_s']*error[:2], -limit, limit)
        est_p, est_yaw = self.vehicle.estimate()
        # The goal lives in the estimate's frame, whose height may be offset from the floor; the
        # vehicle clamps its own setpoint at the ground, so no clamp here or the descent stalls.
        goal = est_p + (step[0] + self.bias[0])*self.f + (step[1] + self.bias[1])*self.l + np.array([0., 0., step[2]])
        return [*goal, wrap(est_yaw + turn)], error

    async def run(self):
        started = self.vehicle.now()
        result = {'outcome': None, 'states': [], 'attempts': 0, 'started': started}
        try:
            outcome = await self.procedure(result)
        except Exception as exc:
            outcome = 'failed'
            result['error'] = f'{type(exc).__name__}: {exc}'
        result.update(outcome=outcome, frames=self.frames_seen, detections=self.detections, duration_s=self.vehicle.now() - started,
                      stand_contacts=getattr(self.vehicle, 'stand_contacts', None), commands=getattr(self.vehicle, 'commands', None),
                      last_measurement=None if self.last_measurement is None else {k: self.last_measurement[k] for k in ('pose', 'detected', 'reprojection_px', 'min_tag_px')})
        return result

    def enter(self, result, state):
        result['states'].append({'state': state, 't': round(self.vehicle.now(), 3)})
        self.note(state)

    async def procedure(self, result):
        p = self.p
        self.enter(result, 'return')
        arrived = await self.goto(p['approach_flu_m'], 0.)
        self.note('return', arrived=arrived)
        attempts = 0
        while True:
            self.enter(result, 'acquire')
            if not await self.acquire():
                self.enter(result, 'land-in-place')
                await self.land_here()
                return 'dock_not_found'
            self.enter(result, 'align')
            aligned = await self.align()
            if aligned == 'timeout':
                self.enter(result, 'land-in-place')
                await self.land_here()
                return 'align_timeout'
            if aligned == 'lost':
                continue
            self.enter(result, 'descend')
            descended = await self.descend()
            if descended == 'lost':
                continue
            self.enter(result, 'settle')
            attempts += 1; result['attempts'] = attempts
            status = await self.settle()
            if status and status['contact']:
                self.enter(result, 'docked')
                result['dock_status'] = status
                # Loop closure: the aircraft is at the dock pose, so the navigation estimate is re-anchored there.
                reset = getattr(self.vehicle, 'reset_estimate', None)
                if reset is not None:
                    await self.vehicle.wait(1.)   # let the airframe settle fully before anchoring
                    reset(self.origin, self.dock_yaw)
                    result['estimate_reset'] = True
                return 'docked'
            self.note('settle', contact=False, status=status, attempt=attempts)
            if attempts > p['retries']:
                return 'docked_without_contact'
            await self.client.set_mode('off')
            self.enter(result, 'retry')
            await self.vehicle.command(self.corrected(p['hover_flu_m']))
            await self.vehicle.wait(3.)

    async def acquire(self):
        """Wait for two consecutive tag solutions; otherwise look left and right about the approach heading,
        then back away from the stand (the usual reason: arrived too close and too high), and look again."""
        p = self.p; start = self.vehicle.now(); consecutive = 0
        self.bias[:] = 0.
        base_p, base_yaw = self.vehicle.estimate()
        search = [('yaw', math.radians(30)), ('yaw', math.radians(-30)), ('back', 1), ('yaw', math.radians(30)), ('yaw', math.radians(-30))]
        stage = 0
        while True:
            m, meta = await self.measure()
            consecutive = consecutive + 1 if m else 0
            if consecutive >= 2:
                self.note('acquire', tags=m['detected'], pose=m['pose']['position_m'])
                return True
            elapsed = self.vehicle.now() - start
            if elapsed > p['acquire_timeout_s']*(stage+1):
                if stage >= len(search):
                    return False
                kind, value = search[stage]; stage += 1
                if kind == 'back':
                    base_p = base_p - value*p['search_back_m']*self.f + np.array([0., 0., p['hover_flu_m'][2] + .05 - p['approach_flu_m'][2]])
                    await self.vehicle.command([*base_p, base_yaw])
                else:
                    await self.vehicle.command([*base_p, wrap(base_yaw + value)])
                self.note('acquire', search=f'{kind} {value:.2f}')
            await self.vehicle.wait(p['frame_period_s'])

    async def align(self):
        p = self.p; start = self.vehicle.now(); lost = 0; held = 0
        hover = np.array(p['hover_flu_m'])
        while self.vehicle.now() - start < p['align_timeout_s']:
            m, meta = await self.measure()
            if m is None:
                if not meta.get('dropped'):
                    lost += 1
                    if lost >= 3:
                        self.note('align', lost=True)
                        return 'lost'
                await self.vehicle.wait(p['frame_period_s'])
                continue
            lost = 0
            goal, error = self.step_toward(m, hover, integrate=True)
            within = (abs(error[0]) <= p['touchdown_tolerance_m'] and abs(error[1]) <= p['touchdown_tolerance_m']
                      and abs(error[2]) <= p['height_tolerance_m'] and abs(m['pose']['yaw_rad']) <= math.radians(p['yaw_tolerance_deg']))
            held = held + 1 if within else 0
            self.note('align', error=[round(float(e), 4) for e in error], yaw_deg=round(math.degrees(m['pose']['yaw_rad']), 2), tags=m['detected'], held=held)
            if held >= 3:
                return 'ok'
            await self.vehicle.command(goal)
            await self.vehicle.wait(p['frame_period_s'])
        return 'timeout'

    async def descend(self):
        p = self.p; lost = 0; target = np.array(p['hover_flu_m'], float)
        step_down = p['descent_speed_m_s']*p['frame_period_s']
        while True:
            m, meta = await self.measure()
            if m is None:
                if meta.get('dropped'):
                    await self.vehicle.wait(p['frame_period_s'])
                    continue
                lost += 1
                last_height = self.last_measurement['pose']['position_m'][2] if self.last_measurement else 1.
                if last_height <= p['blind_descent_height_m']:
                    self.note('descend', blind=True, height=last_height)
                    return await self.touchdown()
                if lost >= 3:
                    self.note('descend', lost=True, height=last_height)
                    await self.vehicle.command(self.corrected(p['hover_flu_m']))
                    await self.vehicle.wait(2.)
                    return 'lost'
                await self.vehicle.wait(p['frame_period_s'])
                continue
            lost = 0
            height = m['pose']['position_m'][2]
            if abs(m['pose']['position_m'][0]) > 2*p['touchdown_tolerance_m'] or abs(m['pose']['position_m'][1]) > 2*p['touchdown_tolerance_m']:
                if height > p['blind_descent_height_m']:
                    self.note('descend', drifted=m['pose']['position_m'])
                    await self.vehicle.command(self.corrected(p['hover_flu_m']))
                    await self.vehicle.wait(1.)
                    return 'lost'
            lateral = max(abs(m['pose']['position_m'][0]), abs(m['pose']['position_m'][1]))
            # Below 0.12 m, hold height until the plant has caught up laterally; the last centimetres are blind.
            target[2] = height if (height < .12 and lateral > p['hold_lateral_m']) else max(0., height - step_down)
            goal, error = self.step_toward(m, target, max_step=max(step_down, p['max_lateral_speed_m_s']*p['frame_period_s']), integrate=True)
            self.note('descend', height=round(height, 4), error=[round(float(e), 4) for e in error], tags=m['detected'])
            if height <= p['blind_descent_height_m']:
                await self.vehicle.command(goal)
                await self.vehicle.wait(p['frame_period_s'])
                return await self.touchdown()
            await self.vehicle.command(goal)
            await self.vehicle.wait(p['frame_period_s'])

    async def touchdown(self):
        """Last centimetres without tags: hold the corrected lateral goal and land."""
        m = self.last_measurement; height = m['pose']['position_m'][2]
        goal, _ = self.step_toward(m, [0., 0., height], max_step=.03, max_turn=.1)   # lateral correction only
        goal[2] -= height + .03   # 3 cm below the floor in the estimate's frame; the vehicle stops at the ground
        await self.vehicle.command(goal)
        return 'ok'

    async def settle(self):
        p = self.p; start = self.vehicle.now()
        await self.client.set_mode('charge')
        while self.vehicle.now() - start < p['settle_timeout_s']:
            await self.vehicle.wait(.25)
            if not self.vehicle.landed:
                continue
            status = await self.client.status()
            if status['contact'] and status['pin_current_ma'] >= p['contact_current_ma']:
                self.note('settle', contact=True, current=status['pin_current_ma'])
                return status
        return await self.client.status()

    async def land_here(self):
        est_p, est_yaw = self.vehicle.estimate()
        if self.last_measurement is not None and self.anchor is not None:
            lateral = self.last_measurement['pose']['position_m'][:2]
            await self.vehicle.command(self.corrected([lateral[0], lateral[1], -.02]))
        else:
            await self.vehicle.command([est_p[0], est_p[1], est_p[2] - 1., est_yaw])
        start = self.vehicle.now()
        while self.vehicle.now() - start < 20 and not self.vehicle.landed:
            await self.vehicle.wait(.25)
