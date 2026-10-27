"""Three aircraft in one room on the shared airspace.

Each aircraft flies out through the room's one doorway to a far point in the other hall and back to its home, so all
three want the same gap at about the same time. Before each leg and five times a second while flying it, a flight asks the
airspace; on 'hold' it stops where it is. Legs are planned round the other aircraft as keep-out boxes. Positions go
to the airspace as estimates (a drawn offset plus drift), the scoring uses the truth. One aircraft's reports stop
for two seconds at a drawn moment: the others must hold.

Plants: `kinematic` (first-order model on a simulated clock, seconds per run) or `rapier` (one transport and
physics process pair per aircraft, real time, about a minute per run).
"""
import asyncio
import copy
import math
import time

import numpy as np

from app.airspace import GIVE_WAY_M, Airspace, segment_distance
from app.mission_navigation import clearance, flight_path
from sim.dock_world import Estimator

CRUISE_M = 1.5
REACH_M = .25
HOLD_SPEED = .15
BLACKOUT_S = 2.
RUN_LIMIT_S = 180.
AIRCRAFT = ('scout-01', 'scout-02', 'scout-03')
# The benchmark room is two halls joined by one doorway at about (6.0, 4.0): three aircraft from three sides want that gap,
# and at 1.5 m separation only one fits through at a time.
HOMES = {'scout-01': (3., 5.), 'scout-02': (8.5, 5.5), 'scout-03': (4.5, 7.5)}
FAR = {'scout-01': (7.5, 3.5), 'scout-02': (5., 4.5), 'scout-03': (9., 6.)}   # each clear of every home by the keep-out box


class SimClock:
    """Simulated time for the kinematic plants: steps every vehicle and wakes the sleepers whose time has come.
    speedup None runs as fast as the event loop allows; a number throttles to that multiple of the wall clock."""
    def __init__(self, speedup=None):
        self.t = 0.; self.speedup = speedup; self.vehicles = []; self.running = True; self.sleepers = []

    def now(self):
        return self.t

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self.sleepers.append((self.t + seconds, future))
        await future

    async def run(self, dt=.05):
        while self.running:
            for v in self.vehicles:
                v.step(dt)
            self.t += dt
            due = [f for wake, f in self.sleepers if wake <= self.t + 1e-9]
            self.sleepers = [(wake, f) for wake, f in self.sleepers if wake > self.t + 1e-9]
            for f in due:
                if not f.done():
                    f.set_result(None)
            await asyncio.sleep(0 if self.speedup is None else dt/self.speedup)
            await asyncio.sleep(0)


def operator_map(scene):
    out = {k: scene[k] for k in ('width', 'depth', 'moving_actor')}
    out.update({key: [{k: b[k] for k in ('x', 'y', 'sx', 'sy', 'height', 'bottom') if k in b} for b in scene.get(key, [])] for key in ('obstacles', 'fixtures')})
    return out


