"""Publish the fixed-cohort controller comparison, retaining every result and input."""
import argparse
import hashlib
import json
from pathlib import Path

from app.components import ROOT

SCENARIOS=('nominal','low-battery','gust','link-loss','weak-motor','pessimistic')
MODELS=[('cf2-reference','cf2-reference','Crazyflie-derived reference'),
        ('micro-90','micro-90-power-v2','Micro 90 / 1S2P'),
        ('scout-110','scout-110-power-v2','Scout 110 / 1S2P'),
        ('guard-110','guard-110-power-v2','Guard 110 / 1S3P'),
        ('height-110','height-110-power-v2','Height 110 / 1S3P'),
        ('split-110','split-110-power-v2','Split 110 / 1S3P'),
        ('scout-published-pack','scout-published-pack','Scout / original Pluto pack')]


def load(path):return json.loads(path.read_text())


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def totals(rows):
    return dict(passed=sum(r['flight_passed'] for r in rows),total=len(rows),
                engineering_passed=sum(r['engineering_passed'] for r in rows))


def verify(rows,identities,seeds):
    expected={(name,scenario,seed) for name in identities for scenario in SCENARIOS for seed in seeds}
    actual=[(r['configuration'],r['scenario'],r.get('seed',137)) for r in rows]
    if len(actual)!=len(set(actual)) or set(actual)!=expected:raise ValueError('Duplicate or omitted benchmark case')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,default=ROOT/'.local/validation/controller-improvement')
    args=parser.parse_args();base=load(ROOT/'docs/component-physics-validation.json')['results']
    original=load(args.runs/'verified-original/summary.json')
    revised=load(args.runs/'verified-revised/summary.json')
    additional=load(args.runs/'verified-additional/summary.json')
    fine=load(args.runs/'verified-fine/summary.json')
    seeds=sorted({r['seed'] for r in additional['results']})
    for rows,ids,run_seeds in [(base,[m[0] for m in MODELS],[137]),(original['results'],[m[0] for m in MODELS],[137]),
                               (revised['results'],[m[1] for m in MODELS],[137]),(additional['results'],[m[1] for m in MODELS],seeds),
                               (fine['results'],[m[1] for m in MODELS],[137])]:verify(rows,ids,run_seeds)
    model_hash=hashlib.sha256((ROOT/'app/ui/micro-physics.mjs').read_bytes()).hexdigest()
    for run in (original,revised,additional,fine):
        if any(r['model_sha256']!=model_hash for r in run['results']):raise ValueError('Mixed controller builds')
    summary=dict(date='2026-10-22',model_sha256=model_hash,baseline=totals(base),controller_only=totals(original['results']),
                 revised=totals(revised['results']),additional_seeds=totals(additional['results']),
                 timestep_2ms=totals(fine['results']),seeds=seeds,models=[],
                 real_hardware_tested=False,recognition_tested=False,full_8gb_stack_tested=False,
                 physics_process_peak_rss_mib=additional['physics_process_peak_rss_mib'],
                 scope_note='The 95% target applies to simulated flight completion. Five designs have explicitly revised, unmeasured and unpriced battery banks. The unchanged 2:1 reserve screen passes '+str(totals(revised['results'])['engineering_passed'])+'/42. Micro 90 still fails motor damage; the original Pluto-pack Scout still fails low battery. Ideal external pose; no hardware, vision or full 8 GB stack qualification.')
    for before,after,name in MODELS:
        rows=[r for r in revised['results'] if r['configuration']==after]
        more=[r for r in additional['results'] if r['configuration']==after]
        summary['models'].append(dict(name=name,original_id=before,revised_id=after,revision=rows[0]['configuration_revision'],
            mass_g=rows[0]['mass_g'],baseline=sum(r['flight_passed'] for r in base if r['configuration']==before),
            controller_only=sum(r['flight_passed'] for r in original['results'] if r['configuration']==before),
            revised=sum(r['flight_passed'] for r in rows),additional_passed=sum(r['flight_passed'] for r in more),additional_total=len(more),
            failures=[r['scenario'] for r in rows if not r['flight_passed']],
            max_yaw_rate_rad_s=max(r['controller']['max_yaw_rate_rad_s'] for r in more)))
    summary['flight_target_met']=all(summary[key]['passed']/summary[key]['total']>=.95 for key in ('revised','additional_seeds','timestep_2ms'))
    write(ROOT/'docs/component-controller-comparison.json',summary)
    write(ROOT/'docs/component-controller-trials.json',dict(controller_only=original,revised=revised,additional_seeds=additional,timestep_2ms=fine))
    inputs=load(args.runs/'verified-revised/inputs.json')
    assemblies={t['snapshot']['assembly']['sha256']:t['snapshot']['assembly'] for t in inputs}
    write(ROOT/'docs/component-controller-inputs.json',dict(model_sha256=model_hash,assemblies=list(assemblies.values()),scenarios=SCENARIOS,seeds=[137]+seeds,dt_s=.004))
    print(json.dumps({k:summary[k] for k in ('flight_target_met','controller_only','revised','additional_seeds','timestep_2ms')}))


if __name__=='__main__':main()
