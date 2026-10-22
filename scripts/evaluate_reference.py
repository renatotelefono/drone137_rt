"""Paired reference-photo diagnostic on known failures; never a mission score."""
import argparse
import asyncio
import fcntl
import hashlib
import html
import json
from pathlib import Path
import statistics
import time
from app import identity
from scripts.evaluate_localization import Supervisors
from scripts.experiment_model import experiment_model
from scripts.memory_watch import MemoryWatch
from scripts.tools import ROOT

PROMPT=('The first image is the reference item to find. The second image is a candidate from another viewpoint. '
        'Compare the central objects, ignoring their backgrounds. Describe the candidate and a visible similarity '
        'or difference. Is the candidate the same type of object as the reference? Color alone is insufficient: '
        'compare the body and visible attached mechanisms. Do not copy unseen details from the reference. '
        'Use match only when the visible shape and mechanisms support the same object type, different for a '
        'lookalike with a different structure, or uncertain when the visible detail is insufficient. '
        'Return JSON with evidence and verdict (match, different, uncertain).')
SCHEMA={'type':'object','properties':{'evidence':{'type':'string','maxLength':200},
        'verdict':{'type':'string','enum':['match','different','uncertain']}},
        'required':['evidence','verdict'],'additionalProperties':False}


def diagnostic_inputs():
    base=ROOT/'.local/validation/identity-2b-v2'
    old=json.loads((base/'results.json').read_text())
    records=[{'path':base/r['image'],'expected_target':r['expected_target'],
              'label_basis':'Previously manually labeled candidate crop; known development set.'} for r in old['runs']]
    groups=[('laya-identity-baseline-v1','dense-absent',False,[5,6]),
            ('laya-hard-v1','hard-west-dim-present',True,[2,3]),
            ('laya-hard-v1','hard-east-glare-present',True,[6,7,8]),
            ('laya-hard-v1','hard-east-motion-present',False,[4,5])]
    for experiment,case,expected,frames in groups:
        for n in frames:
            records.append({'path':ROOT/f'.local/validation/{experiment}/{case}-qwen-laya/identity-frame-{n:04d}.jpg',
                'expected_target':expected,
                'label_basis':'Manually inspected candidate crop after mission. False-claim crops label the canister, even in a room containing a target.'})
    return records


async def evaluate(output):
    lock=(ROOT/'.local/localization.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    reference_path=ROOT/'.local/validation/laya-identity-baseline-v1/dense-present-qwen-laya/identity-frame-0002.jpg'
    reference=reference_path.read_bytes();(output/'reference.jpg').write_bytes(reference)
    inputs=[]
    for i,record in enumerate(diagnostic_inputs()):
        source=record.pop('path');data=source.read_bytes();name=f'candidate-{i:02d}.jpg';(output/name).write_bytes(data)
        inputs.append({**record,'image':name,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest()})
    protocol={'scope':'Known, correlated synthetic development crops, selected after inspecting failures. Not held-out accuracy or mission completion.',
        'reference_source':str(reference_path.relative_to(ROOT)),'reference_sha256':hashlib.sha256(reference).hexdigest(),
        'parts_prompt':identity.PROMPT,'parts_schema':identity.SCHEMA,
        'reference_prompt':PROMPT,'reference_schema':SCHEMA,'inputs':inputs,
        'laya_role':'Loaded to measure memory alongside Qwen; not invoked in this vision-only diagnostic.'}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2))
    report={'protocol':protocol,'runs':[],'errors':[],'memory':None}
    report['source_hashes']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
        ('scripts/evaluate_reference.py','app/identity.py','adapters/llama.py','scripts/experiment_model.py')}
    try:
        async with experiment_model('2b',output) as (backend,app_pid,manifest):
            report['model']=manifest;watch=MemoryWatch([app_pid]);watch.start()
            try:
                supervisor=Supervisors(backend);supervisor.load_laya()
                for record in inputs:
                    data=(output/record['image']).read_bytes()
                    for mode in ('parts','reference'):
                        watch.check();began=time.monotonic()
                        if mode=='parts':
                            value=identity.parse(await backend.image(data,identity.PROMPT,identity.SCHEMA,time.monotonic()+12,max_tokens=200))
                            accepted=identity.supported(value)
                        else:
                            value=json.loads(await backend.image(data,PROMPT,SCHEMA,time.monotonic()+12,reference=reference,max_tokens=220))
                            if (set(value)!={'evidence','verdict'} or value['verdict'] not in ('match','different','uncertain')
                                    or not isinstance(value['evidence'],str) or len(value['evidence'])>200):
                                raise ValueError('Invalid reference verdict')
                            accepted=value['verdict']=='match'
                        run={**record,'mode':mode,'response':value,'accepted':accepted,
                             'correct':accepted==record['expected_target'],'latency_s':time.monotonic()-began}
                        report['runs'].append(run);(output/'partial.json').write_text(json.dumps(report,indent=2))
                        print(json.dumps(run),flush=True);watch.check()
            finally:watch.stop();report['memory']=watch.report()
    except Exception as e:report['errors'].append(repr(e))
    summary={}
    for mode in ('parts','reference'):
        runs=[r for r in report['runs'] if r['mode']==mode]
        summary[mode]={'planned':len(inputs),'executed':len(runs),'correct':sum(r['correct'] for r in runs),
            'false_accepts':sum(r['accepted'] and not r['expected_target'] for r in runs),
            'false_rejections':sum(not r['accepted'] and r['expected_target'] for r in runs),
            'mean_latency_s':statistics.mean(r['latency_s'] for r in runs) if runs else None}
    report['summary']=summary;(output/'results.json').write_text(json.dumps(report,indent=2))
    cards=''
    for record in inputs:
        rows=[r for r in report['runs'] if r['image']==record['image']]
        text=''.join(f'<h3>{r["mode"]}: {"PASS" if r["correct"] else "FAIL"}</h3><pre>{html.escape(json.dumps(r["response"],indent=2))}</pre>' for r in rows)
        cards+=f'<article><img src="{record["image"]}"><p>Actual target: {record["expected_target"]}</p>{text}</article>'
    (output/'report.html').write_text('<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Reference-photo diagnostic</title>'
        '<style>body{padding:24px;background:#14232b;color:#dfedec;font:16px system-ui}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}article{background:#20343e;padding:16px;border-radius:10px}img{max-width:100%;max-height:300px}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#a8e7cf}</style>'
        f'<h1>Reference photo · Qwen 2B diagnostic</h1><p>{html.escape(protocol["scope"])}</p><img src=reference.jpg alt="Separate target reference"><pre>{html.escape(json.dumps(summary,indent=2))}</pre><p><a href=results.json>Full evidence</a> · <a href=protocol.json>Frozen input manifest</a></p><main>{cards}</main></html>')
    print(json.dumps({'summary':summary,'errors':report['errors'],'report':str(output/'report.html')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    asyncio.run(evaluate(parser.parse_args().output))
