"""Freeze SQLite assemblies, simulate them with the browser's Rapier module, record results."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from app.components import Components,DEFAULT_DB,ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=str(DEFAULT_DB))
    p.add_argument('--output',type=Path,default=ROOT/'.local/validation/component-physics')
    p.add_argument('--configurations',nargs='*')
    p.add_argument('--seeds',type=int,nargs='+',default=[137])
    p.add_argument('--dt',type=float,choices=[.002,.004],default=.004)
    p.add_argument('--scenarios',nargs='+',default=['nominal','low-battery','gust','link-loss','weak-motor','pessimistic'])
    args=p.parse_args();registry=Components(args.db);args.output.mkdir(parents=True,exist_ok=True)
    refs=args.configurations or [c['content']['id']+'@'+str(c['revision']) for c in registry.list('configuration')]
    trials=[registry.freeze(ref,scenario,seed,args.dt) for ref in refs for scenario in args.scenarios for seed in args.seeds]
    source=args.output/'inputs.json';target=args.output/'results.json'
    source.write_text(json.dumps(trials,indent=2)+'\n')
    node=shutil.which('node')
    if not node:raise SystemExit('Node.js is required to run the same physics module used by Three.js')
    subprocess.run([node,str(ROOT/'scripts/run-component-physics.mjs'),str(source),str(target)],check=True,cwd=ROOT)
    data=json.loads(target.read_text())
    for item in data['results']:
        result={k:v for k,v in item['result'].items() if k!='trajectory'}
        registry.record(item['id'],result)
    summary=dict(engine='rapier-0.21.0',trials=len(trials),physics_process_peak_rss_mib=data['physics_process_peak_rss_mib'],
        real_hardware_tested=False,recognition_tested=False,full_8gb_stack_tested=False,
        results=[{k:v for k,v in item['result'].items() if k!='trajectory'} for item in data['results']])
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(trials=len(trials),flight_passed=sum(r['flight_passed'] for r in summary['results']),
        engineering_passed=sum(r['engineering_passed'] for r in summary['results']),summary=str(args.output/'summary.json'))))


if __name__=='__main__':main()
