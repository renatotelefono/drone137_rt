"""Dense workshop search with actual PX4 flight, bounded local models and evidence."""
import argparse
import asyncio
import fcntl
import hashlib
import html
import json
import math
from pathlib import Path
import platform
import statistics
import time
import shutil
from aiohttp import web
from adapters.native_flight import NativeFlight
from app.flight_localization import detection,triangulate,detail_view,planned_parallax,active_detail_views,retained_observation
from app.localization import VISION_PROMPT,VISION_SCHEMA,parse_visual,available_actions,decision_state
from app import identity
from scripts.experiment_model import experiment_model
from scripts.evaluate_localization import Camera,Supervisors
from scripts.memory_watch import MemoryWatch
from scripts.tools import ROOT
from sim.flight_world import scene,VIEWS,clear,inspection_sightline_clear
from sim.hard_flight import build as build_scene, cases as hard_cases, qualification
from sim.asset_world import build as build_asset_scene, verify_assets, ASSET_ROOT
from app.airframes import Airframes, DEFAULT_DB
from app.flight_health import audit as audit_flight_health
from app.inspection_planner import observed_viewpoints
from adapters.vision_reviewer import VisionReviewer, SMOL_PROMPT, FLORENCE_PROMPT
from sim.hardware import apply_profile


class FlightCamera(Camera):
    async def open(self,folder):
        self.process=await asyncio.create_subprocess_exec('node','scripts/flight-camera.cjs',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,cwd=ROOT)
        await self.call(op='open',folder=str(folder),url='http://127.0.0.1:8141')

    async def close(self):
        if getattr(self,'process',None) and self.process.returncode is None:
            try:
                self.stats=await self.call(op='close')
                self.process.stdin.close()
                await asyncio.wait_for(self.process.wait(),10)
                if self.stats.get('video',{}).get('error') or self.stats.get('stats',{}).get('errors'):
                    raise RuntimeError('Camera or video recording failed: '+json.dumps(self.stats))
            finally:
                if self.process.returncode is None:
                    self.process.terminate();await self.process.wait()


async def serve(flight,folder):
    app=web.Application(client_max_size=1024*1024);video=folder/'onboard.webm';sequence=0
    async def state(request):return web.json_response(flight.snapshot())
    async def model(request):return web.json_response(flight.scene)
    async def index(request):return web.FileResponse(ROOT/'app/ui/flight-lab.html')
    async def room(request):
        if not flight.scene.get('room_asset'):raise web.HTTPNotFound()
        return web.FileResponse(folder/'room.glb')
    async def chunk(request):
        nonlocal sequence
        if request.query.get('sequence')!=str(sequence):raise web.HTTPConflict()
        data=await request.read()
        if video.exists() and video.stat().st_size+len(data)>100*1024**2:raise web.HTTPInsufficientStorage()
        with video.open('ab') as f:f.write(data)
        sequence+=1;return web.json_response({'saved':True})
    app.router.add_get('/',index);app.router.add_get('/state',state);app.router.add_get('/scene.json',model)
    app.router.add_get('/room.glb',room)
    app.router.add_post('/video',chunk);app.router.add_static('/assets',ROOT/'app/ui',follow_symlinks=False)
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8141).start();return runner


def flight_metrics(samples, radius=.35):
    airborne=[s for s in samples if s['phase'] not in ('ready','starting','landed')]
    steady=[s for s in samples if s['phase']=='inspection']
    vals=lambda key:[s[key] for s in airborne]
    distances=[math.dist(a['truth']['position'],b['truth']['position']) for a,b in zip(airborne,airborne[1:])]
    return {'samples':len(samples),'distance_m':sum(distances),
        'minimum_truth_center_clearance_m':min(vals('clearance_m'),default=None),
        'envelope_violations':sum(s['clearance_m']<radius for s in airborne),'vehicle_envelope_radius_m':radius,
        'estimated_position_rmse_m':math.sqrt(statistics.mean(v*v for v in vals('position_error_m'))) if airborne else None,
        'max_speed_m_s':max(vals('speed'),default=None),
        'inspection_tracking_rmse_m':math.sqrt(statistics.mean(math.dist(s['estimated']['position'],s['goal'][:3])**2 for s in steady)) if steady else None,
        'simulation_to_wall_time_ratio':(samples[-1]['sim_time']-samples[0]['sim_time'])/(samples[-1]['host_time']-samples[0]['host_time']) if len(samples)>1 else None,
        'camera_attitude_source':'Gazebo rigid-body quaternion; policy localization uses PX4 estimator',
        'collision_metric':'Conservative swept horizontal envelope against shared scene boxes, not a contact-sensor count'}


