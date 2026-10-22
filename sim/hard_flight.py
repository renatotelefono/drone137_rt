"""Unseen parameter combinations for a frozen, finite native-flight challenge.

These remain authored synthetic rooms with a known floor plan, not scanned
buildings. Ground-truth target positions are used to construct/score the scene;
they do not choose search stations or enter either model's inputs.
"""
import copy
import json
from pathlib import Path
from sim.flight_world import scene

MANIFEST = Path(__file__).resolve().parents[1]/'config/native-hard-v1.json'


def cases():
    return json.loads(MANIFEST.read_text())['cases']


def build(case):
    result = scene(case['seed'], case['target'], case['condition'], case.get('target_xy'))
    stress = case.get('stress')
    if not stress:
        return result
    result['title'] = 'Unfamiliar workshop arrangement · native flight'
    result['visual_revision'] = 'hard-workshop-v1'
    result['challenge'] = copy.deepcopy(stress)
    # Move existing complete assets and their shared collision bounds together.
    for prop in result['obstacles']:
        if prop['kind'] in stress['furniture_xy']:
            prop['x'], prop['y'] = stress['furniture_xy'][prop['kind']]
        if prop['kind'] == 'extinguisher':
            prop['yaw'] = stress['target_yaw_radians']
    for i, position in enumerate(((1.1, 8.8), (10.6, 3.1))):
        result['obstacles'].append(dict(id=f'decoy-{i}', x=position[0], y=position[1],
            sx=.46, sy=.46, height=1.2, bottom=0., kind='red-canister'))
    # A low storage box occludes part of the west search area. Its position is
    # fixed for both members of the present/absent pair, never picked at runtime.
    if stress['partial_occlusion']:
        result['obstacles'].append(dict(id='occluding-carton', x=4.7, y=7.95,
            sx=.65, sy=.38, height=.64, bottom=0., kind='carton', detail=True,
            color='#aa8c60'))
    result['complexity']['props'] = len(result['obstacles'])
    result['complexity']['ratio'] = len(result['obstacles'])/result['complexity']['baseline_props']
    result['camera'].update(stress['camera'])
    result['illumination'] = stress['illumination']
    result['camera_mount']['pitch_degrees'] += stress['mount_pitch_error_degrees']
    result['wind']['mean_enu_m_s'] = stress['draft_enu_m_s']
    return result


def qualification(report, expected):
    """Count the planned denominator, including interrupted/unexecuted cases.

    No best-of-retries selection. Existing correctness remains visible separately
    from flight, resource, deadline and experiment integrity requirements.
    """
    runs = report['runs']
    passing = [r for r in runs if r['score']['correct'] and not r['error']
               and r['landed'] and r['flight']['envelope_violations'] == 0
               and r['wall_time_s'] <= 300 and r.get('physical_checks',{}).get('all_pass',True)]
    memory_ok = bool(report['memory']) and all(
        not m['budget_exceeded'] and not m['measurement_error'] for m in report['memory'].values())
    count = len(passing) if memory_ok and not report['errors'] else 0
    return {'planned_runs': expected, 'completed_runs': len(runs),
            'task_correct': sum(r['score']['correct'] for r in runs),
            'individual_runs_meeting_flight_and_task_gates': len(passing),
            'qualified_passes': count, 'pass_rate': count/expected if expected else 0,
            'all_pass': expected > 0 and count == expected,
            'false_location_claims': sum(r['score']['false_location_claim'] for r in runs),
            'memory_ok': memory_ok, 'per_run_deadline_s': 300,
            'interpretation': 'Observed performance on a frozen synthetic suite. Not a real-world reliability estimate. '
                'Absent cases require a completed search with no location claim; unresolved does not prove absence.'}
