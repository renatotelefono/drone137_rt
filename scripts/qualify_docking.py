"""Docking qualification: N dockings from the return gate's error distribution, scored against the gate.

Vehicles: `kinematic` (first-order model, seconds per run) or `rapier` (the service-owned
micro-physics plant in real time, about a minute per run). The tag camera, dock electronics
and controller are the same in both. Results go to docs/docking-validation.json and the
per-run logs to a folder of the caller's choice.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dock_tags import load_geometry
from sim.dock_world import DockSimulation, DockWorld, Estimator, RapierDockVehicle, beside, kinematic_docking, return_gate_start

GATE = {'touchdown_m': .02, 'yaw_deg': 5., 'stand_contacts': 0, 'estimate_reset_m': .02, 'attempts': 1, 'other_dock_clearance_m': .3}


def score(run):
    t = run['touchdown']
    checks = {'docked': run['outcome'] == 'docked',
              'touchdown_within_20_mm': abs(t['f_m']) <= GATE['touchdown_m'] and abs(t['l_m']) <= GATE['touchdown_m'],
              'yaw_within_5_deg': abs(t['yaw_deg']) <= GATE['yaw_deg'],
              'no_stand_contact': run['stand_contacts'] == GATE['stand_contacts'],
              'estimate_reset_within_20_mm': run['estimate_error_after_reset_m'] is not None and run['estimate_error_after_reset_m'] <= GATE['estimate_reset_m'],
              'first_attempt': run['attempts'] == GATE['attempts']}
    if run.get('other_docks'):
        checks['clear_of_other_docks'] = all(o['distance_m'] >= GATE['other_dock_clearance_m'] for o in run['other_docks'])
    return checks, all(checks.values())


def two_docks(base, seed, left_m=.6):
    """The commanded dock and the other one, left_m to the left of dock 0 (negative: to its right), alternating with the seed:
    (own world, [other spec]). The flight envelope keeps 0.35 m from walls, so a second dock goes on the room side of the first."""
    origin1, yaw1, _ = beside(base, left_m)
    worlds = {0: base, 1: DockWorld(base.geometry, 1, origin1, yaw1)}
    commanded = seed % 2
    own, other = worlds[commanded], worlds[1 - commanded]
    return own, [(tuple(float(v) for v in other.origin), float(other.yaw), other.index)]


async def kinematic_run(seed, geometry, camera, log_folder, docks=1):
    if docks == 2:
        own, others = two_docks(DockWorld(geometry, 0, (1.25, 1.25, 0.), 0.), seed)
        side = 1. if others[0][0][1] > own.origin[1] else -1.    # start on the other dock's side, so it is in view from the first frame
        sim, error = kinematic_docking(seed, geometry, camera, origin=tuple(float(v) for v in own.origin), yaw=own.yaw, index=own.index,
                                       others=others, start_d=(-1.6, side*.6, .9))
    else:
        sim, error = kinematic_docking(seed, geometry, camera)
    log = []
    result = await sim.phase(log).run()
    return finish(seed, sim, error, result, log, log_folder, {'engine': 'first-order kinematic model'})


async def rapier_run(seed, geometry, camera, log_folder, docks=1):
    from adapters.rapier_drone import RapierDrone
    from app.components import Components
    from sim.asset_world import build
    from sim.hard_flight import cases
    scene = build(cases()[0])
    assembly = Components(ROOT/'.local/data/components.sqlite3').assemble('scout-110-power-v2')
    folder = log_folder/f'run-{seed}'; folder.mkdir(parents=True, exist_ok=True)
    flight = RapierDrone(assembly, scene, folder, seed)
    rng = np.random.default_rng(seed)
    error = return_gate_start(rng, geometry)
    origin = (scene['home'][0], scene['home'][1], 0.)
    world = DockWorld(geometry, 0, origin, math.pi)   # forward points into the room; the stand sits between the dock and the wall
    others = (); lateral = .6; via = None
    if docks == 2:
        # Two docks in the bay along the south wall between the bottle table and the partition (x 4.0 to 5.5 m clear of the
        # 0.35 m envelope): dock 0 at x 4.45, dock 1 beside it at x 5.05, both facing the wall. The mission's last waypoint is drawn
        # within 0.3 m sideways, as a planner would in a bay this wide, and the flight goes round the table first.
        world, others = two_docks(DockWorld(geometry, 0, (4.45, .9, 0.), -math.pi/2), seed)
        origin = tuple(float(v) for v in world.origin); lateral = .3; via = [4.4, 1.2, .9]
    try:
        await flight.start()
        await flight.takeoff()
        away_d = (-1.6, float(rng.uniform(-lateral, lateral)), .9)
        away_w, away_yaw = world.to_world(away_d, float(rng.uniform(-.5, .5)))
        if via is not None:
            await flight.settle([*via, away_yaw])
        await flight.settle([*away_w, away_yaw])
        estimator = Estimator(offset=tuple(error), seed=seed)
        sim = DockSimulation(geometry, camera, lambda w, e: RapierDockVehicle(flight, w, e), estimator, origin=origin, yaw=world.yaw, index=world.index,
                             seed=seed, others=others)
        log = []
        result = await sim.phase(log).run()
        result['flight'] = flight.metrics()
        return finish(seed, sim, error, result, log, log_folder, {'engine': result['flight']['engine'], 'away_point_dock_frame': list(away_d),
                      'flight': {k: v for k, v in result['flight'].items() if k != 'telemetry'}})
    finally:
        await flight.close()


def finish(seed, sim, error, result, log, log_folder, extra):
    truth = sim.truth()
    est_p, est_yaw = sim.vehicle.estimate()
    truth_p, truth_yaw = sim.vehicle.truth()
    run = {'seed': seed, 'outcome': result['outcome'], 'attempts': result['attempts'], 'states': [s['state'] for s in result['states']],
           'drawn_error': {'x_m': float(error[0]), 'y_m': float(error[1]), 'z_m': float(error[2]), 'yaw_deg': math.degrees(float(error[3]))},
           'touchdown': {'f_m': truth['f_m'], 'l_m': truth['l_m'], 'yaw_deg': truth['yaw_deg'], 'landed': truth['landed']},
           'stand_contacts': truth['stand_contacts'], 'frames': result['frames'], 'detections': result['detections'],
           'duration_s': result['duration_s'], 'dock_status': result.get('dock_status'),
           'estimate_error_after_reset_m': float(np.linalg.norm((est_p - truth_p)[:2])) if result.get('estimate_reset') else None,
           'estimate_height_error_after_reset_m': float(est_p[2] - truth_p[2]) if result.get('estimate_reset') else None,
           'error': result.get('error'), 'commanded_dock': sim.world.index, 'other_docks': truth.get('other_docks', []), **extra}
    run['checks'], run['passed'] = score(run)
    (log_folder/f'run-{seed}.json').write_text(json.dumps({'run': run, 'log': log}, indent=1, default=float))
    return run


async def main(args):
    geometry = load_geometry()
    from sim.asset_world import build
    from sim.hard_flight import cases
    camera = build(cases()[0])['camera']
    log_folder = Path(args.logs).resolve(); log_folder.mkdir(parents=True, exist_ok=True)
    runs = []
    started = time.time()
    for i in range(args.runs):
        seed = args.seed_base + i
        run = await (rapier_run if args.vehicle == 'rapier' else kinematic_run)(seed, geometry, camera, log_folder, args.docks)
        runs.append(run)
        print(json.dumps({'seed': seed, 'outcome': run['outcome'], 'attempts': run['attempts'], 'touchdown_mm': [round(run['touchdown']['f_m']*1000, 1), round(run['touchdown']['l_m']*1000, 1)],
                          'yaw_deg': round(run['touchdown']['yaw_deg'], 2), 'passed': run['passed'], 'duration_s': round(run['duration_s'], 1)}), flush=True)
    passed = sum(r['passed'] for r in runs)
    report = {'date': time.strftime('%Y-%m-%d'), 'vehicle': args.vehicle, 'docks': args.docks, 'runs': len(runs), 'passed': passed,
              'accepted': passed == len(runs) and len(runs) >= (10 if args.docks == 2 and args.vehicle == 'rapier' else 20),
              'gate': GATE, 'camera': {k: camera[k] for k in ('width', 'height', 'vertical_fov', 'effects', 'jpeg_quality', 'latency_ms', 'drop_every_n', 'pitch_degrees')},
              'geometry': geometry['geometry'], 'procedure': geometry['procedure'],
              'summary': {'max_touchdown_mm': max(max(abs(r['touchdown']['f_m']), abs(r['touchdown']['l_m'])) for r in runs)*1000,
                          'max_yaw_deg': max(abs(r['touchdown']['yaw_deg']) for r in runs),
                          'max_estimate_error_after_reset_mm': max((r['estimate_error_after_reset_m'] or 0) for r in runs)*1000,
                          'attempts': [r['attempts'] for r in runs], 'mean_duration_s': sum(r['duration_s'] for r in runs)/len(runs),
                          'stand_contacts': sum(r['stand_contacts'] for r in runs),
                          'min_distance_to_other_dock_m': min((o['distance_m'] for r in runs for o in r['other_docks']), default=None),
                          'landings_per_dock': {str(i): sum(1 for r in runs if r['commanded_dock'] == i) for i in sorted({r['commanded_dock'] for r in runs})}},
              'wall_time_s': time.time()-started, 'logs': str(log_folder), 'runs_detail': runs,
              'scope': 'Simulated dock A with the benchmark camera optics, latency and frame drops; the docking controller sees frames, estimate and dock status only. Not a hardware qualification.'}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=1, default=float) + '\n')
    print(json.dumps({'accepted': report['accepted'], 'passed': passed, 'runs': len(runs), 'summary': report['summary']}, default=float), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--vehicle', choices=('kinematic', 'rapier'), default='kinematic')
    parser.add_argument('--docks', type=int, choices=(1, 2), default=1, help='2: a second dock 0.6 m to the left with its own tags; the commanded dock alternates')
    parser.add_argument('--runs', type=int, default=20)
    parser.add_argument('--seed-base', type=int, default=1000)
    parser.add_argument('--output', default=str(ROOT/'docs/docking-validation.json'))
    parser.add_argument('--logs', default=str(ROOT/'.local/validation/docking'))
    sys.exit(asyncio.run(main(parser.parse_args())))
