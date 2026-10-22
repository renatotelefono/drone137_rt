"""Compare routes and fixed-pose camera pixels with an immutable flight snapshot.

This is an equivalence/microbenchmark, not another live mission score. Physics
does not run. Both renderers receive the same recorded pose/time/cart position,
with explicit angular-speed fixtures because historical frames omitted that field.
"""
import argparse
import asyncio
import copy
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import shutil
import time
from aiohttp import web
from scripts.evaluate_localization import Camera
from scripts.tools import ROOT
from sim.flight_world import route, HOME, VIEWS


def geometry_benchmark(baseline):
    source=baseline/'source/sim/flight_world.py'
    spec=importlib.util.spec_from_file_location('frozen_flight_world',source)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    scenes=[json.loads(p.read_text()) for p in sorted(baseline.glob('*/scene.json'))]
    records=[]
    for world in scenes:
        previous=HOME
        for destination in VIEWS+[HOME]:
            a=old.route(world,previous,destination);b=route(world,previous,destination)
            if a!=b:raise AssertionError('Route changed')
            records.append((world,previous,destination));previous=destination
    elapsed={'baseline':[],'optimized':[]}
    for repeat in range(3):
        order=[('baseline',old.route),('optimized',route)]
        if repeat%2:order.reverse()
        for label,fn in order:
            began=time.process_time()
            for world,start,end in records:fn(world,start,end)
            elapsed[label].append(time.process_time()-began)
    medians={k:statistics.median(v) for k,v in elapsed.items()}
    return {'exact_routes':len(records),'timed_batches_cpu_s':elapsed,'median_cpu_s':medians,
            'speedup':medians['baseline']/medians['optimized']}


INSTRUMENT='''import {Matrix4 as BenchMatrix4} from './vendor/three.module.js';
const benchCounts={compose:0,multiply:0};
for(const [method,key] of [['compose','compose'],['multiplyMatrices','multiply']]){
 const original=BenchMatrix4.prototype[method];
 BenchMatrix4.prototype[method]=function(...args){benchCounts[key]++;return original.apply(this,args);};
}
window.__benchSamples=[];
'''


async def renderer_benchmark(baseline,report,output):
    fixture={'world':None,'frame':None,'angular_speed':0.}
    async def server(base,port):
        app=web.Application()
        async def index(request):return web.FileResponse(base/'flight-lab.html',headers={'Cache-Control':'no-store'})
        async def scene(request):return web.json_response(fixture['world'])
        async def state(request):
            f=fixture['frame']
            return web.json_response({'truth':f['truth'],'estimated':f['estimated'],'wall_time':time.time(),
                'phase':'inspection','speed':0.,'angular_speed':fixture['angular_speed'],'trail':[],
                'message':'Fixed-input performance regression'})
        async def module(request):
            text=(base/'flight-lab.js').read_text()
            assert text.count('const t=state.truth')==1 and text.count('effects.render(scene,camera);')==1
            text=INSTRUMENT+text.replace('const t=state.truth','const benchStart=performance.now();benchCounts.compose=0;benchCounts.multiply=0;const t=state.truth')
            text=text.replace('effects.render(scene,camera);','effects.render(scene,camera);window.__benchSamples.push({submit_ms:performance.now()-benchStart,...benchCounts});if(window.__benchSamples.length>64)window.__benchSamples.shift();')
            return web.Response(text=text,content_type='text/javascript',headers={'Cache-Control':'no-store'})
        app.router.add_get('/',index);app.router.add_get('/scene.json',scene);app.router.add_get('/state',state)
        app.router.add_get('/assets/flight-lab.js',module);app.router.add_static('/assets',base)
        runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',port).start();return runner
    runners=[];camera=Camera();rows=[]
    camera.process=await asyncio.create_subprocess_exec('node','scripts/benchmark-camera.cjs',cwd=ROOT,
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
    try:
        runners.append(await server(baseline/'source/app/ui',8150))
        runners.append(await server(ROOT/'app/ui',8151))
        for run in report['runs']:
            folder=output/run['case'];folder.mkdir()
            fixture['world']=json.loads((baseline/run['folder']/'scene.json').read_text())
            fixtures=[]
            for i,step in enumerate(run['steps']):
                frame=copy.deepcopy(step['frame'])
                fixtures.append((frame,(0.,.3,1.2)[i%3]))
            collected={}
            # Alternate order between missions to reduce warmup/order bias.
            variants=[('baseline',8150),('optimized',8151)]
            if len(rows)%2:variants.reverse()
            for label,port in variants:
                fixture['frame'],fixture['angular_speed']=fixtures[0]
                await camera.call(op='open',url=f'http://127.0.0.1:{port}')
                try:
                    items=[]
                    for i,(frame,angular) in enumerate(fixtures):
                        fixture['frame'],fixture['angular_speed']=frame,angular
                        items.append(await camera.call(op='sample',sim_time=frame['truth']['sim_time'],path=str(folder/f'{label}-{i:02}.png')))
                    collected[label]=items
                finally:await camera.call(op='close')
            equal=[a['sha256']==b['sha256'] for a,b in zip(collected['baseline'],collected['optimized'])]
            rows.append({'case':run['case'],'exact_pixels':equal,'measurements':collected})
            print(json.dumps({'case':run['case'],'identical_frames':sum(equal),'total':len(equal)}),flush=True)
    finally:
        camera.process.stdin.close()
        try:await asyncio.wait_for(camera.process.wait(),10)
        except TimeoutError:camera.process.terminate();await camera.process.wait()
        for runner in runners:await runner.cleanup()
    summary={}
    for label in ('baseline','optimized'):
        values=[s for row in rows for image in row['measurements'][label] for s in image['samples']]
        summary[label]={k:statistics.median(v[k] for v in values) for k in ('submit_ms','compose','multiply')}
    return {'frames':sum(len(r['exact_pixels']) for r in rows),
            'identical_frames':sum(sum(r['exact_pixels']) for r in rows),
            'median_frame_metrics':summary,'cases':rows,
            'timing_scope':'Instrumented CPU submission time; not GPU completion, FPS or end-to-end mission time.',
            'fixture_note':'Recorded truth/estimated pose, simulation time and cart position. Angular speeds cycle 0/.3/1.2 rad/s equally in both renderers.'}


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();baseline=args.baseline.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    lock=(ROOT/'.local/localization.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    report=json.loads((baseline/'results.json').read_text())
    for rel,sha in report['source_hashes'].items():
        if hashlib.sha256((baseline/'source'/rel).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+rel)
    current_hashes={rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() for rel in report['source_hashes']}
    # Unchanged files come from the frozen baseline; preserve changed files so
    # benchmark evidence remains interpretable even if a trial is rolled back.
    for rel,sha in current_hashes.items():
        if sha!=report['source_hashes'][rel]:
            destination=output/'candidate-source'/rel;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,destination)
    result={'baseline':str(baseline),'candidate_source_hashes':current_hashes,'geometry':geometry_benchmark(baseline)}
    print(json.dumps(result['geometry']),flush=True)
    result['renderer']=await renderer_benchmark(baseline,report,output)
    result['changed_during_benchmark']=[rel for rel,sha in current_hashes.items() if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=sha]
    (output/'results.json').write_text(json.dumps(result,indent=2))
    if result['changed_during_benchmark']:raise AssertionError('Source changed during benchmark')
    if result['renderer']['frames']!=result['renderer']['identical_frames']:raise AssertionError('Camera pixels changed')


if __name__=='__main__':asyncio.run(main())
