"""Run all three configurations on the same declared live-flight cases."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from scripts.tools import ROOT

ARMS=['qwen','qwen+florence','qwen+smolvlm']
CASES=['realism-east-glare-present','realism-east-glare-absent',
       'realism-west-occluded-present','realism-west-occluded-absent']


def summarize(report):
    runs=report['runs'];positive=[r for r in runs if r['score']['truth_xy_m'] is not None]
    negative=[r for r in runs if r['score']['truth_xy_m'] is None]
    latency=[s['vision_latency_s']+(s.get('identity') or {}).get('latency_s',0)
             +(s.get('identity') or {}).get('independent_review',{}).get('latency_s',0)
             +s['decision']['latency_s'] for r in runs for s in r['steps']]
    return {'attempted':len(runs),'planned':4,'positive_found':sum(r['score']['correct'] for r in positive),
        'positive_planned':2,'missed_or_incorrect_targets':2-sum(r['score']['correct'] for r in positive),
        'negative_correct':sum(r['score']['correct'] for r in negative),'negative_planned':2,
        'false_location_claims':sum(r['score']['false_location_claim'] for r in runs),
        'flight_physics_pass':sum(r.get('physical_checks',{}).get('all_pass',False) and not r['error']
                                    and r['flight']['envelope_violations']==0 for r in runs),
        'task_correct':sum(r['score']['correct'] for r in runs),
        'mean_camera_decision_latency_s':statistics.mean(latency) if latency else None,
        'mean_mission_wall_s':statistics.mean(r['wall_time_s'] for r in runs) if runs else None,
        'peak_application_gib':max((m['sampled_peak_guard_gib'] for m in report['memory'].values()),default=None),
        'accepted':report['qualification']['all_pass'] if report.get('qualification') else False,
        'errors':report['errors']}


def render(root,state):
    rows=''
    for arm in ARMS:
        result=state['results'].get(arm);label=arm.replace('qwen','Qwen').replace('florence','Florence-2').replace('smolvlm','SmolVLM2')
        if not result:
            rows+=f'<tr><th>{label}</th><td colspan=7>{"RUNNING" if state.get("active")==arm else "Pending"}</td></tr>';continue
        s=result['summary'];f=lambda x:'—' if x is None else f'{x:.2f}'
        rows+=f'<tr><th><a href="{result["directory"]}/report.html">{label}</a></th><td>{s["flight_physics_pass"]}/4</td><td>{s["positive_found"]}/2</td><td>{s["negative_correct"]}/2</td><td>{s["false_location_claims"]}</td><td>{f(s["mean_camera_decision_latency_s"])} s</td><td>{f(s["peak_application_gib"])} GiB</td><td class="{"pass" if s["accepted"] else "fail"}">{"PASS" if s["accepted"] else "FAIL"}</td></tr>'
    health=state['preflight'];checks=health['physical_checks']
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Live flight · three vision configurations</title>
<style>:root{{color-scheme:dark}}body{{background:#101b21;color:#e2eeeb;font:16px system-ui;max-width:1250px;margin:auto;padding:28px}}p{{line-height:1.6;max-width:950px;color:#bfd1d3}}table{{border-collapse:collapse;width:100%;margin:28px 0}}th,td{{padding:15px;text-align:left;border-bottom:1px solid #3b535c}}a{{color:#a6e8d6}}.pass{{color:#a9e7b6}}.fail{{color:#ffb5a0}}.scroll{{overflow-x:auto}}article{{padding:20px;background:#1c3039;border-radius:12px;margin:18px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}h1{{font-size:36px}}</style>
<p>DRONE137 / ACTUAL SIMULATED FLIGHTS</p><h1>Three vision configurations. Same flight challenge.</h1>
<p>Each configuration flies the glare and occlusion rooms, each with and without the target. Qwen reads live camera frames and supervises the search. Florence-2 or SmolVLM2 additionally inspects candidate crops in its own process. PX4 controls all four physical simulated rotors. These are fresh flights; camera images and timings can differ with aircraft motion.</p>
<article><b>Aircraft check: {"PASS" if checks["all_pass"] else "FAIL"}</b><p>Four connected rotors, measured rotation directions, lift-off, inspection hover and landing. Rotor speed is measured from Gazebo joint states with the model slowdown factor applied. Hover tracking RMSE: {checks["hover_tracking_rmse_m"]:.3f} m; {checks["inspection_samples"]} inspection samples.</p><a href="preflight.json">Physical evidence</a></article>
<div class=scroll><table><thead><tr><th>Configuration</th><th>Flight checks</th><th>Targets found</th><th>Absent cases correct</th><th>False claims</th><th>Mean vision + decision</th><th>Peak app memory</th><th>Acceptance</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Pass requires all four missions correct, successful flight checks and landing, no envelope violations, each mission within 300 seconds, no experiment errors and application memory within 5 GiB to leave headroom on an 8 GB computer. Failed and unexecuted cases remain in the denominator.</p>
<p>Scope: four known synthetic development cases, one provisional reference aircraft, no physical calibration. The host has 16 GiB; this does not certify performance on an actual 8 GiB machine. An absent-case pass means completed search without a location claim, not proof of absence.</p>
<p><a href="comparison.json">Full comparison</a> · <a href="protocol.json">Frozen protocol</a> · <a href="review/report.html">Flight videos and frame-by-frame evidence</a></p></html>'''
    (root/'report.html').write_text(page)
    (root/'comparison.json').write_text(json.dumps(state,indent=2))


def main(args):
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    preflight=json.loads(args.preflight.read_text());run=preflight['runs'][0]
    if preflight['errors'] or not run.get('physical_checks',{}).get('all_pass') or run['flight']['envelope_violations']:
        raise RuntimeError('Physical preflight gate failed')
    state={'preflight':run,'results':{},'active':None,'complete':False}
    (root/'preflight.json').write_text(json.dumps(run,indent=2))
    (root/'protocol.json').write_text(json.dumps({'arms':ARMS,'cases':CASES,'airframe':'reference-quad@1',
        'navigation':'observed','scope':'Known synthetic development missions; all arms fly live with the same policy and declared conditions.',
        'preflight_sha256':hashlib.sha256(args.preflight.read_bytes()).hexdigest()},indent=2))
    for arm in ARMS:
        state['active']=arm;render(root,state)
        name=arm.replace('+','-');folder=root/name
        command=[sys.executable,'-m','scripts.evaluate_flight','--output',str(folder),
            '--suite','realism','--assets','polyhaven','--airframes','reference-quad@1',
            '--navigation','observed','--arms',arm,'--keep-going','--cases',*CASES]
        print(json.dumps({'starting':arm,'cases':CASES}),flush=True)
        with (root/f'{name}.log').open('wb') as log:
            code=subprocess.call(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if not (folder/'results.json').exists():raise RuntimeError('Evaluator did not write evidence: '+arm)
        report=json.loads((folder/'results.json').read_text())
        state['results'][arm]={'directory':name,'exit_code':code,'summary':summarize(report)}
        render(root,state);print(json.dumps(state['results'][arm]),flush=True)
    state['active']=None;state['complete']=True;render(root,state)
    from scripts.build_flight_review import build
    build([root/r['directory']/'results.json' for r in state['results'].values()],root/'review',remux=True)
    page=root/'review/report.html'
    text=page.read_text().replace('Qwen + Laya · Difficult flight trials','Three vision configurations · live flight')
    text=text.replace('Qwen 2B observes camera pixels, Laya chooses eligible inspection actions, and PX4 controls the simulated quadcopter.',
        'Qwen 2B observes camera pixels and supervises eligible actions; Florence-2 or SmolVLM2 provides additional crop evidence in the paired arms. PX4 controls the simulated quadcopter.')
    page.write_text(text)
    return any(r['summary']['accepted'] for r in state['results'].values())

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--preflight',type=Path,required=True)
    raise SystemExit(0 if main(parser.parse_args()) else 1)
