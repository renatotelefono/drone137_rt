"""Local mission dispatch. One leased airspace, two isolated virtual aircraft.

The selected rectangle bounds inspection viewpoints, not transit. Queued aircraft
are docked outside the simulated volume. No concurrent flight or physical I/O.
"""
import asyncio
import copy
import json
import math
import time
import uuid

from app.perception import object_from_json
from app.recon import ACTIVE, Recon
from app.recorder import RunRecorder
from sim.recon_world import world
from app.airframes import Airframes

DRONES = {'drone-01': 'Scout 01', 'drone-02': 'Scout 02'}
OBJECTIVES = ('inventory', 'passage', 'changes', 'unsupported')
PLAN_SCHEMA = {'type': 'object', 'properties': {
    'objective': {'type': 'string', 'enum': list(OBJECTIVES)},
    'focus': {'type': 'string', 'maxLength': 120},
    'summary': {'type': 'string', 'maxLength': 200}},
    'required': ['objective', 'focus', 'summary'], 'additionalProperties': False}
PLAN_PROMPT = (
    'Classify this operator request for an indoor virtual camera inspection. '
    'Return JSON: objective, focus (short visual topic), summary (one short sentence). '
    'Choose objective using these rules:\n'
    '- unsupported: physical flight, outdoor locations, delivery, following people, measurements or arbitrary flight coordinates.\n'
    '- changes: comparing views with an earlier inspection or finding what changed.\n'
    '- passage: specifically checking whether a doorway or passage is obstructed.\n'
    '- inventory: general patrol, surveying objects, or looking for particular objects. '
    'A general patrol that also checks obstructions is inventory.\n'
    'Examples:\n'
    '"Check the doorway for anything blocking it" => objective "passage".\n'
    '"Describe the bottles and tools" => objective "inventory".\n'
    '"What changed since last time?" => objective "changes".\n'
    '"Deliver a package" => objective "unsupported".\n'
    'The dashboard supplies the area and aircraft; do not invent routes or capabilities. '
    'Keep the entire JSON response under 60 words.\nOperator request: ')


def rectangle(value):
    if (not isinstance(value, list) or len(value) != 4 or
        any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError('Select a finite inspection rectangle [west, south, east, north]')
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= 12 and 0 <= y0 < y1 <= 10 and x1-x0 >= .5 and y1-y0 >= .5):
        raise ValueError('Inspection area must be inside the 12 × 10 m site and at least 0.5 m wide/deep')
    return list(value)


def in_area(point, area):
    return area[0] <= point[0] <= area[2] and area[1] <= point[1] <= area[3]


def parse_plan(raw):
    value = object_from_json(raw)
    if (set(value) != {'objective', 'focus', 'summary'} or value['objective'] not in OBJECTIVES
        or not isinstance(value['focus'], str) or len(value['focus']) > 120
        or not isinstance(value['summary'], str) or not 1 <= len(value['summary']) <= 200):
        raise ValueError('Model returned an invalid mission brief')
    return value


