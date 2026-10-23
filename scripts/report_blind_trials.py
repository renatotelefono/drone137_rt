"""Publish all development outcomes without hiding failed flights."""
import argparse
import html
import json
from pathlib import Path


def build(folder):
    records=[]
    for path in sorted(folder.glob('development-*')):
        if not path.is_dir():continue
        score=path/'score.json'
        summary=path/'explorer/summary.json'
        if score.exists():
            data=json.loads(score.read_text());result=json.loads(summary.read_text())
            records.append({'trial':path.name,'scored':True,**data,'memory_peak_gib':data.get('peak_application_memory_gib',result.get('memory',{}).get('sampled_peak_guard_gib'))})
        elif summary.exists():
            result=json.loads(summary.read_text())
            records.append({'trial':path.name,'scored':False,'running':result['state'] in ('starting','exploring','returning'),'accepted':False,'metrics':{},'error':result.get('error') or 'No finalized score'})
        elif (path/'termination.json').exists():
            termination=json.loads((path/'termination.json').read_text())
            records.append({'trial':path.name,'scored':False,'running':False,'accepted':False,'metrics':{},'error':termination['error']})
    (folder/'comparison.json').write_text(json.dumps(records,indent=2))
    page='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Drone137 · Blind exploration trials</title><style>body{background:#101b21;color:#e1ece8;font:16px system-ui;max-width:1300px;margin:30px auto;padding:20px}p{line-height:1.5;color:#b9cccf}h1{font-size:32px}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #345}a{color:#9ddbc8}.fail{color:#ffb19b}.pass{color:#8ee1b5}small{color:#b9cccf}</style>'''
    passed=sum(x['accepted'] for x in records)
    completed=sum(not x.get('running') for x in records)
    running=sum(bool(x.get('running')) for x in records)
    page+=f'<h1>Unknown-place exploration</h1><h2 class="{"pass" if passed else "fail"}">{passed} of {completed} completed development attempts passed all gates</h2>'
    if running:page+=f'<p>{running} attempt(s) still running or awaiting finalization; excluded from the completed count.</p>'
    page+='<p>These are successive engineering trials, not independent reliability samples. All failed attempts are retained. The earlier known-map benchmark does not qualify blind exploration.</p>'
    for suite in sorted(folder.glob('qualification-*/results.json')):
        data=json.loads(suite.read_text())
        name=html.escape(suite.parent.name)
        page+=f'<h2>{name}: {data["passed"]}/{data["planned"]} planned flights passed</h2>'
        page+='<p>'+html.escape(data.get('scope','Synthetic qualification'))+'. The denominator includes unfinished cases. Layouts used for subsequent fixes become development cases.</p>'
        page+='<table><tr><th>Layout</th><th>Result</th><th>Coverage</th><th>Failed checks</th></tr>'
        for result in data['results']:
            coverage=result.get('metrics',{}).get('free_space_coverage')
            shown=f'{coverage:.1%}' if coverage is not None else '—'
            label=html.escape(str(result['seed']))
            if result.get('report'):
                href=html.escape(suite.parent.name+'/'+result['report'],quote=True)
                label=f'<a href="{href}">{label}</a>'
            failures=', '.join(k for k,v in result.get('gates',{}).items() if not v) or '—'
            page+=f'<tr><td>{label}</td><td>{html.escape(result["state"].upper())}</td><td>{shown}</td><td>{html.escape(failures)}</td></tr>'
        page+='</table>'
    page+='<p>The explorer receives onboard RGB images and synthetic IMU estimates. It starts with an empty room map. Named places, estimated maps and image-backed observations are saved in SQLite. <a href="http://127.0.0.1:8137/places">Open saved places</a></p>'
    page+='<p>Pass criteria: at least 80% free-space coverage, at most 5% false free space, position and return error at most 0.4 m, boundary error at most 0.75 m, boundary recall at least 70%, zero contacts, landing, persistence and a measured application budget below 5 GiB. Camera configurations and algorithms changed between development trials; every run retains its source manifest and scene.</p>'
    page+='<p>From development-48, static contacts use the rendered triangle surfaces. Earlier enclosing boxes included invisible air above furniture. Those historical contacts remain reported, but the collision models differ. Floor-plan scoring and acceptance thresholds remain unchanged.</p>'
    page+='<div style="overflow:auto"><table><tr><th>Trial</th><th>Result</th><th>Coverage</th><th>False free</th><th>Position RMSE</th><th>Return error</th><th>Contacts</th><th>Landed</th><th>Memory</th><th>Static collision model</th></tr>'
    for r in records:
        m=r['metrics']
        def metric(key,suffix='',scale=1):
            value=m.get(key)
            return f'{value*scale:.2f}{suffix}' if isinstance(value,(float,int)) else '—'
        peak=r.get('memory_peak_gib')
        link=f'<a href="{r["trial"]}/report.html">{r["trial"]}</a>' if m else r['trial']
        collision='Rendered surfaces' if r.get('physics_collision_source',{}).get('version')=='rendered-static-triangle-mesh-v1' else 'Enclosing boxes' if m else '—'
        page+=f'<tr><td>{link}</td><td class="{"pass" if r["accepted"] else "fail"}">{"PASS" if r["accepted"] else "RUNNING / UNSCORED" if r.get("running") else "NOT PASSED"}</td><td>{metric("free_space_coverage","%",100)}</td><td>{metric("false_free_fraction","%",100)}</td><td>{metric("pose_rmse_m"," m")}</td><td>{metric("return_error_m"," m")}</td><td>{m.get("contacts","—")}</td><td>{m.get("landed","—")}</td><td>{f"{peak:.2f} GiB" if peak else "—"}</td><td>{collision}</td></tr>'
        if r.get('error'):page+='<tr><td colspan="10"><small>'+html.escape(r['error'])+'</small></td></tr>'
    page+='</table></div><p>Provisional synthetic sensors and camera calibration. No actual 8 GB hardware or real-drone qualification. <a href="comparison.json">Complete results</a></p>'
    (folder/'overview.html').write_text(page)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');build(Path(parser.parse_args().folder))
