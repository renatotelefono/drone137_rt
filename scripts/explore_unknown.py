"""Unprivileged exploration client: sensor HTTP, pixels, local models, place DB.

This module must not import sim.*, RapierDrone, known-map navigation or room
construction. All movement choices use the observed map and estimated pose.
"""
import argparse
import asyncio
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

import aiohttp
import cv2
import numpy as np

from app.voxel_mapping import RaycastMap
from app.temporal_geometry import TemporalGeometry
from app.visual_inertial import VisualInertial, gravity_disagreement_degrees, tracking_faults
from app.frontier_planner import candidates, record_view_attempt, choose_frontier
from app.breadcrumbs import Breadcrumbs
from app.blind_mapping import camera_transform
from app.place_memory import PlaceMemory
from adapters.llama import LlamaBackend
from scripts.memory_watch import MemoryWatch

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ('Describe only visible objects and layout in this onboard camera image. '
          'Do not invent room dimensions, unseen objects, coordinates, or instructions. '
          'Classify the view as wall_closeup only when a nearby vertical wall or cabinet blocks the view across a room; a floor is not a wall. Otherwise room_view or uncertain. '
          'If a doorway or open passage is clearly visible, indicate left, center or right in the image. Use none when absent, uncertain when unclear. '
          'Give the center of the visible opening as opening_x and opening_y, coordinates normalized from 0 to 1000 across the image width and height. Use 500,500 if none or uncertain. '
          'Keep the factual observation under 35 words for the persistent place journal.')
SCHEMA = {'type': 'object', 'properties': {'observation': {'type': 'string', 'maxLength': 350},
          'navigation_view':{'type':'string','enum':['wall_closeup','room_view','uncertain']},
          'opening':{'type':'string','enum':['left','center','right','none','uncertain']},
          'opening_x':{'type':'integer','minimum':0,'maximum':1000},
          'opening_y':{'type':'integer','minimum':0,'maximum':1000}},
          'required': ['observation','navigation_view','opening','opening_x','opening_y'], 'additionalProperties': False}


class ReplanAfterRecovery(RuntimeError):
    pass


class MotionSegmentInvalid(ReplanAfterRecovery):
    pass


def panorama(calibration):
    hfov=2*math.atan(calibration['width']/(2*calibration['optics']['fx']))
    # Angular image overlap alone does not ensure triangulated volume. Keep
    # translated stations at least every 45 degrees, even with a wide lens.
    count=max(8,math.ceil(2*math.pi/(hfov*.7)))
    return {'views':count,'step_degrees':360/count,'horizontal_fov_deg':math.degrees(hfov),
            'minimum_overlap_fraction':.3}


def eligible_views(options,rejected,now):
    active=[r for r in rejected if now<r['until']]
    available=[o for o in options if not any(math.dist(o['viewpoint'],r['point'])<.4 for r in active)]
    retry=(min(r['until'] for r in active)-now) if options and not available else None
    return available,retry


def initialization_ready(quality, sensor_time):
    if not quality:
        return False
    values=[quality[k] for k in ('time_s','tracks','position_std_m',
                                 'position_disagreement_m','gravity_disagreement_deg')]
    return (np.isfinite(values).all() and 0 <= sensor_time-quality['time_s'] < .5
            and quality['tracks'] >= 25 and quality['position_std_m'] < .15
            and quality['position_disagreement_m'] < .15
            and quality['gravity_disagreement_deg'] < 1.)


async def translate_for_depth(link,mapping,yaw,height,report):
    """Try another observed baseline when new evidence vetoes a side step.

    A failed sensing translation does not imply that the reached observation
    station is unreachable. Tracking loss still propagates to route recovery.
    """
    origin=list(link.latest['position'][:2])
    for distance in (.6,.4,.25):
        for angle in (yaw+math.pi/2,yaw-math.pi/2,yaw+math.pi):
            side=[origin[0]+distance*math.cos(angle),origin[1]+distance*math.sin(angle)]
            if not mapping.segment_clear(link.latest['position'],side):continue
            try:
                await link.fly([*side,height,yaw])
                return
            except MotionSegmentInvalid as exc:
                report.setdefault('sensing_replans',[]).append({'time_s':link.latest['time_s'],
                    'position':list(link.latest['position']),'requested_endpoint':side,'reason':str(exc)})