class Fleet:
    def __init__(self, lab):
        self.lab, self.manager, self.runs = lab, lab.manager, lab.runs
        self.drones = {key: Recon(self.manager, self.runs) for key in DRONES}
        self.scene = world(619, 'realism')
        for drone in self.drones.values():
            drone.configure(619, 'realism')
        self.generation = uuid.uuid4().hex
        self.leases = {}
        self.draft = self.mission = self.recorder = None
        self.planning = False
        self.reset_required = False
        self.error = None
        self.task = None
        self.lock = asyncio.Lock()
        self.airframes = Airframes(self.runs.parent/'airframes.sqlite3')

    @property
    def busy(self):
        return self.planning or bool(self.mission and self.mission['state'] in ('queued', 'running', 'returning', 'stopping'))

    def available(self):
        if self.busy:
            raise RuntimeError('Finish or stop the fleet mission first')
        if self.lab.state in ACTIVE | {'paused'}:
            raise RuntimeError('End the Recon lab mission first; it shares the local model')
        if self.reset_required:
            raise RuntimeError('Reset the virtual site after a stopped or failed flight before dispatching again')

    def configure(self, seed, scenario='realism', variant='baseline', condition='nominal'):
        if self.busy or self.lab.state in ACTIVE | {'paused'}:
            raise RuntimeError('Stop all missions before resetting the virtual site')
        if type(seed) is not int or not 0 <= seed <= 2**31-1:
            raise ValueError('Invalid environment seed')
        scene = world(seed, scenario, variant, condition)
        if not scene['checkpoints']:
            raise ValueError('Select an environment with authored inspection viewpoints')
        self.scene = scene
        for drone in self.drones.values():
            if drone.task and not drone.task.done():
                drone.task.cancel()
        self.drones = {key: Recon(self.manager, self.runs) for key in DRONES}
        for drone in self.drones.values():
            drone.configure(seed, scenario, variant, condition)
        self.generation = uuid.uuid4().hex
        self.draft, self.mission, self.recorder = None, None, None
        self.leases.clear()
        self.reset_required, self.error = False, None

    async def plan(self, body):
        self.available()
        async with self.lock:
            return await self._plan(body)

    async def _plan(self, body):
        self.available()
        area = rectangle(body.get('area'))
        instruction, selected = body.get('instruction'), body.get('drones')
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 600:
            raise ValueError('Write a mission brief of 1–600 characters')
        if (not isinstance(selected, list) or not selected or len(selected) > len(DRONES)
            or any(not isinstance(d, str) or d not in DRONES for d in selected) or len(set(selected)) != len(selected)):
            raise ValueError('Select one or two available virtual aircraft')
        points = [c for c in self.scene['checkpoints'] if in_area(c['position'], area)]
        if not points:
            raise ValueError('No inspection viewpoints inside this area; expand the selection')
        if not self.manager.ready or self.manager.status()['busy']:
            raise RuntimeError('Start the local model and wait until it is ready')
        self.planning = True
        self.draft = None
        try:
            prompt = PLAN_PROMPT+json.dumps(instruction.strip())
            intent = parse_plan(await self.manager.text(prompt, PLAN_SCHEMA))
            if intent['objective'] == 'passage':
                points = [c for c in points if c.get('inspection_task') == 'passage' or c['id'] == 'passage']
            assignments = []
            if intent['objective'] != 'unsupported' and points:
                # Contiguous chunks preserve authored viewpoint order and avoid
                # making every aircraft transit both ends of the site.
                count = min(len(selected), len(points))
                for index, drone_id in enumerate(selected[:count]):
                    chunk = points[index*len(points)//count:(index+1)*len(points)//count]
                    assignments.append({'drone_id': drone_id, 'points': [c['id'] for c in chunk]})
            self.draft = {'id': uuid.uuid4().hex, 'generation': self.generation,
                'instruction': instruction.strip(), 'area': area, 'selected_drones': selected,
                **intent, 'assignments': assignments, 'real_inference': True,
                'dispatchable': bool(assignments), 'created_at': time.time(),
                'hardware':{key:self.airframes.assigned(key) for key in selected},
                'hardware_application':'Pinned assignments for native comparison; this dashboard flight remains kinematic, without airframe dynamics.',
                'note': ('Viewpoints are inside the selected area. Transit and return may leave it. '
                         'One aircraft flies at a time; all others remain docked outside the site. '
                         'A change mission requires a matching completed baseline to assess changes.')}
            if not points and intent['objective'] == 'passage':
                self.draft['summary'] = 'This area has no authored doorway inspection viewpoint. Expand the area.'
            return copy.deepcopy(self.draft)
        finally:
            self.planning = False

    def heartbeat(self, drone_id, body):
        client, session = body.get('client'), body.get('session')
        if any(not isinstance(v, str) or not 1 <= len(v) <= 80 for v in (client, session)):
            raise ValueError('A browser and camera session are required')
        drone = self.drones[drone_id]
        old = self.leases.get(drone_id)
        if drone.state in ACTIVE | {'paused'} and drone.client != client:
            raise RuntimeError('This aircraft camera belongs to another browser; stop the flight before taking control')
        if self.busy and self.mission and self.mission['session'] != session:
            raise RuntimeError('Mission camera belongs to another dashboard session')
        if old and old['client'] != client and time.monotonic()-old['time'] < 3:
            raise RuntimeError('Camera is already open in another dashboard; close that dashboard first')
        self.leases[drone_id] = {'client': client, 'session': session, 'time': time.monotonic(),
                               'ready': body.get('ready') is True and body.get('generation') == self.generation}

    def camera_ready(self, drone_id, session=None):
        lease = self.leases.get(drone_id)
        return bool(lease and lease['ready'] and time.monotonic()-lease['time'] < 2
                    and (session is None or lease['session'] == session))

    async def launch(self, draft_id, session):
        async with self.lock:
            self.available()
            if (not self.draft or draft_id != self.draft['id'] or self.draft['generation'] != self.generation
                or not self.draft['dispatchable'] or time.time()-self.draft['created_at'] > 600):
                raise ValueError('Generate and review a fresh mission plan first')
            if not isinstance(session, str) or not 1 <= len(session) <= 80:
                raise ValueError('Dashboard session required')
            if not self.manager.ready or self.manager.status()['busy']:
                raise RuntimeError('Local model must be ready before dispatch')
            if any(not self.camera_ready(a['drone_id'], session) for a in self.draft['assignments']):
                raise RuntimeError('Wait for every assigned camera to be ready in this dashboard')
            episode = uuid.uuid4().hex
            self.airframes.freeze(episode,list(self.draft['hardware'].values()),self.runs/episode)
            recorder = RunRecorder(self.runs, episode, 1024**3, {'mode': 'virtual-fleet-mission',
                'physical_transport': False, 'real_flight_dynamics': False, 'concurrent_flight': False,
                'scene': {k: self.scene[k] for k in ('scenario', 'seed', 'variant', 'condition')},
                'plan': copy.deepcopy(self.draft)})
            self.recorder = recorder
            self.mission = {'id': episode, 'session': session, 'state': 'queued', 'started_at': time.time(),
                'plan': copy.deepcopy(self.draft), 'reason': 'Waiting for the first aircraft camera',
                'jobs': [{**a, 'state': 'queued', 'episode': None} for a in self.draft['assignments']]}
            self.draft = None
            self.persist()
            return self.snapshot()

    def persist(self):
        if self.recorder and self.mission:
            self.recorder.finish(**{k: v for k, v in self.mission.items() if k != 'session'})

    def cancel_queue(self, reason):
        for job in self.mission['jobs']:
            if job['state'] == 'queued':
                job.update(state='cancelled', reason=reason)

    async def stop(self, return_home=False):
        async with self.lock:
            if not self.mission or self.mission['state'] not in ('queued', 'running', 'returning', 'stopping'):
                return
            self.cancel_queue('Operator cancelled queued flights')
            self.mission.update(state='returning' if return_home else 'stopping',
                                reason='Operator requested return' if return_home else 'Operator stopped all flights')
            for drone in self.drones.values():
                if drone.state in ACTIVE:
                    if return_home:
                        drone.return_home()
                    else:
                        await drone.land()
                        self.reset_required = True
            self.persist()

    async def tick(self):
        async with self.lock:
            if not self.mission or not self.busy or self.planning:
                return
            jobs = self.mission['jobs']
            current = next((j for j in jobs if j['state'] in ('running', 'finalizing')), None)
            if current:
                drone = self.drones[current['drone_id']]
                if drone.state in ACTIVE:
                    return
                # Failed/stopped aircraft may still occupy the route: never
                # dispatch the next aircraft, even if video finalizes normally.
                if drone.state != 'complete':
                    self.cancel_queue('Previous aircraft did not finish its assigned inspection')
                    self.reset_required |= math.dist(drone.pose[:2], [1.25, 1.25]) >= .1 or drone.state in ('paused', 'failed', 'ended')
                if current['state'] != 'finalizing':
                    current.update(state='finalizing', finalizing_since=time.monotonic())
                    self.persist()
                if not drone.video_complete and time.monotonic()-current['finalizing_since'] < 10:
                    return
                current.update(state=drone.state if drone.video_complete else 'failed',
                    reason=drone.reason if drone.video_complete else 'Camera evidence did not finalize',
                    observations=len(drone.observations), distance_m=drone.distance,
                    video_complete=drone.video_complete, report_page=f'/reports/{drone.episode}/report.html')
                current.pop('finalizing_since', None)
                if current['state'] != 'complete':
                    self.cancel_queue('Previous flight requires review')
                self.persist()
            queued = next((j for j in jobs if j['state'] == 'queued'), None)
            if queued:
                key = queued['drone_id']
                if not self.camera_ready(key, self.mission['session']):
                    self.cancel_queue('Dashboard camera connection lost; dispatch cancelled')
                    self.mission.update(state='failed', reason='An assigned camera disconnected before dispatch')
                    self.persist()
                    return
                drone = self.drones[key]
                context = {k: self.mission['plan'][k] for k in ('instruction', 'area', 'objective', 'focus')}
                context.update(fleet_mission=self.mission['id'], drone_id=key,hardware=self.mission['plan']['hardware'][key])
                try:
                    await drone.start('qwen', self.leases[key]['client'], 'patrol',
                        compare=context['objective'] == 'changes', checkpoint_ids=queued['points'], task_context=context)
                except Exception as exc:
                    queued.update(state='failed', reason=str(exc))
                    self.cancel_queue('Dispatch failed')
                    self.mission.update(state='failed', reason=str(exc))
                else:
                    queued.update(state='running', episode=drone.episode)
                    self.mission.update(state='running', reason=f'{DRONES[key]} has the shared airspace')
                self.persist()
            elif all(j['state'] not in ('running', 'finalizing') for j in jobs):
                success = all(j['state'] == 'complete' for j in jobs)
                self.mission.update(state='complete' if success else 'needs_review',
                    reason='All assigned viewpoints inspected; aircraft returned and videos saved' if success else 'Mission stopped or incomplete; review each aircraft report',
                    completed_at=time.time())
                self.persist()

    async def run(self):
        try:
            while True:
                try:
                    await self.tick()
                except Exception as exc:
                    self.error = str(exc)
                    if self.mission:
                        self.cancel_queue('Dispatcher error')
                        self.mission.update(state='failed', reason=str(exc))
                    self.reset_required = True
                    for drone in self.drones.values():
                        await drone.land()
                await asyncio.sleep(.2)
        except asyncio.CancelledError:
            pass

    def drone_snapshot(self, drone_id):
        return {**self.drones[drone_id].snapshot(), 'generation': self.generation, 'drone_id': drone_id}

    def snapshot(self):
        drones = []
        for key, name in DRONES.items():
            snapshot = self.drones[key].snapshot()
            drones.append({'id': key, 'name': name, 'camera_ready': self.camera_ready(key),
                'hardware':self.airframes.assigned(key),
                **{k: snapshot[k] for k in ('state', 'pose', 'speed', 'distance_m', 'observations', 'episode', 'reason', 'video_complete', 'report_page')}})
        return {'mode': 'virtual-fleet', 'scene': self.scene, 'generation': self.generation,
            'busy': self.busy, 'planning': self.planning, 'reset_required': self.reset_required,
            'error': self.error, 'model': self.manager.status(), 'draft': self.draft, 'mission': self.mission,
            'drones': drones}

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.stop()
        for drone in self.drones.values():
            await drone.close()
        if self.mission and self.busy:
            self.mission.update(state='interrupted', reason='Application closed; no automatic resume')
            for job in self.mission['jobs']:
                if job['state'] in ('running', 'finalizing'):
                    job['state'] = 'interrupted'
            self.persist()
