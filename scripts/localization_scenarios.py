"""Authored simulation and evaluator labels, never passed to either model."""
import math
from sim.recon_world import world, clearance

VIEWS = [
    [1.25, 1.25, 1.4, math.pi/2],
    [2.5, 4.8, 1.4, 2.1],
    [4.35, 5.8, 1.4, 1.6],
    [8.0, 4.1, 1.4, -1.0],
    [8.5, 4.9, 1.4, .75],
]


def cases():
    specifications = [
        ('development-west', 731, [1.0, 7.3], 'nominal', 'development'),
        ('north-clutter', 941, [4.4, 8.9], 'nominal', 'evaluation'),
        ('east-clutter', 1203, [10.1, 6.4], 'nominal', 'evaluation'),
        ('west-low-light', 1619, [1.0, 7.3], 'dim', 'evaluation'),
        ('north-motion-blur', 1807, [4.4, 8.9], 'motion', 'evaluation'),
        ('target-absent', 2053, None, 'nominal', 'evaluation'),
    ]
    result = []
    for name, seed, target, condition, split in specifications:
        scene = world(seed, 'realism', 'baseline', condition)
        scene['obstacles'] = [b for b in scene['obstacles'] if b['kind'] != 'extinguisher']
        if target:
            scene['obstacles'].append(dict(x=target[0], y=target[1], sx=.5, sy=.5,
                                           height=1.3, kind='extinguisher'))
        # Known pinhole intrinsics for triangulation; stress lighting and blur remain.
        scene['camera']['effects'].update(distortion=0, jitter=0)
        scene['checkpoints'] = []
        scene['visual_revision'] += '-localization-v1'
        views = []
        for i, pose in enumerate(VIEWS):
            confirmation = [pose[0]-.65*math.sin(pose[3]), pose[1]+.65*math.cos(pose[3]), *pose[2:]]
            for candidate in (pose, confirmation):
                if clearance(scene, *candidate[:2]) < .35:
                    raise ValueError(f'Inspection pose intersects geometry: {name}, {candidate}')
            views.append({'id': f'view-{i}', 'pose': pose, 'confirmation_pose': confirmation})
        result.append({'id': name, 'split': split, 'scene': scene, 'views': views,
                       'truth_xy_m': target, 'tolerance_m': .75})
    return result