class KinematicAircraft:
    """The plant interface the mission loop uses (latest, settle, takeoff, land, check), as a first-order model."""
    def __init__(self, scene, home, clock, *, max_speed=.7, tau=.6):
        self.scene, self.clock, self.map = scene, clock, operator_map(scene)
        self.position = np.array([home[0], home[1], 0.]); self.velocity = np.zeros(3); self.yaw = 0.; self.goal = None
        self.max_speed, self.tau = max_speed, tau
        self.phase, self.landed, self.error = 'ready', True, None
        self.minimum_clearance, self.envelope_violations, self.radius = float('inf'), 0, .35
        clock.vehicles.append(self)

    @property
    def latest(self):
        return {'position': self.position.tolist(), 'yaw': self.yaw, 'speed': float(np.linalg.norm(self.velocity)), 'goal': self.goal,
                'arrived': self.arrived(), 'time_s': self.clock.now(), 'contacts': 0}

    def arrived(self):
        return self.goal is not None and float(np.linalg.norm(self.position - np.array(self.goal[:3]))) < .08 and float(np.linalg.norm(self.velocity)) < .1

    def step(self, dt):
        if self.goal is None:
            return
        error = np.array(self.goal[:3]) - self.position
        desired = error/self.tau; n = float(np.linalg.norm(desired))
        if n > self.max_speed:
            desired *= self.max_speed/n
        self.velocity += (desired - self.velocity)*min(1., dt/self.tau)
        self.position = self.position + self.velocity*dt
        if self.position[2] < 0.:
            self.position[2] = 0.; self.velocity[2] = 0.
        self.yaw = float(self.goal[3])
        if self.position[2] > .1:
            c = clearance(self.map, self.position); self.minimum_clearance = min(self.minimum_clearance, c)
            self.envelope_violations += int(c < self.radius)

    async def start(self):
        pass

    async def takeoff(self):
        self.phase, self.landed = 'takeoff', False
        await self.settle([float(self.position[0]), float(self.position[1]), CRUISE_M, 0.], 20)

    async def settle(self, target, timeout=40):
        if len(target) != 4 or not all(math.isfinite(v) for v in target) or not 0 <= target[2] <= 1.8:
            raise ValueError('Invalid bounded flight setpoint')
        self.goal = [float(v) for v in target]; since = None; started = self.clock.now()
        while True:
            self.check()
            if self.arrived() and self.goal == [float(v) for v in target]:
                since = since or self.clock.now()
                if self.clock.now() - since >= .6:
                    return
            else:
                since = None
            if self.clock.now() - started > timeout:
                raise TimeoutError('Setpoint not reached in time')
            await self.clock.sleep(.1)

    async def land(self):
        self.phase = 'landing'; p = self.position
        self.goal = [float(p[0]), float(p[1]), 0., self.yaw]
        while self.position[2] >= .05 or float(np.linalg.norm(self.velocity)) >= .15:
            await self.clock.sleep(.1)
        self.phase, self.landed = 'landed', True

    def check(self):
        if self.error:
            raise RuntimeError(self.error)
        if self.envelope_violations:
            raise RuntimeError('Vehicle violated the collision/separation envelope')

    async def check_fresh(self):
        self.check()

    async def close(self):
        pass


class Flight:
    """One aircraft on the airspace: its plant, its estimator, its legs and what happened to it."""
    def __init__(self, aircraft, plant, home, legs, estimator, now, sleep, delay_s=0.):
        self.id, self.plant, self.home, self.legs, self.estimator, self.now, self.sleep, self.delay_s = aircraft, plant, tuple(home), legs, estimator, now, sleep, delay_s
        self.state, self.error, self.finished = 'ready', None, False
        self.goals_reached, self.holds, self.held_s, self.gave_way = 0, 0, 0., 0
        self.blackout = None   # (t0, t1): reports withheld, the flight holds

    def truth(self):
        return [float(v) for v in self.plant.latest['position']]

    def estimate(self):
        self.estimator.advance(self.now())
        p, yaw = self.estimator.estimate(np.array(self.truth()), float(self.plant.latest['yaw']))
        return [float(v) for v in p], float(yaw)

    def in_blackout(self, t):
        return self.blackout is not None and self.blackout[0] <= t < self.blackout[1]

    def airborne(self):
        return self.truth()[2] > .1


async def fly_leg(flight, airspace, target, goal):
    """Settle on target unless the airspace says hold meanwhile or the flight's own link is out: 'arrived' or 'held'."""
    task = asyncio.create_task(flight.plant.settle(target, 60))
    while not task.done():
        await flight.sleep(.2)
        now = flight.now()
        if flight.in_blackout(now) or airspace.advice(flight.id, goal, now)['action'] != 'proceed':
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            return 'held'
    await task
    return 'arrived'


def retreat_point(flight, away_from):
    """A point GIVE_WAY_M from here, away from the flight we block, or sideways if the room is in the way; None if nowhere is clear."""
    p = flight.truth(); dx, dy = p[0] - away_from[0], p[1] - away_from[1]; n = math.hypot(dx, dy)
    base = math.atan2(dy, dx) if n > 1e-6 else 0.
    for turn in (0., math.pi/2, -math.pi/2, 3*math.pi/4, -3*math.pi/4):
        a = base + turn; q = [p[0] + GIVE_WAY_M*math.cos(a), p[1] + GIVE_WAY_M*math.sin(a), CRUISE_M]
        if clearance(flight.plant.map, q) >= .6 and airspace_inside(flight, q):
            return q
    return None


def airspace_inside(flight, q):
    return flight.corridor_check(q) if hasattr(flight, 'corridor_check') else True


