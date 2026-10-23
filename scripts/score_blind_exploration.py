"""Post-flight evaluator. Truth enters here, never into the exploration client."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def evaluate(folder):
    world = json.loads((folder/'plant/scene.json').read_text())
    trace=[json.loads(line) for line in (folder/'plant/evaluator-telemetry.jsonl').read_text().splitlines()]
    finalized=(folder/'plant/final.json').is_file()
    final = json.loads((folder/'plant/final.json').read_text()) if finalized else trace[-1]
    result = json.loads((folder/'explorer/summary.json').read_text())
    termination=json.loads((folder/'termination.json').read_text()) if (folder/'termination.json').exists() else None
    lifecycle_memory=json.loads((folder/'startup-and-flight-memory.json').read_text()) if (folder/'startup-and-flight-memory.json').exists() else None
    policy = result.get('protocol') or json.loads((ROOT/'config/blind-exploration-v1.json').read_text())
    m = result['map']
    cell = m['resolution_m']
    n = round(2*m['extent_m']/cell)
    known = np.zeros((n,n),bool)
    occupied = np.zeros_like(known)
    for x,y,value,seen in m['cells']:
        known[x,y] = value < -.3
        occupied[x,y] = value > .5
    x,y = np.mgrid[:n,:n]
    wx = (x+.5)*cell-m['extent_m']+world['home'][0]
    wy = (y+.5)*cell-m['extent_m']+world['home'][1]
    distance = np.minimum.reduce([wx,wy,world['width']-wx,world['depth']-wy])-.06
    for b in [*world['obstacles'],*world.get('fixtures',[])]:
        if b.get('bottom',0) > 1.35 or b.get('bottom',0)+b['height'] < .85:
            continue
        dx,dy = np.abs(wx-b['x'])-b['sx']/2,np.abs(wy-b['y'])-b['sy']/2
        d = np.hypot(np.maximum(dx,0),np.maximum(dy,0))+np.minimum(np.maximum(dx,dy),0)
        distance = np.minimum(distance,d)
    free = distance > .35
    boundary = np.abs(distance) < cell
    coverage = float(np.sum(free & known)/max(1,np.sum(free)))
    false_free = float(np.sum((distance<0)&known)/max(1,np.sum(known)))
    true_points, mapped = np.argwhere(boundary)*cell, np.argwhere(occupied)*cell
    def nearest(a,b):
        if not len(a) or not len(b):
            return np.full(len(a),float('inf'))
        return np.array([np.min(np.linalg.norm(b-p,axis=1)) for p in a])
    boundary_error = nearest(mapped,true_points)
    boundary_recall = float(np.mean(nearest(true_points,mapped)<=.75)) if len(mapped) else 0.
    errors=[]
    for s in trace:
        if s['truth']['position'][2] > .1:
            truth = np.array(s['truth']['position'])-np.array([*world['home'],0])
            errors.append(float(np.linalg.norm(truth-np.array(s['sensor']['position']))))
    rmse = math.sqrt(sum(e*e for e in errors)/max(1,len(errors)))
    actual=final['truth']
    last=actual['position']
    returned=math.dist(last[:2],world['home'])
    raw=(folder/'plant/public-responses.jsonl').read_text()
    forbidden=['"truth":','"scene":','"obstacles":','"target_xy":','"cart_position":','"checkpoints":']
    metrics={'free_space_coverage':coverage,'false_free_fraction':false_free,
             'boundary_p95_m':float(np.percentile(boundary_error,95)) if len(boundary_error) else None,
             'boundary_recall':boundary_recall,'pose_rmse_m':rmse,'return_error_m':returned,
             'contacts':actual['contacts'],'landed':last[2]<.05 and actual['speed']<.15,
             'observations':len(result['steps']),'visual_corrections':final['sensor']['vision_updates']}
    a=policy['acceptance']
    gates={'finalized':finalized,'coverage':coverage>=a['minimum_free_space_coverage'],
           'false_free':false_free<=a['maximum_false_free_fraction'],
           'boundary_error':metrics['boundary_p95_m'] is not None and metrics['boundary_p95_m']<=a['maximum_boundary_error_m'],
           'boundary_recall':boundary_recall>=a['minimum_boundary_recall'],
           'pose':rmse<=a['maximum_pose_rmse_m'],'return':returned<=a['maximum_return_error_m'],
           'no_contact':actual['contacts']==0,'landed':metrics['landed'],
           'persistence':result.get('persistence_verified') is True,
           'no_truth_fields':not any(s in raw for s in forbidden),
           'navigation_completed':result.get('navigation_finished') is True and not result['error'],
           'deadline':result['wall_time_s']<=policy['limits']['deadline_s'],
           'memory':bool(result.get('memory')) and not result['memory']['budget_exceeded'] and not result['memory']['measurement_error']
                    and (lifecycle_memory is None or (not lifecycle_memory['budget_exceeded'] and not lifecycle_memory['measurement_error']))}
    score={'protocol':policy,'accepted':all(gates.values()),'gates':gates,'metrics':metrics,
           'error':result['error'] or (termination['error'] if termination else None),'place':result['place'],'visit':result['visit'],
           'physics_collision_source':world.get('physics_collision_source',{'version':'conservative-box-proxies'}),
           'peak_application_memory_gib':(lifecycle_memory or result.get('memory',{})).get('sampled_peak_guard_gib'),
           'notes':['Boundary scoring uses conservative simulator collision boxes, not exact visual mesh surfaces.',
                    result.get('geometry_method','Learned monocular depth; no metric depth sensor is supplied.'),
                    'No real hardware or real-world reliability qualification.'],
           'protocol_sha256':hashlib.sha256(((folder/'evaluation-source/blind-exploration-v1.json')
                    if (folder/'evaluation-source/blind-exploration-v1.json').exists()
                    else ROOT/'config/blind-exploration-v1.json').read_bytes()).hexdigest()}
    (folder/'score.json').write_text(json.dumps(score,indent=2,allow_nan=False))
    from app.place_memory import PlaceMemory
    PlaceMemory(ROOT/'.local/data/places.sqlite3').record_evaluation(result['visit'],score)
    # Visible truth is evaluator-only, clearly separated from the built map.
    def svg(mask,kind):
        parts=['<svg viewBox="0 0 480 400" role="img" aria-label="'+kind+'">']
        for i,j in np.argwhere(mask):
            px,py=(wx[i,j]-cell/2)*40,(world['depth']-wy[i,j]-cell/2)*40
            parts.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{cell*40:.1f}" height="{cell*40:.1f}" fill="#83d1ad"/>')
        return ''.join(parts)+'</svg>'
    cells=[]
    for i,j,value,seen in m['cells']:
        px,py=(wx[i,j]-cell/2)*40,(world['depth']-wy[i,j]-cell/2)*40
        cells.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{cell*40:.1f}" height="{cell*40:.1f}" fill="'+('#e7b16c' if value>.5 else '#83d1ad' if value<-.3 else '#52636b')+'"/>')
    cards=''.join('<article><img src="explorer/'+s['image']+'"><p>'+html.escape(s.get('observation') or 'Geometry observation; no semantic caption requested')+'</p></article>' for s in result['steps'])
    page='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Drone137 · Unknown place exploration</title><style>body{background:#101b21;color:#e1ece8;font:16px system-ui;max-width:1200px;margin:30px auto;padding:20px}p{line-height:1.5;color:#b9cccf}h1{font-size:32px}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #345}section{display:grid;grid-template-columns:1fr 1fr;gap:20px}svg{width:100%;background:#23333a}article{display:inline-block;width:30%;vertical-align:top;padding:1%}img{width:100%}a{color:#9ddbc8}.fail{color:#ffb19b}.pass{color:#8ee1b5}</style>'''
    page+='<h1>Unknown place: '+html.escape(result['place'])+'</h1><h2 class="'+('pass' if score['accepted'] else 'fail')+'">'+('PASS' if score['accepted'] else 'NOT PASSED')+'</h2><p>Single RGB camera + synthetic IMU integration. No supplied room map, true pose, depth buffer or authored viewpoints. '+html.escape(result.get('geometry_method','Depth is predicted by a local model.'))+'. Unknown map cells remain unknown.</p>'
    page+='<p>'+html.escape(score['error'] or result.get('stop_reason',''))+'</p><table><tr><th>Acceptance gate</th><th>Result</th></tr>'+''.join('<tr><td>'+k+'</td><td>'+('PASS' if v else 'FAIL')+'</td></tr>' for k,v in gates.items())+'</table>'
    page+='<section><div><h2>Built from camera observations</h2><svg viewBox="0 0 480 400">'+''.join(cells)+'</svg></div><div><h2>Evaluator reference — hidden during flight</h2>'+svg(free,'Hidden reference free space')+'</div></section>'
    page+='<pre>'+html.escape(json.dumps(metrics,indent=2))+'</pre><p><a href="score.json">Complete scoring</a> · <a href="explorer/summary.json">Observed place memory</a></p>'
    if (folder/'plant/onboard.webm').exists():
        page+='<h2>Recorded onboard video</h2><video controls preload="metadata" style="width:100%;max-height:620px" src="plant/onboard.webm"></video>'
    page+='<h2>Camera evidence and model journal</h2>'+cards
    (folder/'report.html').write_text(page)
    return score


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder')
    print(json.dumps(evaluate(Path(p.parse_args().folder)),indent=2))
