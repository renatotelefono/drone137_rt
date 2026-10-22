"""Combine auditable native-flight runs without hiding earlier failed attempts."""
import argparse
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import statistics
from scripts.evaluate_flight import report_html
from scripts.tools import ROOT


def route_map(folder,run):
    scene=json.loads((folder/'scene.json').read_text())
    samples=json.loads((folder/'flight.json').read_text())['samples']
    point=lambda xy:(35+xy[0]*30,325-xy[1]*30)
    parts=['<svg viewBox="0 0 430 365" role="img" aria-label="Actual flight trajectory and scoring locations" style="width:100%;max-width:430px"><rect x="35" y="25" width="360" height="300" fill="#192a33" stroke="#7d969d"/>']
    for obj in scene['obstacles']:
        x,y=point([obj['x']-obj['sx']/2,obj['y']+obj['sy']/2])
        parts.append(f'<rect x="{x}" y="{y}" width="{obj["sx"]*30}" height="{obj["sy"]*30}" fill="#42555d"/>')
    points=' '.join(f'{x:.2f},{y:.2f}' for x,y in [point(s['truth']['position']) for s in samples[::3]])
    parts.append(f'<polyline points="{points}" fill="none" stroke="#92d9ed" stroke-width="2"/>')
    truth=run['score']['truth_xy_m'];location=run.get('location')
    if truth:
        x,y=point(truth);parts.append(f'<path d="M{x-6},{y-6}L{x+6},{y+6}M{x-6},{y+6}L{x+6},{y-6}" stroke="#ff9f94" stroke-width="3"/>')
    if location:
        x,y=point(location['xy_m']);parts.append(f'<circle cx="{x}" cy="{y}" r="8" stroke="#ffbc68" stroke-width="3" fill="none"/>')
    for step in run['steps']:
        x,y=point(step['frame']['estimated']['position']);parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#dbf6ef"/>')
    parts.append('<text x="35" y="350" fill="#b1c6cd" font-size="11">Blue: actual path · Coral ×: truth · Amber: estimate</text></svg>')
    return ''.join(parts),samples


def summarize(inputs,output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    report={'version':'dense-native-review-v1','runs':[],'memory':{},'attempts':[],
        'source_reports':[],'summary':{},'scope':'Authored simulation stress experiment; latest attempts shown, all earlier attempts retained.'}
    latest={};total_samples=[]
    for source in inputs:
        source=source.resolve();record=json.loads(source.read_text())
        report['source_reports'].append({'path':str(source.relative_to(output.parent)),
            'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'version':record['version'],'errors':record['errors']})
        for arm,m in record['memory'].items():
            if m['sampled_peak_gib']>report['memory'].get(arm,{}).get('sampled_peak_gib',0):
                report['memory'][arm]={k:v for k,v in m.items() if k!='samples'}
        for run in record['runs']:
            run=copy.deepcopy(run);folder=source.parent/run['folder'];run['folder']='../'+str(folder.relative_to(output.parent))
            run['source_report']='../'+str(source.relative_to(output.parent))
            svg,samples=route_map(folder,run);run['route_svg']=svg
            run['flight']['max_body_height_m']=max((s['truth']['position'][2] for s in samples),default=0)
            run['flight']['max_body_tilt_degrees']=max((math.degrees(math.acos(max(-1,min(1,1-2*(s['truth']['quaternion'][0]**2+s['truth']['quaternion'][1]**2))))) for s in samples),default=0)
            run['flight']['cart_travel_m']=max((s['truth'].get('cart_position',[0])[0] for s in samples),default=0)-min((s['truth'].get('cart_position',[0])[0] for s in samples),default=0)
            run['flight']['crossed_partition']=any(s['truth']['position'][0]>6.5 for s in samples)
            report['attempts'].append({k:run[k] for k in ('case','arm','folder','outcome','landed','score','error','source_report')})
            latest[(run['case'],run['arm'])]=run
    report['runs']=list(latest.values())
    for arm in report['memory']:
        runs=[r for r in report['runs'] if r['arm']==arm];steps=[s for r in runs for s in r['steps']]
        report['summary'][arm]={'correct':sum(r['score']['correct'] for r in runs),'cases':len(runs),
            'landed':sum(r['landed'] for r in runs),'false_location_claims':sum(r['score']['false_location_claim'] for r in runs),
            'mean_decision_s':statistics.mean(s['decision']['latency_s'] for s in steps) if steps else None,
            'mean_vision_s':statistics.mean(s['vision_latency_s'] for s in steps) if steps else None,
            'wall_time_s':sum(r['wall_time_s'] for r in runs),'distance_m':sum(r['flight']['distance_m'] for r in runs),
            'sampled_peak_gib':report['memory'][arm]['sampled_peak_gib']}
    report['models']={'qwen':json.loads((ROOT/'.local/data/models/manifest.json').read_text()),
                      'laya':json.loads((ROOT/'.local/data/laya-mlx/download-provenance.json').read_text())}
    report['simulator_versions']=json.loads((ROOT/'docs/versions.json').read_text())
    page=report_html(report)
    for run in report['runs']:
        video=f'<video controls preload=metadata poster="{run["folder"]}/preview.png"'
        poster=run['steps'][-1]['image'] if run['steps'] else 'preview.png'
        page=page.replace(video,run['route_svg']+f'<video controls preload=metadata poster="{run["folder"]}/{poster}"')
        if (output/run['folder']/'onboard-indexed.webm').is_file():
            page=page.replace(f'{run["folder"]}/onboard.webm',f'{run["folder"]}/onboard-indexed.webm')
    audit='<section><h2>All attempts</h2><p>The main cards use the latest run for each case and supervisor. Earlier attempts remain here, including the telemetry-stall failure. The follow-up adds a floor stand and moves route planning off the telemetry loop; model prompts and action eligibility are unchanged. The far-room case was added to exercise the doorway.</p><ul>'
    for attempt in report['attempts']:
        audit+=f'<li><a href="{html.escape(attempt["folder"])}/result.json">{html.escape(attempt["case"])} · {html.escape(attempt["arm"])}</a>: {html.escape(attempt["outcome"])}'+(' · '+html.escape(attempt['error']) if attempt['error'] else '')+'</li>'
    audit+='</ul></section>'
    table='<section><h2>Latest results by supervisor</h2><table><tr><th>Supervisor</th><th>Correct jobs</th><th>Returned + landed</th><th>False location claims</th><th>Mean decision</th><th>Sampled app RAM</th></tr>'
    for arm,s in report['summary'].items():table+=f'<tr><td>{arm}</td><td>{s["correct"]}/{s["cases"]}</td><td>{s["landed"]}/{s["cases"]}</td><td>{s["false_location_claims"]}</td><td>{s["mean_decision_s"]:.3f} s</td><td>{s["sampled_peak_gib"]:.2f} GiB</td></tr>'
    table+='</table><p>Small, independent simulated flights; differences in pixels and timing prevent a controlled claim that one supervisor is more accurate or faster overall.</p></section>'
    page=page.replace('<table><tr><th>Case',table+'<table><tr><th>Case',1).replace('</body>',audit+'</body>')
    (output/'results.json').write_text(json.dumps(report,indent=2));(output/'report.html').write_text(page)
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('inputs',nargs='+',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();summarize(args.inputs,args.output)