async def mission(case,arm,folder,backend,supervisors,watch,smoke=False,identity_check=True,inspection_policy='parallax-v1'):
    folder.mkdir();world=build_asset_scene(case) if case.get('assets')=='polyhaven' else build_scene(case)
    if case.get('hardware'):world=apply_profile(world,case['hardware'],case.get('navigation')=='observed')
    if case.get('sensor_faults'):world['sensor_faults']=case['sensor_faults']
    if case.get('extra_obstacles'):world['obstacles'].extend(case['extra_obstacles'])
    if case.get('room_package'):
        from sim.room_assets import attach_room
        world=attach_room(world,case['room_package']);shutil.copyfile(world['room_asset']['path'],folder/'room.glb')
    (folder/'scene.json').write_text(json.dumps(world,indent=2))
    flight=NativeFlight(world,folder,watch);camera=FlightCamera();server=None
    run={'case':case['id'],'arm':arm,'steps':[],'outcome':'unresolved','location':None,'landed':False,'error':None,'folder':folder.name,
         'hardware':case.get('hardware'),'navigation_mode':world.get('navigation_mode','operator-map')}
    started=time.monotonic();first=None;first_supported=False;visited=set();views=VIEWS[:1] if smoke else case.get('views',VIEWS)
    try:
        await flight.start();server=await serve(flight,folder);await camera.open(folder)
        await camera.call(op='screenshot',name='preview.png')
        await flight.takeoff()
        index=0;confirmations=0;pose=views[0];inspection_mode=None
        while index<len(views):
            flight.message=f'{arm} · inspecting area {index+1}/{len(views)}'+(f' · extra view {confirmations}' if confirmations else '')
            await flight.fly(pose);visited.add(index);flight.check()
            frame=await camera.call(op='capture');metadata=frame['metadata']
            image=(folder/frame['image']).read_bytes()
            if smoke:
                await asyncio.sleep(3);flight.check()
                await camera.call(op='screenshot',name='preview.png');run['outcome']='flight-smoke';break
            began=time.monotonic()
            raw=await backend.image(image,VISION_PROMPT,VISION_SCHEMA,time.monotonic()+12,max_tokens=180)
            visual=parse_visual(raw);vision_time=time.monotonic()-began;flight.check()
            parts=None;detail=None;current_supported=False
            if identity_check and visual['status']=='present':
                crop,crop_metadata=identity.crop_candidate(image,visual['bbox'])
                crop_name='identity-'+frame['image'];(folder/crop_name).write_bytes(crop)
                began=time.monotonic()
                if crop_metadata['adequate_pixels']:
                    parts=identity.parse(await backend.image(crop,identity.PROMPT,identity.SCHEMA,time.monotonic()+12,max_tokens=200))
                current_supported=identity.supported(parts)
                detail={'image':crop_name,'sha256':hashlib.sha256(crop).hexdigest(),'crop':crop_metadata,
                        'parts':parts,'supported':current_supported,'latency_s':time.monotonic()-began}
                reviewer=getattr(supervisors,'reviewer',None)
                if reviewer and crop_metadata['adequate_pixels']:
                    review=await reviewer.review(folder/crop_name)
                    detail['independent_review']=review
                    current_supported=current_supported and review['accepted']
                    detail['supported']=current_supported
                flight.check()
            view=f'area-{index}'+('' if not confirmations else '-confirmation' if confirmations==1
                    else f'-detail-{confirmations}' if inspection_policy=='active-v2' else '-detail')
            current=detection(metadata['estimated'],visual['bbox'],view,world['camera'].get('optics')) if visual['status']=='present' else None
            location=triangulate(first,current) if first and current else None
            remaining=len(views)-len(visited)
            # Confirmation stations are operator-defined lateral moves. Bounds,
            # speed, stopping and separation are enforced outside either model.
            base=views[index]
            confirmation=[base[0]-.8*math.sin(base[3]),base[1]+.8*math.cos(base[3]),*base[2:]]
            can_confirm=not confirmations and flight.can_inspect(confirmation)
            inspection_plan=None;inspection_map=None
            if identity_check:
                reference=retained_observation(first,first_supported,current,current_supported)
                if inspection_policy=='active-v2':
                    extra=identity.reinspection_needed(confirmations,location,first_supported,current_supported,detail,visual['bbox'])
                    if extra and inspection_mode is None:
                        inspection_mode='centred' if visual['bbox'][1]<=10 or visual['bbox'][3]>=990 else 'elevated'
                    candidates=[]
                    if extra and flight.nav:
                        nav=flight.nav
                        snapshot={'grid':list(nav.grid),'safe':sorted(nav.safe),'cell_m':nav.CELL,
                            'width_cells':nav.nx,'height_cells':nav.ny,'vehicle_radius_m':nav.radius,'clearance_margin_m':nav.margin,
                            'source':'Timestamped observed ranges and estimated pose; no scene obstacle manifest'}
                        serialized=json.dumps(snapshot,separators=(',',':'))
                        map_name='inspection-map-'+Path(frame['image']).stem+'.json'
                        (folder/map_name).write_text(serialized)
                        inspection_map={'file':map_name,'sha256':hashlib.sha256(serialized.encode()).hexdigest()}
                        candidates=await asyncio.to_thread(observed_viewpoints,snapshot,metadata['estimated']['position'],location,world['camera'].get('optics'))
                    if extra:
                        candidates.extend({'pose':p,'mode':inspection_mode} for p in active_detail_views(
                            metadata['estimated']['position'],location,world['camera'].get('optics'),elevated=inspection_mode=='elevated'))
                else:
                    extra=confirmations==1 and location and first_supported != current_supported
                    candidates=[{'pose':detail_view(metadata['estimated']['position'],location,side),'mode':'parallax-v1'} for side in (1,-1)] if extra else []
                if extra:
                    for plan in candidates:
                        candidate=plan['pose']
                        camera_position=([candidate[0]+.12*math.cos(candidate[3]),
                                          candidate[1]+.12*math.sin(candidate[3]),candidate[2]+.02] if candidate else None)
                        parallax=planned_parallax(reference,candidate,location,world['camera'].get('optics')) if candidate else None
                        if (candidate and parallax
                                and (plan['mode']=='observed-map-sightline' or flight.can_inspect(candidate))
                                and (flight.observed or inspection_sightline_clear(world,camera_position,location['xyz_m']))):
                            confirmation=candidate;can_confirm=True
                            inspection_plan={**plan,'reference_view':reference['view_id'],**parallax};break
                can_confirm=can_confirm and current is not None
                state=identity.guarded_state(visual,parts,remaining,can_confirm,location,first_supported,current_supported)
                if detail and detail.get('independent_review'):
                    state+=' Independent image reviewer: '+json.dumps(detail['independent_review'])
                if inspection_policy=='active-v2':
                    state+=' Image too small or clipped for reliable detail: '+str(identity.needs_detail(detail,visual['bbox']))+'.'
                actions=identity.guarded_actions(remaining=remaining,confirmation_available=can_confirm,
                    location=location,first_supported=first_supported,current_supported=current_supported)
            else:
                state=decision_state(visual,remaining,can_confirm,location)
                actions=available_actions(remaining=remaining,confirmation_available=can_confirm,location=location)
            decision=({'action':next(iter(actions)),'latency_s':0.,'source':'deterministic eligibility; one action available'}
                      if identity_check and len(actions)==1 else await supervisors.decide('qwen' if arm in ('qwen+florence','qwen+smolvlm') else arm,state,actions))
            flight.check()
            if decision['action'] not in actions:raise RuntimeError('Supervisor selected ineligible action')
            event={'view_id':view,'image':frame['image'],'image_sha256':hashlib.sha256(image).hexdigest(),
                'frame':metadata,'visual':visual,'vision_latency_s':vision_time,'decision':decision,
                'location':location,'identity':detail,'state':state,'allowed_actions':actions,'inspection_plan':inspection_plan,'inspection_map':inspection_map}
            run['steps'].append(event)
            print(json.dumps({'case':case['id'],'arm':arm,'view':view,'visual':visual,'identity':parts,'action':decision['action'],'location':location}),flush=True)
            await camera.call(op='screenshot',name='preview.png')
            if decision['action'] in ('found','unresolved'):
                run['outcome']=decision['action']
                if decision['action']=='found':run['location']=location
                break
            if decision['action']=='confirm':
                first=retained_observation(first,first_supported,current,current_supported)
                if current_supported or not first_supported:
                    first_supported=current_supported
                confirmations+=1;pose=confirmation
            else:index+=1;confirmations=0;first=None;first_supported=False;inspection_mode=None;pose=views[index] if index<len(views) else None
        await flight.return_land();run['landed']=True
        # Flush video while the landed simulator still supplies live camera
        # frames. Tearing telemetry down first can strand canvas recording.
        await camera.close()
    except (Exception,asyncio.CancelledError) as e:
        run['error']=f'{type(e).__name__}: {e}'
        run['outcome']='interrupted' if isinstance(e,asyncio.CancelledError) else 'failed'
        print(json.dumps({'error':run['error'],'case':case['id'],'arm':arm}),flush=True)
    finally:
        # Keep recording through normal landing. Error cleanup also attempts to land.
        await flight.close()
        try:await camera.close()
        except Exception as e:run['error']='Camera cleanup: '+repr(e);run['outcome']='failed'
        run['camera']=getattr(camera,'stats',None)
        if server:await server.cleanup()
    run['wall_time_s']=time.monotonic()-started;run['flight']=flight_metrics(flight.samples,flight.profile['airframe']['body_radius_m'] if flight.profile else .35)
    run['navigation']=flight.nav.report() if flight.nav else None
    run['sensor_events']=flight.sensor_events
    run['cleanup_error']=flight.failed
    run['landed']=flight.landed
    if flight.samples:
        run['physical_checks']=audit_flight_health(folder,flight.samples,run['landed'])
    if flight.failed:run['error']=run['error'] or flight.failed
    run['search_areas_visited']=len(visited)
    truth=case.get('target_xy',[4.4,8.9]) if case['target'] else None
    error=math.dist(truth,run['location']['xy_m']) if truth and run['location'] else None
    found=run['outcome']=='found'
    run['score']={'truth_xy_m':truth,'error_m':error,'false_location_claim':found and (truth is None or error>.75),
        'correct':run['landed'] and ((found and error is not None and error<=.75) if truth else (run['outcome']=='unresolved' and len(visited)==len(views)))}
    run['score']['evaluated']=not smoke
    run['supervisor_calls']=sum(s['decision'].get('source') is None for s in run['steps'])
    run['deterministic_actions']=len(run['steps'])-run['supervisor_calls']
    (folder/'result.json').write_text(json.dumps(run,indent=2))
    return run