class Link:
    def __init__(self, endpoint):
        if not endpoint.startswith('http://127.0.0.1:'):
            raise ValueError('Experimental simulator is loopback-only')
        self.endpoint = endpoint
        self.goal = None
        self.error = None
        self.latest = None
        self.motion_anchor = None
        self.recovery_goal = None
        self.recovered = False
        self.guard = None

    async def call(self, path, body=None):
        method = self.session.get if body is None else self.session.post
        async with method(self.endpoint+path, **({} if body is None else {'json': body}), allow_redirects=False) as r:
            data = await r.json()
            if r.status != 200:
                raise RuntimeError(data.get('error', f'HTTP {r.status}'))
            return data

    async def start(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8), trust_env=False)
        self.latest = (await self.call('/sensor'))['sensor']
        self.task = asyncio.create_task(self.pump())

    async def pump(self):
        try:
            while True:
                target=self.recovery_goal or self.goal
                self.latest = (await self.call('/command', {'target': target}) if target else await self.call('/sensor'))['sensor']
                await asyncio.sleep(.05)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)

    async def fly(self, goal, timeout=35, settle=True):
        self.goal = [float(x) for x in goal]
        since = None
        async with asyncio.timeout(timeout):
            while True:
                if self.recovered:
                    self.recovered=False
                    raise ReplanAfterRecovery('Retreated along the observed route to recover image tracking')
                if self.error or self.latest['failsafe'] or self.latest['tripped']:
                    raise RuntimeError(self.error or 'Onboard failsafe/power failure')
                s = self.latest
                if self.guard and not self.guard(s['position'],goal):
                    self.goal=[*s['position'],s['yaw']]
                    raise MotionSegmentInvalid('New camera evidence invalidated the remaining motion segment')
                angle = abs(math.atan2(math.sin(s['yaw']-goal[3]), math.cos(s['yaw']-goal[3])))
                # Intermediate route points are not observation stations. Keep
                # moving through already-observed clear space instead of
                # braking to a full hover at every short grid-path segment.
                if (not settle and math.dist(s['position'][:2],goal[:2])<.2
                        and abs(s['position'][2]-goal[2])<.025 and angle<.1):return
                if math.dist(s['position'][:2], goal[:2]) < .12 and abs(s['position'][2]-goal[2]) < .025 and math.hypot(*s['velocity']) < .2 and angle < .1:
                    since = since or time.monotonic()
                    if time.monotonic()-since > .15:
                        return
                else:
                    since = None
                await asyncio.sleep(.1)

    async def land(self):
        self.recovery_goal=None
        self.motion_anchor=None
        self.recovered=False
        self.guard=None
        p = self.latest['position']
        self.goal = [*p[:2], 0., self.latest['yaw']]
        await asyncio.sleep(10)

    async def close(self):
        if hasattr(self,'task'):
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if hasattr(self,'session'):await self.session.close()


