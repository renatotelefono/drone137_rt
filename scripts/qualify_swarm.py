"""Swarm qualification: three aircraft on the shared airspace, N runs, every check at 90 % or better.

  python -m scripts.qualify_swarm --vehicle kinematic --runs 30
  python -m scripts.qualify_swarm --vehicle rapier --runs 10

Per run: separation kept (truth, in the air, at similar heights), every goal reached, every aircraft back home and
landed, the others held within the reaction time when one link went quiet, no envelope violation or contact, done in
time. Over the gate: peak memory of this process and its plant processes within the small-host budget, and the
deployment estimate for three real flights within it too. Results to docs/swarm-validation-<vehicle>.json.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.swarm_world import AIRCRAFT, BLACKOUT_S, RUN_LIMIT_S, run_swarm

GATE = {'min_separation_m': 1.2, 'home_error_m': .3, 'reaction_s': 2.5, 'run_limit_s': RUN_LIMIT_S, 'pass_rate': .9, 'small_budget_gib': 3.5}
GIB = 2**30


def score(run):
    flights = run['flights'].values()
    blackout = run['blackout']
    checks = {'separation_kept': run['min_separation_m'] is not None and run['min_separation_m'] >= GATE['min_separation_m'],
              'all_goals_reached': all(f['goals_reached'] == f['goals'] for f in flights),
              'all_landed_home': all(f['finished'] and f['home_error_m'] <= GATE['home_error_m'] and f['error'] is None for f in flights),
              'link_loss_hold': blackout.get('others_in_the_air', 0) == 0 or (blackout['reaction_s'] is not None and blackout['reaction_s'] <= GATE['reaction_s']),
              'no_envelope_violation': all(f['envelope_violations'] == 0 and not f['contacts'] for f in flights),
              'within_time': run['duration_s'] <= GATE['run_limit_s']}
    return checks, all(checks.values())


class MemoryPeak:
    """Resident memory of this process and everything it spawned, sampled while the runs go."""
    def __init__(self):
        import psutil
        self.psutil = psutil; self.peak = 0; self.samples = 0; self.task = None

    def sample(self):
        me = self.psutil.Process()
        total = me.memory_info().rss
        for child in me.children(recursive=True):
            try:
                total += child.memory_info().rss
            except Exception:
                pass
        self.peak = max(self.peak, total); self.samples += 1
        return total

    async def run(self):
        while True:
            self.sample()
            await asyncio.sleep(.5)


def deployment_estimate(aircraft=3):
    """Three real flights on one ground computer: model, console, and a flight with its estimator per aircraft."""
    baselines = json.loads((ROOT/'config/memory-baselines.json').read_text())
    c = baselines['components']
    model_gib = 1.68
    try:
        from app import memory_budget
        est = memory_budget.model_estimate(baselines['model']) if hasattr(memory_budget, 'model_estimate') else None
        if est and est.get('bytes'):
            model_gib = est['bytes']/GIB
    except Exception:
        pass
    per_aircraft = c['flight']['gib'] + c['vio']['gib']
    total = model_gib + c['console']['gib'] + aircraft*per_aircraft
    return {'model_gib': round(model_gib, 2), 'console_gib': c['console']['gib'], 'per_aircraft_gib': round(per_aircraft, 2), 'aircraft': aircraft,
            'total_gib': round(total, 2), 'verifier_off_gib': c['verifier']['gib'], 'fits_small_budget': total <= GATE['small_budget_gib']}


async def main(args):
    from sim.asset_world import build
    from sim.hard_flight import cases
    scene = build(cases()[0])
    assembly = None
    if args.vehicle == 'rapier':
        from app.components import Components
        assembly = Components(ROOT/'.local/data/components.sqlite3').assemble('scout-110-power-v2')
    log_folder = Path(args.logs).resolve(); log_folder.mkdir(parents=True, exist_ok=True)
    memory = MemoryPeak(); memory.task = asyncio.create_task(memory.run())
    runs = []; started = time.time()
    for i in range(args.runs):
        seed = args.seed_base + i
        folder = log_folder/f'run-{seed}'; folder.mkdir(parents=True, exist_ok=True)
        run = await run_swarm(seed, scene, vehicle=args.vehicle, folder=folder, assembly=assembly, speedup=args.speedup)
        run['checks'], run['passed'] = score(run)
        (folder/'run.json').write_text(json.dumps(run, indent=1, default=float))
        runs.append(run)
        print(json.dumps({'seed': seed, 'passed': run['passed'], 'failed': [k for k, v in run['checks'].items() if not v],
                          'min_separation_m': None if run['min_separation_m'] is None else round(run['min_separation_m'], 2),
                          'reaction_s': run['blackout']['reaction_s'], 'holds': run['holds_total'], 'duration_s': round(run['duration_s'], 1),
                          'memory_gib': round(memory.sample()/GIB, 2)}), flush=True)
    memory.task.cancel()
    rates = {k: sum(r['checks'][k] for r in runs)/len(runs) for k in runs[0]['checks']}
    peak_gib = memory.peak/GIB; estimate = deployment_estimate(3)
    report = {'date': time.strftime('%Y-%m-%d'), 'vehicle': args.vehicle, 'runs': len(runs), 'passed': sum(r['passed'] for r in runs),
              'gate': GATE, 'pass_rates': rates, 'all_pass_rate': sum(r['passed'] for r in runs)/len(runs),
              'memory': {'peak_gib': round(peak_gib, 2), 'samples': memory.samples, 'within_small_budget': peak_gib <= GATE['small_budget_gib'],
                         'deployment_estimate': estimate},
              'summary': {'min_separation_m': min(r['min_separation_m'] for r in runs if r['min_separation_m'] is not None),
                          'max_reaction_s': max((r['blackout']['reaction_s'] or 0) for r in runs),
                          'mean_duration_s': sum(r['duration_s'] for r in runs)/len(runs), 'max_duration_s': max(r['duration_s'] for r in runs),
                          'holds_per_run': sum(r['holds_total'] for r in runs)/len(runs),
                          'give_way_total': sum(f['gave_way'] for r in runs for f in r['flights'].values()),
                          'blackout_aircraft': {k: sum(1 for r in runs if r['blackout']['aircraft'] == k) for k in AIRCRAFT}},
              'wall_time_s': time.time() - started, 'logs': str(log_folder), 'runs_detail': runs,
              'scope': ('Three aircraft on the shared airspace in the benchmark room, flying through its one doorway; positions reported as '
                        'estimates, separation scored on the truth. The plant does not model aircraft-to-aircraft collision; separation is the '
                        'measure. Not a hardware qualification.')}
    report['accepted'] = (all(v >= GATE['pass_rate'] for v in rates.values()) and report['all_pass_rate'] >= GATE['pass_rate']
                          and report['memory']['within_small_budget'] and estimate['fits_small_budget'])
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=1, default=float) + '\n')
    print(json.dumps({'accepted': report['accepted'], 'passed': report['passed'], 'runs': len(runs), 'pass_rates': rates,
                      'peak_memory_gib': report['memory']['peak_gib'], 'deployment_gib': estimate['total_gib'], 'summary': report['summary']}, default=float), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--vehicle', choices=('kinematic', 'rapier'), default='kinematic')
    parser.add_argument('--runs', type=int, default=30)
    parser.add_argument('--seed-base', type=int, default=3000)
    parser.add_argument('--speedup', type=float, default=None, help='kinematic only: throttle to this multiple of the wall clock; default as fast as possible')
    parser.add_argument('--output', default=None)
    parser.add_argument('--logs', default=str(ROOT/'.local/validation/swarm'))
    args = parser.parse_args()
    args.output = args.output or str(ROOT/f'docs/swarm-validation-{args.vehicle}.json')
    sys.exit(asyncio.run(main(args)))
