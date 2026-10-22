"""Repeat identical saved inputs without caching; this is not mission accuracy."""
import argparse
import asyncio
import fcntl
import hashlib
import json
from pathlib import Path
import time
from app import identity
from app.localization import VISION_PROMPT, VISION_SCHEMA, parse_visual
from scripts.evaluate_localization import Supervisors
from scripts.experiment_model import experiment_model
from scripts.memory_watch import MemoryWatch
from scripts.tools import ROOT


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();base=args.baseline.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    lock=(ROOT/'.local/localization.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    previous=json.loads((base/'results.json').read_text());protocol=previous['protocol']
    assert protocol['vision_prompt']==VISION_PROMPT and protocol['identity_prompt']==identity.PROMPT
    assert protocol['identity_schema']==identity.SCHEMA
    requests=[];choices=[]
    for run in previous['runs']:
        # Fixed selection rule before inference: final full-frame observation and
        # final adequate candidate crop in each mission, regardless of correctness.
        step=run['steps'][-1]
        requests.append((run['case'],'full-frame',base/run['folder']/step['image'],step['image_sha256'],
                         VISION_PROMPT,VISION_SCHEMA,180,parse_visual,step['visual']))
        detail=next((s['identity'] for s in reversed(run['steps']) if s['identity'] and s['identity']['crop']['adequate_pixels']),None)
        if detail:
            requests.append((run['case'],'crop',base/run['folder']/detail['image'],detail['sha256'],
                             identity.PROMPT,identity.SCHEMA,200,identity.parse,detail['parts']))
        choices.extend((run['case'],s) for s in run['steps'] if len(s['allowed_actions'])>1)
    report={'scope':'Fixed saved inputs, two fresh requests each, no response cache. Not a new flight/accuracy evaluation.',
            'selection':'Last full frame and last adequate crop per case; all actual multi-action supervisor states.',
            'vision':[],'supervisor':[],'errors':[]}
    try:
        async with experiment_model('2b',output) as (backend,pid,manifest):
            assert manifest==previous['model'],'Model manifest differs from baseline'
            report['model']=manifest;watch=MemoryWatch([pid]);watch.start()
            try:
                supervisors=Supervisors(backend);supervisors.load_laya()
                report['laya']=json.loads((ROOT/'.local/data/laya-mlx/manifest.json').read_text())
                assert report['laya']==previous['laya'],'Laya manifest differs from baseline'
                for case,kind,path,sha,prompt,schema,tokens,parse,expected in requests:
                    data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==sha
                    results=[]
                    for repeat in range(2):
                        watch.check();raw=await backend.image(data,prompt,schema,time.monotonic()+12,max_tokens=tokens)
                        results.append(parse(raw))
                    row={'case':case,'kind':kind,'input_sha256':sha,'repeats':results,
                         'identical_repeats':results[0]==results[1],
                         'matches_recorded_output':[v==expected for v in results]}
                    report['vision'].append(row);print(json.dumps({k:v for k,v in row.items() if k!='repeats'}),flush=True)
                for case,step in choices:
                    answers=[]
                    for repeat in range(2):
                        watch.check();answers.append((await supervisors.decide('qwen+laya',step['state'],step['allowed_actions']))['action'])
                    report['supervisor'].append({'case':case,'view':step['view_id'],'answers':answers,
                        'identical_repeats':answers[0]==answers[1],
                        'matches_recorded_choice':all(a==step['decision']['action'] for a in answers)})
            finally:watch.stop();report['memory']={k:v for k,v in watch.report().items() if k!='samples'}
    except Exception as e:report['errors'].append(repr(e))
    finally:
        report['summary']={'vision_inputs':len(report['vision']),
            'identical_vision_repeats':sum(r['identical_repeats'] for r in report['vision']),
            'vision_inputs_matching_recorded_output':sum(all(r['matches_recorded_output']) for r in report['vision']),
            'supervisor_states':len(report['supervisor']),
            'identical_supervisor_choices':sum(r['identical_repeats'] for r in report['supervisor']),
            'supervisor_states_matching_recorded_choice':sum(r['matches_recorded_choice'] for r in report['supervisor'])}
        (output/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['summary']),flush=True)
    if report['errors']:raise RuntimeError(report['errors'])


if __name__=='__main__':asyncio.run(main())