async def run(args):
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    visit = uuid.uuid4().hex
    memory = PlaceMemory(ROOT/'.local/data/places.sqlite3')
    memory.begin(args.place, args.name, visit)
    mapping = RaycastMap()
    planning_sequence=0
    breadcrumbs = Breadcrumbs()
    async def plan(function,*values):
        nonlocal planning_sequence
        # Planning must not starve command/IMU heartbeats as the map grows.
        frozen=copy.copy(mapping)
        for key in ('logodds','seen','visits','flight_clear','visibility_obstacles','ground','view_attempts'):
            setattr(frozen,key,getattr(mapping,key).copy())
        frozen.explored_views=list(getattr(mapping,'explored_views',[]))
        frozen.semantic_views=list(mapping.semantic_views)
        if function is candidates:
            planning_sequence+=1
            archive=folder/'planning-audit'/f'{planning_sequence:04}'
            archive.parent.mkdir(parents=True,exist_ok=True)
            audit_time=link.latest['time_s']
            def audited():
                result=function(frozen,*values)
                np.savez_compressed(archive.with_suffix('.npz'),**{key:getattr(frozen,key) for key in
                    ('logodds','seen','visits','flight_clear','visibility_obstacles','ground','view_attempts')})
                archive.with_suffix('.json').write_text(json.dumps({'time_s':audit_time,'args':values,'candidates':result,
                    'explored_views':frozen.explored_views,'semantic_views':frozen.semantic_views},allow_nan=False))
                return result
            return await asyncio.to_thread(audited)
        return await asyncio.to_thread(function,frozen,*values)
    report = {'visit': visit, 'place': args.place, 'state': 'starting', 'steps': [], 'error': None,
              'input_contract': 'RGB + synthetic IMU-derived local pose; no scene/true pose/depth/labels/route',
              'previous_map_supplied': False, 'model': 'Qwen3-VL-2B + OpenVINS + multiview RGB geometry',
              'memory_scope': 'Evaluator, vision process, simulator/camera tree and specified local-model process roots'}
    report['assumptions']=['Level launch floor and a clear 0.5 m launch patch for visual-inertial initialization',
                           'Provisional calibrated camera and mounting; received sensor calibration is archived with this visit',
                           'Metric scale and obstacle geometry from camera/IMU parallax; image correspondences are uncertainty-gated',
                           'Survey and transit at 1.5 m; navigation requires observed clearance at 1.35–1.65 m',
                           'No historical map supplied to this first-visit experiment']
    sources=['scripts/explore_unknown.py','app/blind_mapping.py','app/metric_mapping.py','app/visual_inertial.py',
             'app/frontier_planner.py','app/breadcrumbs.py','app/voxel_mapping.py','app/temporal_geometry.py','app/planar_surfaces.py','app/place_memory.py','app/ui/blind-physics.mjs','scripts/blind_simulator.py',
             'app/ui/visible-colliders.mjs','app/ui/flight-lab.js','scripts/flight-camera.cjs',
             'scripts/blind-physics.mjs','sim/blind_world.py','native/openvins_bridge.cpp',
             'config/openvins/estimator.yaml','config/openvins/imu.yaml']
    report['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    report['protocol']=json.loads((ROOT/'config/blind-exploration-v1.json').read_text())
    binary=ROOT/'.local/build/openvins/drone137_openvins'
    report['native_runtime_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    manifest=ROOT/'.local/build/openvins/build-manifest.json'
    if manifest.exists():report['native_build']=json.loads(manifest.read_text())
    report['geometry_method']='Uncertainty-gated multiview triangulation with measured-support planar patches; no learned depth or renderer depth'
    for source in sources+['config/openvins-runtime.json','config/vendor-patches/openvins-macos.patch']:
        archived=folder/'source'/source
        archived.parent.mkdir(parents=True,exist_ok=True)
        archived.write_bytes((ROOT/source).read_bytes())
    watcher = MemoryWatch(args.memory_pid, budget_gib=5)
    watcher.start()
    link = Link(args.endpoint)
    model = LlamaBackend(timeout=20)
    vision_task = sensor_task = journal_task = None
    vio = VisualInertial()
    sensor_view = None
    latest_vio = None
    sensor_ready = False
    fusion_ready = False
    initialization_quality = None
    live_view = None
    vision_error = None
    started = time.monotonic()
    def save():
        report['wall_time_s'] = time.monotonic()-started
        report['map'] = mapping.snapshot()
        memory.save_map(visit, report['map'])
        temp = folder/'summary.tmp'
        temp.write_text(json.dumps(report, allow_nan=False))
        temp.replace(folder/'summary.json')
    try:
        geometry = TemporalGeometry()
        await model.health()
        await link.start()
        async with asyncio.timeout(10):
            while not link.latest.get('imu_calibration',{}).get('ready'):
                if link.error:raise RuntimeError(link.error)
                await asyncio.sleep(.05)
        # Establish a stationary visual/inertial reference before liftoff.
        # Airborne initialization can accept a momentarily quiet hover, then
        # diverge as monocular scale/gravity become observable under motion.
        first=await link.call('/frame')
        report['sensor_calibration']=first['calibration']
        report['initial_panorama']=panorama(first['calibration'])
        sweep_count=report['initial_panorama']['views']
        report['vio_input']='Calibrated rectified pinhole images; raw sensor JPEGs retained as evidence'
        await vio.start(first['calibration'], folder/'vio', link.latest['position'][2], stationary_phase=True)
        async def sensor_loop():
            nonlocal sensor_view, sensor_ready, vision_error,latest_vio,initialization_quality
            try:
                last_tracking=time.monotonic()
                bootstrap=True
                recovery_started=None
                recovery_good=None
                recovery_view=0
                while True:
                    watcher.check()
                    f=await link.call('/frame')
                    jpeg=base64.b64decode(f.pop('jpeg'))
                    imu=await link.call('/imu?after='+str(vio.last_imu))
                    result=await vio.observe(f,jpeg,imu)
                    latest_vio=result
                    if result and result['initialized']:
                        sensor_ready=True
                        tilt_error=gravity_disagreement_degrees(result['quaternion'],f['pose']['quaternion'])
                        initialization_quality={'time_s':result['time_s'],'gravity_disagreement_deg':tilt_error,
                            'position_disagreement_m':math.dist(result['position'],f['pose']['position']),
                            'tracks':result['stable_image_tracks'],'position_std_m':max(result['position_std_m'])}
                        if not fusion_ready:report['latest_initialization_quality']=dict(initialization_quality)
                        faults=tracking_faults(result,tilt_error,fusion_ready)
                        good=not faults
                        report['latest_tracking_health']={'time_s':result['time_s'],'faults':faults,
                            'position_std_m':result['position_std_m'],
                            'relative_position_std_m':result.get('relative_position_std_m'),
                            'relative_position_span_s':result.get('relative_position_span_s')}
                        if good and fusion_ready:
                            try:
                                await link.call('/visual',{**{k:result[k] for k in ('time_s','position','velocity','quaternion')},
                                                           'inliers':result['stable_image_tracks']})
                            except RuntimeError as exc:
                                good=False
                                report.setdefault('rejected_visual_updates',[]).append({'time_s':result['time_s'],'reason':str(exc)})
                        if good:
                            last_tracking=time.monotonic()
                            if fusion_ready:bootstrap=False
                            f['pose']={k:result[k] for k in ('time_s','position','quaternion')}
                            sensor_view=(f,jpeg,result)
                            rotation=result['rotation_imu_to_global']
                            breadcrumbs.observe(result['position'],math.atan2(rotation[1][0],rotation[0][0]))
                            if recovery_started is not None and result['stable_image_tracks']>=50:
                                recovery_good=recovery_good or time.monotonic()
                                if time.monotonic()-recovery_good>.7:
                                    link.goal=[*link.latest['position'],link.latest['yaw']]
                                    link.recovery_goal=None;link.recovered=True
                                    recovery_started=recovery_good=None
                            elif recovery_started is not None:
                                recovery_good=None
                    lost=time.monotonic()-last_tracking
                    if not bootstrap and lost>1 and link.motion_anchor is not None and recovery_started is None:
                        link.recovery_goal=list(link.motion_anchor)
                        recovery_started=time.monotonic();recovery_good=None
                        recovery_view=0
                        report.setdefault('tracking_recoveries',[]).append({'time_s':link.latest['time_s'],
                            'from':link.latest['position'],'retreat_to':link.recovery_goal,
                            'reason':'Tracking quality unavailable; retreat along the just-observed route',
                            'quality':report.get('latest_tracking_health')})
                    if recovery_started is not None:
                        age=time.monotonic()-recovery_started
                        if age>3 and recovery_view==0 and math.dist(link.latest['position'],link.motion_anchor[:3])<.2:
                            recovery_view=1
                            link.recovery_goal=[*link.motion_anchor[:3],link.motion_anchor[3]+math.pi/3]
                        elif age>8 and recovery_view==1:
                            recovery_view=2
                            link.recovery_goal=[*link.motion_anchor[:3],link.motion_anchor[3]-math.pi/3]
                    if recovery_started is not None and time.monotonic()-recovery_started>12:
                        raise RuntimeError('Visual tracking did not recover during bounded retreat')
                    if lost>(25 if bootstrap else 12 if recovery_started is not None else 4):
                        raise RuntimeError('Visual-inertial tracking unavailable; exploration stopped')
                    await asyncio.sleep(.03)
            except asyncio.CancelledError:raise
            except Exception as exc:
                vision_error=f'{type(exc).__name__}: {exc}'
                link.error='Visual estimation unavailable: '+vision_error
        sensor_task=asyncio.create_task(sensor_loop())
        async with asyncio.timeout(15):
            while not sensor_ready:
                if vision_error:raise RuntimeError(vision_error)
                await asyncio.sleep(.1)
        async def qualify_initialization(stage):
            stable=None
            try:
                async with asyncio.timeout(8):
                    while True:
                        qualified=initialization_ready(initialization_quality,link.latest['time_s'])
                        stable=(stable or time.monotonic()) if qualified else None
                        if stable is not None and time.monotonic()-stable>.7:return
                        if vision_error:raise RuntimeError(vision_error)
                        await asyncio.sleep(.05)
            except TimeoutError as exc:
                raise RuntimeError(stage+' camera/IMU initialization did not stabilize') from exc
        await qualify_initialization('Ground')
        report['ground_initialization']=dict(initialization_quality)
        # Ground-only stationary corrections cannot be re-enabled in flight.
        # Publish the phase change before sending the first liftoff command.
        vio.stationary_phase=False
        await link.fly([0,0,.3,0])
        await asyncio.sleep(2)
        # Excite both horizontal axes inside the declared clear launch patch
        # before trusting visual feedback. A single short straight move can
        # leave monocular scale/gravity poorly constrained while covariance is
        # already small. The calibrated IMU stabilizes this bounded maneuver.
        # Two non-collinear horizontal baselines and a return to the origin
        # suffice to test excitation after the vertical takeoff baseline. A
        # second circuit only prolonged unaided IMU integration and could
        # invalidate agreement before trustworthy visual feedback was enabled.
        for x,y in ((-.25,0),(0,.25),(0,0)):
            await link.fly([x,y,.3,0])
        await qualify_initialization('After-motion')
        report['visual_fusion_initialization']=dict(initialization_quality)
        fusion_ready=True
        await link.fly([-.3,0,.3,0])
        async def vision_loop():
            nonlocal live_view,vision_error
            last=-1
            try:
                while True:
                    if sensor_view is None or sensor_view[0]['capture_time_s']<=last:
                        await asyncio.sleep(.05);continue
                    f,jpeg,result=sensor_view
                    last=f['capture_time_s'];began=time.monotonic()
                    depth,tw,k,points,quality=await asyncio.to_thread(geometry.observe,jpeg,f['pose'],f['calibration'],result['landmarks'])
                    if len(points):
                        evidence=await asyncio.to_thread(mapping.prepare_cloud,points,tw[:3,3])
                        mapping.integrate_prepared(evidence,tw[:3,3],f['pose']['position'])
                    vo={'valid':True,'inliers':result['stable_image_tracks'],'landmarks':len(result['landmarks']),'position_std_m':result['position_std_m'],
                        'relative_position_std_m':result.get('relative_position_std_m'),
                        'position':result['position'],'multiview_geometry':quality,'estimator':'OpenVINS RGB + IMU'}
                    if depth is not None:live_view=(f,jpeg,depth,vo,time.monotonic()-began)
                    await asyncio.sleep(.05)
            except asyncio.CancelledError:raise
            except Exception as exc:
                vision_error=f'{type(exc).__name__}: {exc}'
                link.error='Mapping unavailable: '+vision_error
        vision_task=asyncio.create_task(vision_loop())
        launch_heading=0.
        for height in (.55,.8,1.05,1.3,1.5):
            link.motion_anchor=[*link.latest['position'],link.latest['yaw']]
            try:await link.fly([-.3,0,height,launch_heading])
            except ReplanAfterRecovery:
                # Retain the view that actually recovered tracking instead of
                # immediately turning away from it by another arbitrary 45°.
                launch_heading=link.latest['yaw']
                await link.fly([-.3,0,height,launch_heading])
            # Stable feature counts fluctuate as the estimator retires tracks.
            # Do not turn away from a valid view on a single low-count frame.
            # The sensor loop already handles sustained tracking loss with a
            # bounded retreat and a view search, at every ascent stage.
        link.motion_anchor=None
        report['state'] = 'exploring'
        heading, scans, last_move = launch_heading, 0, 0
        rejected_views=[]
        mapping.explored_views=[]
        active_view=None
        pending_views=[]
        surveyed_centers=[[0.,0.]]
        survey_height=1.5
        for index in range(args.observations):
            watcher.check()
            if journal_task:
                await journal_task
                journal_task=None
            if latest_vio and max(latest_vio.get('position_std_m',[0]))>=.25:
                report['stop_reason']='Accumulated position uncertainty return limit reached'
                break
            return_path=await plan(lambda m,p:m.path(p,[0,0]),list(link.latest['position']))
            backup=breadcrumbs.route(link.latest['position'],link.latest['yaw'])
            return_distance=(sum(math.dist(a,b) for a,b in zip(return_path,return_path[1:])) if return_path
                             else sum(math.dist(a[:3],b[:3]) for a,b in zip(backup,backup[1:])))
            reserve=max(45,return_distance/.4+25)
            if time.monotonic()-started > args.deadline-reserve:
                report['stop_reason'] = 'Return reserve reached'
                break
            # Loaded voltage is real telemetry, unlike simulator battery SOC.
            # Keep a conservative voltage reserve for the observed return route.
            return_voltage=3.30+.003*reserve
            if link.latest['voltage_v']<return_voltage:
                report['stop_reason']='Battery return reserve reached'
                report['return_reserve']={'loaded_voltage_v':link.latest['voltage_v'],
                    'threshold_v':return_voltage,'return_distance_m':return_distance,'seconds':reserve}
                break
            fresh_after=link.latest['time_s']-.5
            async with asyncio.timeout(12):
                while live_view is None or live_view[0]['capture_time_s']<fresh_after:
                    if vision_error:raise RuntimeError(vision_error)
                    await asyncio.sleep(.05)
            f,jpeg,depth,vo,geometry_latency=live_view
            if index<sweep_count:
                # The translated startup panorama is real exploration too.
                # Leaving it out of view history made launch-area uncertainty
                # appear untouched and repeatedly attracted the planner back.
                qx,qy,qz,qw=f['pose']['quaternion']
                observed_yaw=math.atan2(2*(qw*qz+qx*qy),1-2*(qy*qy+qz*qz))
                mapping.explored_views.append([*f['pose']['position'][:2],observed_yaw])
                record_view_attempt(mapping,f['pose']['position'],observed_yaw)
            image = f'frame-{index+1:04}.jpg'
            (folder/image).write_bytes(jpeg)
            began = time.monotonic()
            depth_image = cv2.applyColorMap(np.uint8(np.nan_to_num(np.clip(depth/8, 0, 1))*255), cv2.COLORMAP_TURBO)
            cv2.imwrite(str(folder/f'depth-{index+1:04}.jpg'), depth_image)
            step = {'sequence': index+1, 'image': image, 'pose': f['pose'], 'capture_time_s': f['capture_time_s'],
                    'visual_odometry': vo, 'observation': None, 'latency_s': 0,
                    'geometry_latency_s':geometry_latency,'evidence_directory':str(folder)}
            report['steps'].append(step)
            async def record(entry,pixels,caption,calibration):
                began=time.monotonic()
                if caption:
                    raw=await model.image(pixels,PROMPT,SCHEMA,time.monotonic()+20,max_tokens=200)
                    interpretation=json.loads(raw)
                    entry.update(interpretation)
                    x,y,z,w=entry['pose']['quaternion']
                    yaw=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
                    bearing=None
                    if interpretation['opening'] in ('left','center','right'):
                        transform,k=camera_transform(entry['pose'],calibration)
                        pixel=[interpretation['opening_x']*calibration['width']/1000,
                               interpretation['opening_y']*calibration['height']/1000,1]
                        ray=transform[:3,:3]@np.linalg.solve(k,pixel)
                        bearing=math.atan2(ray[1],ray[0])
                    mapping.semantic_views.append({'position':entry['pose']['position'][:2],
                        'yaw':yaw,'navigation_view':interpretation['navigation_view'],'opening':interpretation['opening'],
                        'opening_bearing':bearing,
                        'observation':entry['sequence'],'time_s':entry['capture_time_s']})
                    mapping.semantic_views=mapping.semantic_views[-20:]
                entry['latency_s']=time.monotonic()-began
                memory.observe(visit,entry['sequence'],pixels,entry)
            # Caption generation cannot change the flight command. Overlap it
            # with motion, while bounding the queue to one pending observation.
            journal_task=asyncio.create_task(record(step,jpeg,index%3==0,f['calibration']))
            save()
            print(json.dumps({'step': index+1, 'position': link.latest['position'], 'mapped_cells': len(report['map']['cells']), 'vo': vo,
                              'seconds': round(report['wall_time_s'], 1)}), flush=True)
            # A panoramic sweep precedes moves into newly observed free space.
            # Heading increments are generic active sensing, not authored routes.
            if scans < sweep_count-1:
                scans += 1
                heading += 2*math.pi/sweep_count
                # Rotation alone does not observe depth. A small orbit within
                # the clear launch patch supplies camera translation/parallax.
                # Stay behind the launch origin while looking across it. A
                # lateral baseline avoids ending nose-first against a wall.
                for side in (-.3,.3):
                    await link.fly([-.3*math.cos(heading)-side*math.sin(heading),
                                    -.3*math.sin(heading)+side*math.cos(heading),1.5,heading])
                continue
            if index==sweep_count-1:
                # Finish initialization back inside the declared clear launch
                # patch. The final orbit endpoint can sit at an uncertain map
                # edge, even though the central launch corridor is observed.
                await link.fly([0,0,survey_height,heading])
                link.guard=mapping.segment_clear
            if active_view is None:
                if pending_views:
                    active_view=pending_views.pop(0)
            if active_view is None:
                options=await plan(candidates,list(link.latest['position']),heading,15)
                rejected_views=[r for r in rejected_views if time.monotonic()<r['until']]
                options,retry=eligible_views(options,rejected_views,time.monotonic())
                if retry is not None:
                    # Temporary route rejection is not exhausted exploration.
                    # Hold observed space and re-evaluate with fresh imagery;
                    # the outer loop still enforces battery/deadline reserves.
                    link.goal=[*link.latest['position'],link.latest['yaw']]
                    report.setdefault('frontier_backoffs',[]).append({'time_s':link.latest['time_s'],'retry_after_s':retry})
                    await asyncio.sleep(min(2.,retry+.01))
                    continue
                if not options:
                    report['stop_reason']='No observed collision-clear frontier'
                    break
                active_view=choose_frontier(options,link.latest['position'],heading)
                report['steps'][-1]['frontier_candidates']=options
                report['steps'][-1]['selected_frontier']=active_view
            route=await plan(lambda m,p,q:m.path(p,q),list(link.latest['position']),active_view['viewpoint'])
            if not route:
                rejected_views.append({'point':active_view['viewpoint'],'until':time.monotonic()+15});active_view=None;continue
            next_point=None
            for point in route[1:]:
                if math.dist(link.latest['position'][:2],point)>2.:break
                if mapping.segment_clear(link.latest['position'],point):next_point=point
            if next_point is None:
                rejected_views.append({'point':active_view['viewpoint'],'until':time.monotonic()+15});active_view=None;continue
            arriving=math.dist(next_point,active_view['viewpoint'])<.2
            yaw=active_view['view_heading_rad'] if arriving else math.atan2(next_point[1]-link.latest['position'][1],next_point[0]-link.latest['position'][0])
            target=[*next_point,survey_height,yaw]
            link.motion_anchor=[*link.latest['position'],link.latest['yaw']]
            motion_phase='transit'
            try:
                await link.fly(target,settle=arriving)
                if arriving:
                    # A monocular camera needs translation after selecting a
                    # new viewing direction; a stationary turn supplies none.
                    p=link.latest['position'][:2]
                    measured=live_view[3]['multiview_geometry'] if live_view else {}
                    useful=(measured.get('points',0)>1000 and measured.get('baseline_m',0)>.5
                            and link.latest['time_s']-live_view[0]['capture_time_s']<1)
                    motion_phase='sensing_translation'
                    if not useful:
                        if latest_vio and latest_vio.get('stable_image_tracks',0)>=90:
                            link.motion_anchor=[*p,survey_height,yaw]
                        await translate_for_depth(link,mapping,yaw,survey_height,report)
                    # Record camera stations actually reached, including the
                    # parallax endpoint, rather than the requested grid point.
                    mapping.explored_views.append([*p,yaw])
                    if math.dist(p,link.latest['position'][:2])>.15:
                        mapping.explored_views.append([*link.latest['position'][:2],yaw])
                    record_view_attempt(mapping,link.latest['position'],yaw)
                    # A useful corridor may sit outside the direction with
                    # highest map uncertainty. At a genuinely new station,
                    # inspect the other two sectors before abandoning it.
                    # These are camera-only active-sensing moves in already
                    # observed airspace, never room-authored viewpoints.
                    if (not active_view.get('survey_followup') and
                            min(math.dist(active_view['viewpoint'],c) for c in surveyed_centers)>1.8):
                        center=list(link.latest['position'][:2])
                        surveyed_centers.append(center)
                        pending_views=[{'viewpoint':center,'view_heading_rad':yaw+j*2*math.pi/3,
                                        'survey_followup':True} for j in (1,2)]
                        report.setdefault('local_sweeps',[]).append({'position':center,'time_s':link.latest['time_s']})
                    active_view=None
            except ReplanAfterRecovery as exc:
                # A blocked/aborted route is not evidence that its destination
                # was observed. Keep it eligible after the temporary rejection.
                report.setdefault('navigation_replans',[]).append({'time_s':link.latest['time_s'],
                    'position':list(link.latest['position']),'requested_viewpoint':active_view['viewpoint'],
                    'phase':motion_phase,'reason':str(exc)})
                rejected_views.append({'point':active_view['viewpoint'],'until':time.monotonic()+15});active_view=None
                heading=link.latest['yaw']
                continue
            heading = target[3]
            scans = sweep_count-1
            last_move = index
        report['state'] = 'returning'
        save()
        link.motion_anchor=None
        path = await plan(lambda m,p:m.path(p,[0,0]),list(link.latest['position']))
        use_recorded=path is None
        # Simplify only where the entire segment remains observed and clear.
        while path and len(path)>1:
            furthest=1
            for i in range(2,len(path)):
                if not mapping.segment_clear(path[0],path[i]):break
                furthest=i
            point=path[furthest]
            if not mapping.segment_clear(link.latest['position'],point):
                use_recorded=True;break
            try:await link.fly([*point,survey_height,heading],timeout=max(35,math.dist(path[0],point)/.4+10))
            except ReplanAfterRecovery:
                use_recorded=True;break
            path=path[furthest:]
        if use_recorded:
            backup=breadcrumbs.route(link.latest['position'],link.latest['yaw'])
            report['return_mode']='Previously traversed camera/IMU trajectory; fresh observed obstacles veto each segment'
            report['return_trajectory']=backup
            link.guard=mapping.recorded_segment_unobstructed
            for point in backup[1:]:await link.fly(point)
            # The endpoint is in the declared clear launch patch. Re-observed
            # obstacles still veto this final short alignment with the origin.
            await link.fly([0,0,survey_height,link.latest['yaw']])

        await link.land()
        report['state'] = 'partial'
        report['navigation_finished'] = True
        report['note'] = 'Explorer does not see truth or self-award coverage. Independent evaluator decides pass/fail.'
    except Exception as exc:
        report['state'], report['error'] = 'failed', f'{type(exc).__name__}: {exc}'
        if link.latest:
            try:
                await link.land()
            except Exception as landing_error:
                report['landing_error'] = str(landing_error)
    finally:
        if journal_task:
            try:await journal_task
            except Exception as exc:
                report['state']='failed'
                report['error']=report['error'] or 'Image journal failed: '+str(exc)
        for task in (vision_task,sensor_task):
            if task:task.cancel()
        await asyncio.gather(*[t for t in (vision_task,sensor_task) if t],return_exceptions=True)
        await vio.close()
        # Retain the actual observed volume for post-flight diagnosis. This
        # archive contains estimates only and is never loaded by a new visit.
        np.savez_compressed(folder/'map-grid.npz',voxels=mapping.voxels,
                            ground=mapping.ground,flight_clear=mapping.flight_clear,
                            logodds=mapping.logodds,seen=mapping.seen,
                            visits=mapping.visits,view_attempts=mapping.view_attempts,
                            visibility_obstacles=mapping.visibility_obstacles)
        save()
        watcher.stop()
        report['memory'] = watcher.report()
        (folder/'summary.json').write_text(json.dumps(report, allow_nan=False))
        memory.finish(visit, report['state'], {k:v for k,v in report.items() if k not in ('map','steps','memory')})
        recalled = PlaceMemory(memory.path).recall(args.place)
        report['persistence_verified'] = any(v['id'] == visit and v['map'] and len(v['observations']) == len(report['steps']) for v in recalled['visits'])
        (folder/'summary.json').write_text(json.dumps(report, allow_nan=False))
        await model.close()
        if link.latest:
            try:
                await link.call('/finish', {})
            except Exception as exc:
                report['simulator_finish_error']=str(exc)
        await link.close()
    print(json.dumps({k:report.get(k) for k in ('state','error','persistence_verified','wall_time_s')}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--endpoint', default='http://127.0.0.1:8156')
    p.add_argument('--output', required=True)
    p.add_argument('--place', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--observations', type=int, default=100)
    p.add_argument('--deadline', type=float, default=600)
    p.add_argument('--memory-pid', action='append', type=int, default=[])
    asyncio.run(run(p.parse_args()))