async def hold(flight, airspace, goal):
    """Stop where we are and stay until the airspace lets this leg go on and our own link is back; back off when asked."""
    flight.holds += 1; t0 = flight.now()
    p = flight.truth(); yaw = float(flight.plant.latest['yaw'])
    await flight.plant.settle([p[0], p[1], CRUISE_M, yaw], 30)
    while True:
        now = flight.now()
        if flight.in_blackout(now):
            await flight.sleep(.2); continue
        advice = airspace.advice(flight.id, goal, now)
        if advice['action'] == 'give_way':
            q = retreat_point(flight, advice['away_from'])
            if q is not None:
                flight.gave_way += 1
                await flight.plant.settle([q[0], q[1], CRUISE_M, yaw], 30)
            else:
                await flight.sleep(.2)
            continue
        if advice['action'] != 'hold':
            break
        await flight.sleep(.2)
    flight.held_s += flight.now() - t0


async def fly_mission(flight, airspace):
    try:
        await flight.sleep(flight.delay_s)
        await flight.plant.takeoff(); flight.state = 'flying'
        for goal in [*flight.legs, [flight.home[0], flight.home[1], CRUISE_M, 0.]]:
            while True:
                now = flight.now()
                if flight.in_blackout(now):
                    await hold(flight, airspace, goal); continue
                advice = airspace.advice(flight.id, goal, now)
                if advice['action'] == 'refuse':
                    raise RuntimeError(advice['reason'])
                if advice['action'] == 'hold':
                    await hold(flight, airspace, goal); continue
                try:
                    path = flight_path(airspace.map_for(flight.id, flight.plant.map), flight.truth(), goal)
                except ValueError:
                    # A holding aircraft blocks the route: those whose keep-out box lies across the straight line are asked to give way.
                    me = flight.truth()
                    for box in airspace.keep_out(flight.id):
                        if segment_distance((box['x'], box['y']), me, goal) < box['sx']/2 + .58:
                            airspace.blocked(flight.id, box['keep_out_for'], now)
                    await hold(flight, airspace, goal); await flight.sleep(.5); continue
                outcome = 'arrived'
                for wp in path:
                    outcome = await fly_leg(flight, airspace, [*wp, goal[3]], goal)
                    if outcome == 'held':
                        break
                if outcome == 'arrived':
                    flight.goals_reached += 1
                    break
        await flight.plant.land(); flight.finished = True; flight.state = 'landed'; airspace.landed(flight.id, flight.now())
    except Exception as exc:
        flight.error = f'{type(exc).__name__}: {exc}'; flight.state = 'failed'


async def report_positions(flight, airspace, stop):
    while not stop.is_set() and flight.state not in ('landed', 'failed'):
        now = flight.now()
        if not flight.in_blackout(now):
            p, yaw = flight.estimate()
            airspace.report(flight.id, p, yaw, now, state='flying' if flight.airborne() else 'ground')
        await flight.sleep(.1)


async def monitor(flights, airspace, stop, record, sleep, now):
    """Truth: pairwise separation in the air, speeds, and the others' reaction to the blackout."""
    blackout = next((f for f in flights if f.blackout), None); reacted = None
    while not stop.is_set():
        t = now(); positions = {f.id: f.truth() for f in flights}; speeds = {f.id: float(f.plant.latest['speed']) for f in flights}
        for i, a in enumerate(flights):
            for b in flights[i + 1:]:
                if positions[a.id][2] > .3 and positions[b.id][2] > .3 and abs(positions[a.id][2] - positions[b.id][2]) <= airspace.vertical_band:
                    d = math.hypot(positions[a.id][0] - positions[b.id][0], positions[a.id][1] - positions[b.id][1])
                    if d < record['min_separation_m']:
                        record.update(min_separation_m=d, min_separation_pair=[a.id, b.id], min_separation_t=t)
        if blackout and blackout.blackout[0] <= t and reacted is None:
            others = [f for f in flights if f is not blackout and f.state == 'flying']
            if all(speeds[f.id] < HOLD_SPEED for f in others):
                reacted = t - blackout.blackout[0]; record['blackout']['reaction_s'] = reacted
        if blackout and blackout.blackout[0] <= t < blackout.blackout[1]:
            others = [f for f in flights if f is not blackout and f.state == 'flying']
            record['blackout']['others_in_the_air'] = max(record['blackout'].get('others_in_the_air', 0), len(others))
        record['samples'] += 1
        await sleep(.1)


