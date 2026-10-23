"""Full missions share the dashboard/API path. No truth is used for decisions."""
import asyncio
import copy
import hashlib
import json
import math
import statistics
from pathlib import Path
import time
import uuid

from adapters.rapier_drone import RapierDrone, ROOT
from app.mission_camera import MissionCamera
from app.components import Components, digest
from app.fleet import PLAN_PROMPT, PLAN_SCHEMA, parse_plan, rectangle
from app.localization import VISION_PROMPT, VISION_SCHEMA, parse_visual
from app.flight_localization import detection, triangulate, active_detail_views, planned_parallax, retained_observation
from app import identity
from app import mission_identity
from sim.flight_world import VIEWS, inspection_sightline_clear
from sim.hard_flight import cases
from sim.asset_world import build, verify_assets
from app.mission_views import next_views
from adapters.vision_reviewer import VisionReviewer


class MissionRuntime:
    def __init__(self, model, directory):
        self.model, self.directory = model, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.components = Components(self.directory.parent/'components.sqlite3')
        self.draft = self.run = self.task = self.vehicle = None
        self.lock = asyncio.Lock()
        self.planning = False
        self.intervention = None
        self.model_lock = asyncio.Lock()
        self.reviewer = None
        self.available = lambda: None
        paths = ['app/mission_runtime.py', 'adapters/rapier_drone.py', 'app/mission_camera.py',
                 'scripts/flight-camera.cjs', 'scripts/mission-physics.mjs', 'scripts/mission-transport.cjs', 'app/ui/mission-physics.mjs',
                 'app/ui/micro-physics.mjs', 'app/ui/flight-lab.js', 'app/identity.py', 'app/localization.py',
                 'app/flight_localization.py', 'app/mission_views.py', 'app/mission_navigation.py', 'app/mission_identity.py', 'adapters/vision_reviewer.py',
                 'scripts/vision_reviewer_worker.py', 'sim/asset_world.py', 'sim/hard_flight.py', 'config/native-hard-v1.json',
                 'sim/flight_world.py', 'adapters/llama.py', 'app/fleet.py', 'app/components.py',
                 'app/mission_api.py', 'app/recon_server.py']
        self.source_hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}

    @property
    def busy(self):
        return self.planning or bool(self.task and not self.task.done())

    def snapshot(self):
        return {'mode': 'service-owned-rapier-mission', 'busy': self.busy, 'draft': self.draft,
                'model': self.model.status() if hasattr(self.model, 'status') else None,
                'mission': self.run, 'vehicle': self.vehicle.latest if self.vehicle else None,
                'map': self.vehicle.map if self.vehicle else None,
                'physical_enabled': False, 'dashboard_required': False,
                'cases': [{'id': c['id'], 'condition': c['condition']} for c in cases()],
                'assemblies': [{'reference': f"{c['content']['id']}@{c['revision']}", 'name': c['content']['name']}
                               for c in self.components.list('configuration')]}

    async def plan(self, body):
        async with self.lock:
            self.available()
            if self.busy:
                raise RuntimeError('Finish the active mission first')
            if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h for p, h in self.source_hashes.items()):
                raise RuntimeError('Mission code changed; restart the service before testing')
            instruction = body.get('instruction')
            if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 600:
                raise ValueError('Write a mission brief of 1–600 characters')
            area = rectangle(body.get('area', [0, 0, 12, 10]))
            case = next((copy.deepcopy(c) for c in cases() if c['id'] == body.get('case')), None)
            if not case:
                raise ValueError('Select a registered environment')
            assembly = self.components.assemble(body.get('assembly', 'scout-110-power-v2'))
            self.planning = True
            self.draft = None
            try:
                intent = parse_plan(await self.model.text(PLAN_PROMPT+json.dumps(instruction), PLAN_SCHEMA))
                # The current qualified task has a precise target specification.
                # Do not silently relabel another object request as this task.
                supported = (intent['objective'] == 'inventory'
                             and 'fire extinguisher' in intent['focus'].casefold()
                             and 'red' in instruction.casefold())
                points = [p for p in VIEWS if area[0] <= p[0] <= area[2] and area[1] <= p[1] <= area[3]]
                if not points:
                    raise ValueError('Area contains no inspection stations')
                self.draft = {'id': uuid.uuid4().hex, 'created_at': time.time(), 'instruction': instruction,
                    'area': area, 'case': case['id'], 'assembly': assembly, 'views': points,
                    'intent': intent, 'dispatchable': supported is True and intent['objective'] != 'unsupported',
                    'backend': 'Rapier component dynamics + service-owned Three.js camera + local Qwen and Florence',
                    'vision_policy': mission_identity.VERSION+'; two-view neutral Qwen crop identity AND independent Florence identity; geometry-guided acquisition',
                    'note': 'One aircraft. Known operator floor plan; ideal external pose. Area bounds inspection stations, not transit. Hardware remains unqualified.'}
                return self.draft
            finally:
                self.planning = False

    async def launch(self, identity):
        async with self.lock:
            self.available()
            if self.busy or not self.draft or self.draft['id'] != identity or not self.draft['dispatchable'] or time.time()-self.draft['created_at'] > 600:
                raise ValueError('Generate a fresh supported mission plan first')
            draft, self.draft = self.draft, None
            episode = uuid.uuid4().hex
            self.run = {'id': episode, 'state': 'starting', 'plan': draft, 'started_at': time.time(),
                'steps': [], 'outcome': 'unresolved', 'location': None, 'error': None,
                'visited': [], 'landed': False, 'report': f'/api/mission/runs/{episode}/report.html'}
            self.intervention = None
            self.task = asyncio.create_task(self.execute(draft))
            return self.snapshot()

    async def stop(self, return_home=False):
        if self.task and not self.task.done():
            self.intervention = 'return' if return_home else 'land'
            if self.vehicle:
                self.vehicle.interrupt = 'Operator requested '+self.intervention
            self.run['state'] = 'returning' if return_home else 'landing'
        return self.snapshot()

    def persist(self, folder):
        data = json.dumps(self.run, indent=2, allow_nan=False)
        temp = folder/'summary.tmp'
        temp.write_text(data)
        temp.replace(folder/'summary.json')

    async def execute(self, draft):
        folder = self.directory/self.run['id']
        folder.mkdir()
        camera, started = MissionCamera(), time.monotonic()
        case = next(c for c in cases() if c['id'] == draft['case'])
        scene = build(case)
        # Preserve benchmark optics, degradation and latency. The override is
        # explicit; the assembly's unmeasured camera defaults remain recorded.
        self.run['camera_profile'] = {'source': 'unchanged native-hard-v1 / Poly Haven benchmark',
            'benchmark': scene['camera'], 'component_defaults': draft['assembly']['components']['avionics']['content']['parameters']}
        (folder/'scene.json').write_text(json.dumps(scene, indent=2))
        self.run['source_hashes'] = self.source_hashes
        self.run['model'] = self.model.status() if hasattr(self.model, 'status') else {'name': 'test double'}
        self.run['scene_sha256'] = digest(scene)
        self.run['limits'] = {'mission_deadline_s': 300, 'localization_tolerance_m': .75, 'physical_enabled': False,
                              'pose': 'ideal external reference', 'map': 'operator-provided geometry; identities removed from navigation',
                              'planning_clearance_m': .58, 'inspection_clearance_m': .61, 'flight_envelope_m': .35,
                              'clearance_metric': 'three-dimensional obstacle distance; controlled floor contact excluded'}
        self.vehicle = RapierDrone(draft['assembly'], scene, folder, case['seed'])
        flight = self.vehicle
        self.persist(folder)
        try:
            verify_assets()
            async with asyncio.timeout(300):
                if self.reviewer is None:
                    self.reviewer = VisionReviewer('florence', folder)
                    try:
                        await self.reviewer.start()
                    except Exception:
                        await self.reviewer.close()
                        self.reviewer = None
                        raise
                self.run['reviewer'] = self.reviewer.metadata
                await flight.start()
                await camera.open(flight, folder)
                self.run['state'] = 'running'
                await flight.takeoff()
                views = draft['views']
                for index, base in enumerate(views):
                    if self.intervention:
                        raise RuntimeError('Operator requested '+self.intervention)
                    first = None
                    first_supported = False
                    pose = base
                    inspected_poses = []
                    candidate_locations = []
                    for attempt in range(5):
                        flight.message = f'Inspecting area {index+1}/{len(views)}, observation {attempt+1}'
                        await flight.fly(pose)
                        inspected_poses.append(list(pose))
                        if index not in self.run['visited']:
                            self.run['visited'].append(index)
                        frame = await camera.call(op='capture')
                        image = (folder/frame['image']).read_bytes()
                        # Policy input explicitly strips renderer truth and scene IDs.
                        metadata = {'estimated': frame['metadata']['estimated'], 'sensor': frame['metadata']['sensor'],
                                    'sequence': frame['metadata']['sequence']}
                        began = time.monotonic()
                        visual = parse_visual(await self.model.image(image, VISION_PROMPT, VISION_SCHEMA, timeout=12, max_tokens=180))
                        parts = detail = None
                        supported = False
                        if visual['status'] == 'present':
                            crop, crop_meta = identity.crop_candidate(image, visual['bbox'])
                            name = 'identity-'+frame['image']
                            (folder/name).write_bytes(crop)
                            if crop_meta['adequate_pixels']:
                                parts = mission_identity.parse(await self.model.image(crop, mission_identity.PROMPT, mission_identity.SCHEMA, timeout=12, max_tokens=180))
                            detail = {'image': name, 'crop': crop_meta, 'parts': parts, 'supported': supported}
                            if crop_meta['adequate_pixels']:
                                review = await self.reviewer.review(folder/name)
                                supported = mission_identity.supported(parts, review)
                                detail.update(independent_review=review, supported=supported)
                        await flight.check_fresh()
                        current = detection(metadata['estimated'], visual['bbox'], f'area-{index}-view-{attempt}') if visual['status'] == 'present' else None
                        location = triangulate(first, current) if first and current else None
                        if location:
                            location['method'] = 'Two model-predicted image boxes, nominal camera intrinsics and ideal external pose/full attitude; Rapier simulation'
                        step = {'view': f'{index}/{attempt}', 'image': frame['image'], 'image_sha256': hashlib.sha256(image).hexdigest(),
                            'frame': metadata, 'visual': visual, 'identity': detail, 'location': location, 'latency_s': time.monotonic()-began}
                        self.run['steps'].append(step)
                        if location and first_supported and supported:
                            self.run.update(outcome='found', location=location)
                            step['action'] = 'found'
                            self.persist(folder)
                            break
                        candidate = None
                        if current and attempt == 0:
                            p = [base[0]-.8*math.sin(base[3]), base[1]+.8*math.cos(base[3]), *base[2:]]
                            # A nominal range is only an acquisition hint, never
                            # a localized claim. Centre the candidate while moving.
                            aim = [o+2.5*r for o, r in zip(current['origin'], current['ray'])]
                            p[3] = math.atan2(aim[1]-p[1], aim[0]-p[0])
                            if visual['bbox'][3] >= 990:
                                p[2] = max(.9, p[2]-.3)
                            elif visual['bbox'][1] <= 10:
                                p[2] = min(1.8, p[2]+.3)
                            if flight.can_inspect(p):
                                candidate = p
                        elif current and location and attempt < 4:
                            reference = retained_observation(first, first_supported, current, supported)
                            candidate_locations.append(location['xyz_m'])
                            # Occlusion moves predicted box centres. A robust
                            # acquisition hint reduces viewpoint jumps; the
                            # final claim still uses the actual verified rays.
                            hint = {'xyz_m': [statistics.median(p[i] for p in candidate_locations) for i in range(3)]}
                            plans = await asyncio.to_thread(next_views, flight.map, metadata['estimated']['position'], hint, reference, inspected_poses, supported or first_supported)
                            if plans:
                                candidate = plans[0]['pose']
                                step['view_plan'] = plans[0]
                            for elevated in (() if candidate else (True, False)):
                                for p in active_detail_views(metadata['estimated']['position'], location, elevated=elevated):
                                    origin = [p[0]+.12*math.cos(p[3]), p[1]+.12*math.sin(p[3]), p[2]+.02]
                                    if flight.can_inspect(p) and planned_parallax(reference, p, location) and inspection_sightline_clear(flight.map, origin, location['xyz_m']):
                                        candidate = p
                                        break
                                if candidate:
                                    break
                        step['action'] = 'confirm' if candidate else 'scan'
                        self.persist(folder)
                        if not candidate:
                            break
                        if supported or not first_supported:
                            first, first_supported = current, supported
                        pose = candidate
                    if self.run['outcome'] == 'found':
                        break
                self.run['state'] = 'returning'
                await flight.return_land()
                self.run['state'] = 'finalizing'
        except (Exception, asyncio.CancelledError) as exc:
            self.run.update(state='cancelled' if self.intervention else 'failed', error=f'{type(exc).__name__}: {exc}')
            # The mission never becomes a pass merely because cleanup landed.
            flight.interrupt = None
            if flight.latest:
                try:
                    if flight.error:
                        await flight.watchdog_land()
                    elif self.intervention == 'return':
                        await flight.return_land()
                    else:
                        await flight.land()
                except Exception as cleanup:
                    self.run['recovery_error'] = str(cleanup)
                    if not flight.landed:
                        try:
                            await flight.watchdog_land()
                        except Exception as fallback:
                            self.run['recovery_error'] += '; watchdog landing: '+str(fallback)
        finally:
            try:
                await camera.close()
                if self.run['state'] == 'finalizing':
                    self.run['state'] = 'complete'
            except Exception as exc:
                self.run.update(state='failed', error='Camera finalization: '+str(exc))
            self.run.update(landed=flight.landed, flight=flight.metrics(), wall_time_s=time.monotonic()-started,
                            camera=getattr(camera, 'stats', None), dashboard_required=False)
            await flight.close()
            self.persist(folder)

    async def close(self):
        if self.task and not self.task.done():
            await self.stop()
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 30)
            except TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
        if self.reviewer:
            await self.reviewer.close()
            self.reviewer = None