def report_html(report):
    esc=html.escape;rows=[];cards=[]
    for run in report['runs']:
        f=run['flight'];score=run['score'];directory=run['folder'];error=score['error_m']
        label='PASS' if score['correct'] else 'FAIL'
        if not report['real_inference']:
            label=('FLIGHT PASS' if run['landed'] and not run['error'] and f['envelope_violations']==0 else 'FLIGHT FAIL')+' · no inference'
        rows.append(f'<tr><td>{esc(run["case"])}</td><td>{esc(run["arm"])}</td><td>{label}</td><td>{esc(run["outcome"])}</td><td>{f["distance_m"]:.1f} m</td><td>{f["envelope_violations"]}</td><td>{f"{error:.2f} m" if error is not None else "—"}</td></tr>')
        steps=[]
        for s in run['steps']:
            b=s['visual']['bbox'];box='' if b is None else f'<span class=box style="left:{b[0]/10}%;top:{b[1]/10}%;width:{(b[2]-b[0])/10}%;height:{(b[3]-b[1])/10}%"></span>'
            detail=s.get('identity');detail_html=''
            if detail:
                detail_html=f'<p>Visible parts supported: <b>{detail["supported"]}</b></p><img loading=lazy src="{directory}/{detail["image"]}"><p>{esc(json.dumps(detail["parts"]))}</p>'
                if detail.get('independent_review'):
                    detail_html+='<p>Independent image review: '+esc(json.dumps(detail['independent_review']))+'</p>'
            steps.append(f'<article><div class=frame><img loading=lazy src="{directory}/{s["image"]}">{box}</div><p>{esc(s["view_id"])} · <b>{esc(s["decision"]["action"])}</b></p><p>{esc(s["visual"]["evidence"])}</p>{detail_html}</article>')
        cards.append(f'<section><h2>{esc(run["case"])} · {esc(run["arm"])}</h2><p>{esc(run["error"] or "Takeoff, inspection and return/landing completed.")}</p><video controls preload=metadata poster="{directory}/preview.png" src="{directory}/onboard.webm"></video><p><a href="{directory}/flight.json">Full flight telemetry</a> · <a href="{directory}/result.json">Model decisions and scores</a></p><div class=steps>{"".join(steps)}</div></section>')
    memory=' · '.join(f'{esc(arm)}: {m["sampled_peak_gib"]:.2f} GiB physical footprint'+(f', {m["sampled_peak_rss_gib"]:.2f} GiB summed RSS' if 'sampled_peak_rss_gib' in m else '') for arm,m in report['memory'].items())
    return '<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Dense workshop · Native flight results</title><style>body{max-width:1400px;padding:30px;margin:auto;background:#101c22;color:#e6efea;font:16px system-ui}p{color:#b1c6cd;line-height:1.5}h1{font-size:38px}table{border-collapse:collapse;width:100%;display:block;overflow:auto}td,th{padding:12px;border-bottom:1px solid #36505b;text-align:left}section{margin-top:38px;border-top:1px solid #36505b}video{max-width:100%;width:960px;border-radius:12px}.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px}article{background:#1b2b33;padding:12px;border-radius:9px}.frame{position:relative}img{width:100%}.box{position:absolute;border:2px solid #ffbc68;box-sizing:border-box}a{color:#9fdbed}@media(max-width:600px){body{padding:16px}h1{font-size:28px}}</style><body><p>DRONE137 / PHYSICS + LOCAL VISION</p><h1>A denser world. Actual simulated flight.</h1><p>120 props versus 12 in the previous scene. PX4 controls a Gazebo x500 at a 4 ms physics step. Three.js renders the actual body position, full attitude and fixed camera mount. The model sees camera pixels; localization uses PX4 estimated pose. The route uses an operator-provided map.</p><p>Measured application memory: '+memory+'. Measured on a 16 GiB Mac with a 5 GiB application guard; actual 8 GiB hardware remains untested.</p><p><b>Limits:</b> synthetic workshop, approximate collision boxes and optics, simulated GNSS indoors, generic x500 dynamics. No calibrated real-aircraft agreement, indoor VIO, wall/ground-effect model, rolling shutter or real-world reliability claim. Tenfold object count is not tenfold physical accuracy. These flight runs have different camera pixels; they are not a paired accuracy benchmark against the earlier camera-station test.</p><p><a href=results.json>Full experiment record</a></p><table><tr><th>Case</th><th>Supervisor</th><th>Result</th><th>Outcome</th><th>Distance</th><th>Envelope violations</th><th>Position error</th></tr>'+''.join(rows)+'</table>'+''.join(cards)+'</body></html>'