def scenario(seed):
    """Homes, legs, take-off delays, estimator errors and the blackout for one run."""
    rng = np.random.default_rng(seed)
    victim = AIRCRAFT[int(rng.integers(len(AIRCRAFT)))]
    return {'homes': dict(HOMES), 'legs': {k: [[FAR[k][0], FAR[k][1], CRUISE_M, 0.]] for k in AIRCRAFT},
            'delays': {k: float(rng.uniform(0., 3.)) for k in AIRCRAFT},
            'estimate_error': {k: (float(rng.normal(0, .04)), float(rng.normal(0, .04)), 0., float(rng.normal(0, .02))) for k in AIRCRAFT},
            'blackout': {'aircraft': victim, 't0': float(rng.uniform(8., 20.)), 'duration_s': BLACKOUT_S}}


def check_scene(scene):
    m = operator_map(scene)
    for k in AIRCRAFT:
        for p in (HOMES[k], FAR[k]):
            c = clearance(m, [p[0], p[1], CRUISE_M])
            if c < .6:
                raise ValueError(f'{k} point {p} has {c:.2f} m clearance in this room')


async def run_swarm(seed, scene, *, vehicle='kinematic', folder=None, assembly=None, speedup=None, airspace=None):
    """One run of three aircraft; returns the record for scoring."""
    check_scene(scene)
    plan = scenario(seed); airspace = airspace or Airspace()
    record = {'seed': seed, 'vehicle': vehicle, 'min_separation_m': float('inf'), 'min_separation_pair': None, 'min_separation_t': None,
              'blackout': {**plan['blackout'], 'reaction_s': None}, 'samples': 0}
    flights = []; plants = []; clock = None
    if vehicle == 'kinematic':
        clock = SimClock(speedup); now, sleep = clock.now, clock.sleep
        for i, k in enumerate(AIRCRAFT):
            plant = KinematicAircraft(scene, plan['homes'][k], clock); plants.append(plant)
            flights.append(Flight(k, plant, plan['homes'][k], plan['legs'][k], Estimator(offset=plan['estimate_error'][k], seed=seed + i), now, sleep, plan['delays'][k]))
    else:
        from adapters.rapier_drone import RapierDrone
        started = time.monotonic(); now = lambda: time.monotonic() - started; sleep = asyncio.sleep
        for i, k in enumerate(AIRCRAFT):
            own = copy.deepcopy(scene); own['home'] = list(plan['homes'][k])
            sub = folder/k; sub.mkdir(parents=True, exist_ok=True)
            plant = RapierDrone(assembly, own, sub, seed*10 + i); plants.append(plant)
            flights.append(Flight(k, plant, plan['homes'][k], plan['legs'][k], Estimator(offset=plan['estimate_error'][k], seed=seed + i), now, sleep, plan['delays'][k]))
    victim = next(f for f in flights if f.id == plan['blackout']['aircraft'])
    victim.blackout = (plan['blackout']['t0'], plan['blackout']['t0'] + BLACKOUT_S)
    stop = asyncio.Event(); tasks = []
    try:
        for p in plants:
            await p.start()
        if clock:
            tasks.append(asyncio.create_task(clock.run()))
        tasks += [asyncio.create_task(report_positions(f, airspace, stop)) for f in flights]
        tasks.append(asyncio.create_task(monitor(flights, airspace, stop, record, sleep, now)))
        missions = [asyncio.create_task(fly_mission(f, airspace)) for f in flights]
        deadline = now() + RUN_LIMIT_S
        while not all(m.done() for m in missions):
            if now() > deadline:
                for f in flights:
                    if not f.finished and not f.error:
                        f.error = 'run limit reached'
                for m in missions:
                    m.cancel()
                break
            await sleep(.2)
        await asyncio.gather(*missions, return_exceptions=True)
    finally:
        stop.set()
        if clock:
            clock.running = False
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for p in plants:
            try:
                await p.close()
            except Exception:
                pass
    record.update(duration_s=now(), flights={f.id: {'goals_reached': f.goals_reached, 'goals': len(f.legs) + 1, 'finished': f.finished, 'error': f.error,
                                                    'holds': f.holds, 'held_s': round(f.held_s, 2), 'gave_way': f.gave_way, 'final': f.truth(),
                                                    'home_error_m': math.hypot(f.truth()[0] - f.home[0], f.truth()[1] - f.home[1]),
                                                    'envelope_violations': getattr(f.plant, 'envelope_violations', 0),
                                                    'contacts': (f.plant.latest or {}).get('contacts', 0) if f.plant.latest else 0,
                                                    'minimum_clearance_m': getattr(f.plant, 'minimum_clearance', None)} for f in flights},
                  events=airspace.events[-60:], holds_total=sum(f.holds for f in flights))
    if record['min_separation_m'] == float('inf'):
        record['min_separation_m'] = None
    return record
