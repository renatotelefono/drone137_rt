"""Repeatable accelerated geometry tests. No camera, inference or flight dynamics."""
import argparse
import json
import math
from pathlib import Path
import platform
import time

from app.recon import Recon


def episode(seed, scenario='room', variant='baseline'):
    recon = Recon(None, Path('.local/data/runs'))
    recon.configure(seed, scenario, variant)
    now, started = 0., time.monotonic()
    result = {'seed': seed, 'scenario': scenario, 'variant': variant, 'returned': False}
    try:
        for step in range(1800):
            now = step*.1
            recon.sense(now)
            recon.return_requested = now >= 60
            if recon.return_requested and math.dist(recon.pose[:2], [1.25,1.25]) < .1:
                result['returned'] = True
                break
            if not recon.move(.1, now):
                if recon.return_requested:
                    raise RuntimeError('No return route')
                # No reachable frontier remains; go home immediately.
                for _ in range(1200):
                    now += .1
                    recon.sense(now)
                    recon.return_requested = True
                    if math.dist(recon.pose[:2], [1.25,1.25]) < .1:
                        result['returned'] = True
                        break
                    if not recon.move(.1, now):
                        raise RuntimeError('No return route')
                break
        if not result['returned']:
            result['failure'] = 'Mission deadline'
    except (RuntimeError, ValueError) as error:
        result['failure'] = str(error)
    return {**result, 'distance_m': recon.distance, 'minimum_clearance_m': recon.vehicle.minimum_clearance,
            'obstacle_stops': recon.stops, 'elapsed_sim_s': now,
            'observed_fraction': sum(v != 0 for v in recon.grid)/len(recon.grid),
            'wall_time_s': time.monotonic()-started}


def evaluate(count, output):
    results = []
    for seed in range(count):
        result = episode(seed)
        results.append(result)
        if seed % 10 == 0:
            print(json.dumps({'completed': len(results), 'total': count}), flush=True)
    for scenario in ('warehouse', 'rooms'):
        for variant in ('baseline', 'changed'):
            results.append(episode(137, scenario, variant))
    violations = [r for r in results if r['minimum_clearance_m'] < .12]
    failures = [r for r in results if r.get('failure')]
    report = {'suite': 'recon-geometry', 'host': platform.platform(),
              'real_inference': False, 'rendered_camera': False, 'real_flight_dynamics': False,
              'physical_transport': False, 'hardware_gate': 'blocked',
              'episodes': len(results), 'returned': sum(r['returned'] for r in results),
              'clearance_violations': len(violations), 'failures': len(failures),
              'passed': not violations and not failures, 'results': results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'results'}), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes', type=int, default=100, choices=range(1, 1001))
    parser.add_argument('--output', type=Path, default=Path('.local/validation/recon-geometry.json'))
    args = parser.parse_args()
    raise SystemExit(0 if evaluate(args.episodes, args.output) else 1)