async def evaluate(args):
    if args.room and args.assets!='polyhaven':raise ValueError('Imported-room challenge requires separately imported movable targets (--assets polyhaven)')
    lock=(ROOT/'.local/localization.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=False)
    # Snapshot before any model request, not after a potentially edited run.
    source_files=sorted(p for base in ('adapters','app','sim','scripts','config') for p in (ROOT/base).rglob('*')
                        if p.is_file() and p.suffix in ('.py','.js','.cjs','.json','.html','.cpp','.gltf','.bin','.jpg','.hdr')
                        and '__pycache__' not in p.parts)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    for p in source_files:
        dest=folder/'source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    report={'version':'dense-native-flight-v5','suite':args.suite,'assets':args.assets,'real_flight_dynamics':True,'real_inference':not args.smoke,
        'physical_transport':False,'host':platform.platform(),'runs':[],'memory':{},'errors':[],
        'source_hashes':hashes,
        'physics':'Pinned PX4 x500 and Gazebo Harmonic, 250 Hz physics; Three.js camera attached to true rigid-body pose',
        'navigation':'Known operator map with conservative route inflation; PX4 estimated position, simulated GNSS',
        'model_size':args.model_size,
        'protocol':{'vision_prompt':VISION_PROMPT,'views':VIEWS,'tolerance_m':.75,'scene_complexity':scene()['complexity'],
                    'visual_reviewers':{'florence':FLORENCE_PROMPT,'smolvlm':SMOL_PROMPT,
                        'policy':'Companion sees only candidate pixels; explicit unnegated extinguisher identification AND Qwen visible parts required in both triangulated views. Qwen supervises search in all three comparison arms.'},
                    'identity_check':not args.legacy_baseline,'identity_version':identity.VERSION,
                    'identity_prompt':identity.PROMPT,'identity_schema':identity.SCHEMA,
                    'inspection_policy':args.inspection_policy,
                    'max_views_per_area':2 if args.legacy_baseline else 5 if args.inspection_policy=='active-v2' else 3,
                    'detail_view':('At most three extra views for small/clipped triangulated candidates or verifier disagreement, without requiring an initial identity hint: prefer camera stations <=3.5 m away reachable through inflated observed-free cells, with no known blocker along the estimated sightline (unknown sightline cells remain uncertain); route execution uses the existing observed navigation and motion guards. Save each planning map. Fallback: <1 m centred/elevated moves. All moves <=0.3 m vertically; ' if args.inspection_policy=='active-v2' else 'At most one extra view from estimated rays: <=0.72 m horizontal move; ')+
                        '>=1.4 m estimated standoff, 0.9–1.8 m altitude; predicted baseline >=0.55 m and angle >=7 degrees relative to the retained observation; observed-map clearance required. Identity acceptance gates unchanged.'}}
    specifications=[{'id':'dense-present','seed':417,'target':True,'condition':'nominal'},
        {'id':'dense-absent','seed':823,'target':False,'condition':'nominal'},
        {'id':'dense-low-light','seed':1109,'target':True,'condition':'dim'},
        {'id':'dense-east','seed':2017,'target':True,'target_xy':[10.1,6.4],
         'condition':'nominal','views':VIEWS[2:]+VIEWS[:2]}]
    if args.suite=='hard':specifications=hard_cases()
    if args.suite=='realism':
        from sim.realism_challenge import cases
        specifications=cases()
    if args.assets=='polyhaven':
        report['asset_manifest']=verify_assets()
        report['asset_manifest_sha256']=hashlib.sha256((ASSET_ROOT/'manifest.json').read_bytes()).hexdigest()
        report['protocol']['assets']={'manifest_sha256':report['asset_manifest_sha256'],
            'variant':'polyhaven-workshop-v1','target_height_m':report['asset_manifest']['assets']['korean_fire_extinguisher_01']['size_xyz_m'][1],
            'policy':'Same prompts, planner and decision gates; new assets, physical dimensions and HDR illumination.'}
        specifications=[{**c,'assets':'polyhaven'} for c in specifications]
    if args.cases and (len(set(args.cases))!=len(args.cases) or set(args.cases)-{c['id'] for c in specifications}):
        raise ValueError('Unknown or duplicate cases in requested suite')
    chosen=[c for c in specifications if not args.cases or c['id'] in args.cases]
    if args.smoke:chosen=chosen[:1]
    report['full_suite_selected']=len(chosen)==len(specifications) and not args.smoke
    if args.airframes:
        registry=Airframes(args.profile_db);snapshots=[registry.resolve(ref) for ref in args.airframes]
        if len({(s['profile']['id'],s['revision']) for s in snapshots})!=len(snapshots):raise ValueError('Duplicate airframe comparison entry')
        registry.freeze(folder.name,snapshots,folder)
        report['hardware']=snapshots;report['navigation']=args.navigation
        report['hardware_comparison']='Sequential native flights with shared local inference; not simultaneous aircraft in one airspace'
        chosen=[{**c,'id':c['id']+'-'+s['profile']['id']+'-r'+str(s['revision']),'base_case':c['id'],'hardware':s,'navigation':args.navigation} for s in snapshots for c in chosen]
    if args.room:
        from sim.room_assets import load_room
        room,asset,audit=load_room(args.room);report['room']={'manifest':room,'audit':audit}
        frozen_room=folder/'room-package';frozen_room.mkdir()
        shutil.copyfile(asset,frozen_room/'room.glb')
        room={**room,'visual_glb':'room.glb'};(frozen_room/'room.json').write_text(json.dumps(room,indent=2))
        chosen=[{**c,'room_package':str(frozen_room/'room.json')} for c in chosen]
    report['planned_runs']=len(chosen)*(1 if args.smoke else len(args.arms))
    (folder/'protocol.json').write_text(json.dumps({'cases':chosen,**report['protocol']},indent=2))
    report['protocol_sha256']=hashlib.sha256((folder/'protocol.json').read_bytes()).hexdigest()
    try:
        async with experiment_model(args.model_size,folder) as (backend,app_pid,manifest):
            report['model']=manifest;supervisors=Supervisors(backend)
            report['startup_memory']=backend.startup_memory
            for arm in (['qwen'] if args.smoke else args.arms):
                watch=MemoryWatch([app_pid]);watch.start()
                reviewer=None
                try:
                    if arm=='qwen+laya':
                        supervisors.load_laya()
                        report['laya']=json.loads((ROOT/'.local/data/laya-mlx/manifest.json').read_text())
                    if arm in ('qwen+florence','qwen+smolvlm'):
                        reviewer=VisionReviewer(arm.split('+')[1],folder)
                        report.setdefault('reviewers',{})[arm]=await reviewer.start()
                        supervisors.reviewer=reviewer;watch.check()
                    for case in chosen:
                        watch.check();run=await mission(case,arm,folder/(case['id']+'-'+arm.replace('+','-')),backend,supervisors,watch,args.smoke,not args.legacy_baseline,args.inspection_policy)
                        report['runs'].append(run)
                        (folder/'partial.json').write_text(json.dumps(report,indent=2))
                        if run['error'] and (not args.keep_going or backend.quarantined or run.get('cleanup_error')):raise RuntimeError(run['error'])
                finally:
                    if reviewer:await reviewer.close()
                    supervisors.reviewer=None
                    watch.stop();report['memory'][arm]=watch.report()
    except Exception as e:
        report['errors'].append(repr(e))
    finally:
        if args.room:
            try:load_room(folder/'room-package/room.json')
            except Exception as e:report['errors'].append('Room integrity: '+str(e))
        if args.assets=='polyhaven':
            try:
                current=verify_assets()
                if current!=report['asset_manifest']:raise ValueError('Asset manifest changed during experiment')
            except Exception as e:report['errors'].append(str(e))
        report['changed_sources']=[str(p.relative_to(ROOT)) for p in source_files if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p.relative_to(ROOT))]]
        if report['changed_sources']:report['errors'].append('Source changed during experiment')
        report['qualification']=qualification(report,report['planned_runs']) if not args.smoke else None
        if report['qualification']:
            report['qualification']['full_suite_qualified']=report['full_suite_selected'] and report['qualification']['all_pass']
        (folder/'results.json').write_text(json.dumps(report,indent=2))
        page=report_html(report).replace('<h1>A denser world. Actual simulated flight.</h1>',f'<h1>Qwen {args.model_size} · native flight + object checks</h1><p>Identity gate: {not args.legacy_baseline}. Both views must support the visible cylinder, curved hose and projecting top bar before a found action is eligible. This is an experimental check, not calibrated identity confidence.</p>')
        if args.assets=='polyhaven':
            page=page.replace('120 props versus 12 in the previous scene.', 'CC0 extinguisher, storage cart, shelves and crates with 1K PBR textures and photographed workshop HDR lighting. The target is 0.659 m tall. Same model prompts and policy as the procedural comparison. <a href="https://polyhaven.com">Assets from Poly Haven</a>.')
        if args.airframes:
            nav=('Sensor-only 5 cm occupancy map and simulated noisy odometry. GPS sensor removed; PX4 external-vision fusion enabled. '
                 'The odometry is synthesized from physics, not computed from images.' if args.navigation=='observed' else 'Known operator map and simulated GNSS.')
            page=page.replace('The route uses an operator-provided map.',nav)
            page=page.replace('synthetic workshop, approximate collision boxes and optics, simulated GNSS indoors, generic x500 dynamics. No calibrated real-aircraft agreement, indoor VIO, wall/ground-effect model, rolling shutter or real-world reliability claim.',
                'Provisional quad-X hardware profiles, conservative collision columns, first-order rotational rolling shutter/exposure and unmeasured sensor distributions. No real-camera VIO, calibrated aircraft/room agreement, propwash or physical-world qualification.')
            profiles=', '.join(html.escape(s['profile']['name'])+' r'+str(s['revision']) for s in report['hardware'])
            page=page.replace('<table><tr>','<p><b>Frozen hardware:</b> '+profiles+'. '+nav+'</p><table><tr>',1)
        if report['qualification']:
            q=report['qualification'];page=page.replace('<table><tr>',f'<h2>{q["qualified_passes"]}/{q["planned_runs"]} qualify · {"ALL PASS" if q["all_pass"] else "ACCEPTANCE TARGET NOT MET"}</h2><p>Suite: {html.escape(args.suite)}. Task-correct: {q["task_correct"]}/{q["completed_runs"]} executed; false location claims: {q["false_location_claims"]}. All planned runs count, including unexecuted runs after a failure. {html.escape(q["interpretation"])}</p><p><a href="protocol.json">Frozen cases and policy</a></p><table><tr>',1)
        (folder/'report.html').write_text(page)
    print(json.dumps({'report':str(folder/'report.html'),'errors':report['errors'],'runs':[{k:r[k] for k in ('case','arm','outcome','landed','score','flight')} for r in report['runs']],'memory':{a:m['sampled_peak_gib'] for a,m in report['memory'].items()}}),flush=True)
    return not report['errors'] and (bool(report['runs']) and all(r['landed'] and not r['error'] and r['flight']['envelope_violations']==0 and r.get('physical_checks',{}).get('all_pass',False) for r in report['runs']) if args.smoke else bool(report['qualification'] and report['qualification']['all_pass']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--model-size',choices=['2b','4b'],default='2b')
    parser.add_argument('--suite',choices=['baseline','hard','realism'],default='baseline')
    parser.add_argument('--airframes',nargs='+',help='SQLite profile IDs, optionally id@revision; compare sequentially')
    parser.add_argument('--room',type=Path,help='Frozen room.json from reconstruction/import; currently a 12 × 10 m operating volume')
    parser.add_argument('--keep-going',action='store_true',help='Retain failed missions and continue independent cases after successful cleanup')
    parser.add_argument('--profile-db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--navigation',choices=['observed','operator-map'],default='observed')
    parser.add_argument('--assets',choices=['procedural','polyhaven'],default='procedural')
    parser.add_argument('--legacy-baseline',action='store_true',help='Reproduce the old geometry-only identity gate')
    parser.add_argument('--inspection-policy',choices=['parallax-v1','active-v2'],default='parallax-v1',help='Bounded inspection strategy; active-v2 obtains closer views on small/clipped crops and disagreement')
    parser.add_argument('--arms',nargs='+',choices=['qwen','qwen+laya','qwen+florence','qwen+smolvlm'],default=['qwen','qwen+laya'])
    parser.add_argument('--cases',nargs='+',help='Optional case IDs within the selected suite; default: every case')
    raise SystemExit(0 if asyncio.run(evaluate(parser.parse_args())) else 1)
