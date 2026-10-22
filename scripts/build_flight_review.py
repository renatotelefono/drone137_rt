"""Small review page: all attempted/planned cases, one video loaded at a time."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
from scripts.tools import ROOT


def episode_passes(run,report):
    return (run['score']['correct'] and not run['error'] and run['landed']
            and run['flight']['envelope_violations']==0 and run['wall_time_s']<=300
            and run.get('physical_checks',{}).get('all_pass',True)
            and report['qualification']['memory_ok'] and not report['errors'])


def build(inputs, output, remux=False, reference_diagnostic=None):
    output.mkdir(parents=True, exist_ok=False)
    experiments=[];episodes=[]
    for path in inputs:
        path=path.resolve();report=json.loads(path.read_text());base=path.parent
        protocol=json.loads((base/'protocol.json').read_text())
        experiments.append({'name':base.name,'suite':report.get('suite','baseline'),
            'assets':report.get('assets','procedural'),
            'hardware':report.get('hardware',[]),'navigation':report.get('navigation'),
            'qualification':report['qualification'],
            'positive_planned':sum(c['target'] for c in protocol['cases']),
            'negative_planned':sum(not c['target'] for c in protocol['cases']),
            'positive_correct':sum(r['score']['correct'] and r['score']['truth_xy_m'] is not None for r in report['runs']),
            'negative_correct':sum(r['score']['correct'] and r['score']['truth_xy_m'] is None for r in report['runs']),
            'peak_gib':max(m['sampled_peak_guard_gib'] for m in report['memory'].values()),
            'errors':report['errors'],'protocol_sha256':report['protocol_sha256'],
            'results_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'results':os.path.relpath(path,output),
            'protocol':os.path.relpath(base/'protocol.json',output)})
        for case in protocol['cases']:
            runs=[r for r in report['runs'] if r['case']==case['id']]
            if not runs:
                episodes.append({'case':case['id'],'experiment':base.name,'status':'NOT RUN',
                                 'error':'Batch stopped before this planned case. It remains in the denominator.',
                                 'steps':[],'video':None,'score':None})
            for run in runs:
                folder=base/run['folder'];video=folder/'onboard.webm';validation=None
                if video.exists() and remux:
                    indexed=folder/'onboard-indexed.webm'
                    if not indexed.exists():
                        subprocess.run([str(ROOT/'scripts/with-sim.sh'),'ffmpeg','-v','error','-nostdin',
                                        '-i',str(video),'-c','copy',str(indexed)],check=True)
                    video=indexed
                    probe=subprocess.run([str(ROOT/'scripts/with-sim.sh'),'ffprobe','-v','error',
                        '-count_frames','-show_entries','stream=codec_name,width,height,nb_read_frames:format=duration',
                        '-of','json',str(video)],check=True,capture_output=True,text=True)
                    validation=json.loads(probe.stdout)
                steps=[]
                for step in run['steps']:
                    detail=step.get('identity')
                    steps.append({'view':step['view_id'],'image':os.path.relpath(folder/step['image'],output),
                        'visual':step['visual'],'decision':step['decision']['action'],
                        'source':step['decision'].get('source',run['arm']),
                        'sensor':step['frame'].get('sensor'),
                        'identity':detail['parts'] if detail else None,
                        'independent_review':detail.get('independent_review') if detail else None,
                        'supported':detail['supported'] if detail else None,
                        'crop':os.path.relpath(folder/detail['image'],output) if detail else None})
                accepted=episode_passes(run,report)
                episodes.append({'case':run['case'],'experiment':base.name,'status':'PASS' if accepted else 'FAIL',
                    'outcome':run['outcome'],'score':run['score'],'error':run['error'],'landed':run['landed'],
                    'flight':run['flight'],'physical_checks':run.get('physical_checks'),'seconds':run['wall_time_s'],
                    'supervisor_calls':run.get('supervisor_calls'), 'steps':steps,
                    'video':os.path.relpath(video,output) if video.exists() else None,
                    'video_validation':validation,'result':os.path.relpath(folder/'result.json',output)})
    data={'experiments':experiments,'episodes':episodes}
    diagnostic_html=''
    if reference_diagnostic:
        diagnostic=json.loads(reference_diagnostic.read_text())
        data['reference_diagnostic']={'summary':diagnostic['summary'],'errors':diagnostic['errors'],
            'results':os.path.relpath(reference_diagnostic.resolve(),output)}
        p,r=diagnostic['summary']['parts'],diagnostic['summary']['reference']
        diagnostic_html=(f'<article><h2>Reference-photo development diagnostic</h2><p>Existing parts check: {p["correct"]}/{p["planned"]}. '
            f'Reference comparison: {r["correct"]}/{r["planned"]}, with {r["false_accepts"]} false accepts. '
            'The reference approach was not adopted. These are known, correlated crops selected after failures; this is not mission accuracy.</p>'
            f'<a href="{html.escape(os.path.relpath(reference_diagnostic.resolve().parent/"report.html",output))}">Inspect paired crops and responses</a></article>')
    (output/'results.json').write_text(json.dumps(data,indent=2))
    cards=''
    for e in experiments:
        q=e['qualification']
        cards+=f'<article><h2>{html.escape(e["name"])}</h2><p class=big>{q["task_correct"]} / {q["planned_runs"]} task-correct</p><p>Target-present: {e["positive_correct"]}/{e["positive_planned"]} · Target-absent: {e["negative_correct"]}/{e["negative_planned"]}</p><p>{q["completed_runs"]} executed · {q["false_location_claims"]} false claims · {e["peak_gib"]:.2f} GiB peak guard measure</p><p>Full experiment: {"PASS" if q["all_pass"] else "ACCEPTANCE TARGET NOT MET"}</p><a href="{html.escape(e["protocol"])}">Frozen protocol</a> · <a href="{html.escape(e["results"])}">Complete evidence</a></article>'
        if e['hardware']:
            profiles=', '.join(html.escape(s['profile']['name'])+' r'+str(s['revision']) for s in e['hardware'])
            navigation=('GPS removed; PX4 estimates position from delayed noisy synthetic odometry. Navigation builds an observed range map from unknown space. This is not image-derived VIO.' if e['navigation']=='observed' else 'Operator-provided map and simulated GNSS.')
            cards+=f'<article><h2>Frozen aircraft & sensing</h2><p>{profiles}</p><p>{navigation}</p><p>Parameterized lens, mount, first-order rotational shutter/exposure and delayed/dropped frames. Physical calibration remains pending. Native profile comparisons are sequential.</p><a href="http://127.0.0.1:8137/airframes">Open aircraft library</a></article>'
    if any(e['assets']=='polyhaven' for e in experiments):
        cards+='<article><h2>Real-world asset variant</h2><p>CC0 extinguisher (0.659 m tall), storage cart, shelving and repeated crates; 1K PBR textures and photographed workshop HDR lighting. Remaining props and room layout are procedural. Scene, aircraft and sensing settings can differ between experiments; aggregate scores are not an isolated model comparison.</p><p>Assets: <a href="https://polyhaven.com/a/korean_fire_extinguisher_01">extinguisher</a> · <a href="https://polyhaven.com/a/industrial_storage_cart">cart</a> · <a href="https://polyhaven.com/a/steel_frame_shelves_01">shelves</a> · <a href="https://polyhaven.com/a/wooden_crate_01">crate</a> · <a href="https://polyhaven.com/a/industrial_workshop_foundry">HDR lighting</a></p><p>Powered by Poly Haven. Assets bundled locally under CC0; no runtime network download.</p></article>'
    payload=json.dumps(data).replace('<','\\u003c')
    page='''<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Local models · Difficult flight trials</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101b21;color:#e7efed;font:16px system-ui;padding:28px;max-width:1500px;margin:auto}h1{font-size:clamp(28px,4vw,45px);margin:10px 0}h2{font-size:19px;overflow-wrap:anywhere}p{line-height:1.5;color:#b8cbd0}a{color:#9ee4d0}.intro{max-width:1000px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}article,.panel{background:#192c34;padding:20px;border-radius:12px}.big{font-size:28px;color:#e9f5ee;margin:10px 0}.review{display:grid;grid-template-columns:290px minmax(0,1fr);gap:18px;margin-top:24px}nav{display:flex;flex-direction:column;gap:8px}button{font:inherit;color:inherit;background:#20343c;border:1px solid #3e5962;padding:12px;border-radius:8px;text-align:left;cursor:pointer;overflow-wrap:anywhere}button.active{border-color:#a6e9ce;background:#285448}.tag{font-size:12px;letter-spacing:.08em;color:#efc494}video,.frame{width:100%;max-width:960px;border-radius:9px;background:#0a1216}.frame{display:block}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px system-ui;line-height:1.5;color:#c0d2d6}.controls{display:flex;gap:8px;align-items:center;margin:16px 0}.crop{max-width:280px;max-height:320px;width:auto;display:block}.evidence{margin-top:16px;border-top:1px solid #3e5962;padding-top:10px}.note{border-left:3px solid #d2ad71;padding-left:16px}@media(max-width:800px){body{padding:16px}.review{grid-template-columns:1fr}nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}
</style><body><p class=tag>DRONE137 / LOCAL MODEL + NATIVE FLIGHT</p><h1>A harder test. Every result retained.</h1>
<p class=intro>Qwen observes camera pixels; the selected local supervisor chooses eligible inspection actions. Paired vision configurations add an independent image reviewer. PX4 controls the simulated quadcopter. Every experiment retains its failed and unexecuted cases.</p>
<p class="intro note">The objective is every planned mission passing, with zero false location claims. This is a synthetic challenge in one building topology, not proof of real-world accuracy. The current host has 16 GiB; actual 8 GiB hardware and a reconstructed real room remain untested. “Unresolved” means no supported target was located, not proof of absence.</p>
<div class=cards>CARDS</div>DIAGNOSTIC<p>Cases combine rearranged furniture, rotated targets, red-canister decoys, partial occlusion, lighting variation and degraded camera delivery. The frozen protocol lists each case's settings and any sensor outages. Only one video is loaded at a time.</p>
<div class=review><nav id=episodes aria-label="Choose mission"></nav><main class=panel><h2 id=title></h2><p id=summary></p><video id=video controls preload=metadata></video><p id=error></p><a id=raw>Raw mission evidence</a><div class=evidence><div class=controls><button id=prev>Previous frame</button><span id=counter></span><button id=next>Next frame</button></div><img id=frame class=frame alt="Actual camera input to the vision model"><pre id=decision></pre><img id=crop class=crop alt="Candidate crop used for the visible-parts check"><pre id=parts></pre></div></main></div>
<script id=data type=application/json>PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);let selected=0,index=0;
const text=(id,value)=>$(id).textContent=value;
function step(){const r=data.episodes[selected],s=r.steps[index];document.querySelector('.evidence').hidden=!s;if(!s)return;
 $('frame').src=s.image;text('counter',`${index+1} / ${r.steps.length}`);text('decision',`${s.view} → ${s.decision}\nDecision source: ${s.source}\nVision: ${s.visual.evidence}\n${s.sensor?`Image age at render: ${s.sensor.frame_age_ms.toFixed(0)} ms · dropped frames: ${s.sensor.dropped_frames}`:''}`);
 $('crop').hidden=!s.crop;if(s.crop)$('crop').src=s.crop;else $('crop').removeAttribute('src');text('parts',(s.identity?`Required visual checks supported: ${s.supported}\n${JSON.stringify(s.identity,null,2)}`:'No adequate candidate crop check.')+(s.independent_review?`\nIndependent reviewer (${s.independent_review.model}): ${s.independent_review.caption}\nAccepted: ${s.independent_review.accepted}`:''));$('prev').disabled=index===0;$('next').disabled=index===r.steps.length-1;}
function choose(i){selected=i;index=0;const r=data.episodes[i];document.querySelectorAll('nav button').forEach((b,j)=>b.classList.toggle('active',i===j));text('title',`${r.status} · ${r.case}`);text('summary',`${r.experiment}${r.seconds?` · ${r.seconds.toFixed(1)} s · landed: ${r.landed} · Supervisor calls: ${r.supervisor_calls}`:''}`);text('error',r.error||(r.score?.false_location_claim?'False location claim: the reported object did not match the target.':r.status==='FAIL'?'The mission did not meet the task, flight or experiment criteria.':'Mission record saved.'));
 $('video').pause();$('video').poster=r.steps[0]?.image||'';$('video').removeAttribute('src');$('video').hidden=!r.video;if(r.video)$('video').src=r.video;$('video').load();$('raw').hidden=!r.result;if(r.result)$('raw').href=r.result;step();}
data.episodes.forEach((r,i)=>{const b=document.createElement('button');b.textContent=`${r.status} · ${r.case}`;b.onclick=()=>choose(i);$('episodes').append(b);});$('prev').onclick=()=>{index--;step();};$('next').onclick=()=>{index++;step();};choose(0);
</script></body></html>'''.replace('CARDS',cards).replace('DIAGNOSTIC',diagnostic_html).replace('PAYLOAD',payload)
    page=page.replace('</style>','[hidden]{display:none!important}</style>')
    (output/'report.html').write_text(page)
    return output/'report.html'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--remux',action='store_true')
    parser.add_argument('--reference-diagnostic',type=Path)
    args=parser.parse_args();print(build(args.inputs,args.output.resolve(),args.remux,args.reference_diagnostic))
