"""Seeded environments and evaluator-only collision geometry."""
import math
import random

WIDTH, DEPTH = 12., 10.
SCENARIOS = {
    'room': 'Random obstacle room',
    'warehouse': 'Warehouse aisle',
    'rooms': 'Connected rooms',
    'workshop': 'Detailed workshop',
    'realism': 'Camera realism bay',
}

# Synthetic camera stress settings, not a calibration of a physical device.
CAMERA_CONDITIONS = {
    'nominal': dict(exposure=1., blur=.25, noise=.004, vignette=.18, distortion=-.025, glare=0., jitter=.0005),
    'dim': dict(exposure=.38, blur=.6, noise=.018, vignette=.28, distortion=-.025, glare=0., jitter=.0008),
    'glare': dict(exposure=1.1, blur=.35, noise=.006, vignette=.18, distortion=-.025, glare=.45, jitter=.0005),
    'motion': dict(exposure=.9, blur=2.2, noise=.009, vignette=.22, distortion=-.025, glare=0., jitter=.003),
}

CAMERAS = {
    'lean': {'id': 'lean', 'width': 320, 'height': 240, 'snapshot_width': 320,
             'snapshot_height': 240, 'vertical_fov': 75, 'fps': 10, 'bitrate': 400000},
    'detail': {'id': 'module3-720p', 'width': 1280, 'height': 720, 'snapshot_width': 960,
               'snapshot_height': 540, 'vertical_fov': 41, 'fps': 15, 'bitrate': 2500000,
               'reference': 'Approximate standard Camera Module 3 field of view; ideal optics'},
}


def world(seed, scenario='room', variant='baseline', condition='nominal'):
    if scenario not in SCENARIOS or variant not in ('baseline', 'changed'):
        raise ValueError('Unknown environment or scene variant')
    if condition not in CAMERA_CONDITIONS or (scenario != 'realism' and condition != 'nominal'):
        raise ValueError('Unknown or unsupported camera condition')
    rng = random.Random(seed)
    obstacles = []
    for _ in range(8):
        x, y = rng.uniform(2.8, 10.2), rng.uniform(1.3, 8.6)
        sx, sy = rng.uniform(.6, 1.4), rng.uniform(.6, 1.4)
        if any(abs(x-b['x']) < (sx+b['sx'])/2+.8 and abs(y-b['y']) < (sy+b['sy'])/2+.8 for b in obstacles):
            continue
        obstacles.append(dict(x=x, y=y, sx=sx, sy=sy, height=rng.uniform(1.6, 2.5)))
    checkpoints = []
    if scenario != 'room':
        # A generous shared aisle keeps the first patrol finite and inspectable.
        obstacles = [
            dict(x=3.5, y=7.5, sx=2., sy=1., height=2.2, kind='shelf'),
            dict(x=8.5, y=7.5, sx=2., sy=1., height=2.2, kind='shelf'),
            dict(x=9.5, y=1.7, sx=1., sy=1., height=1.8, kind='crate'),
        ]
        if scenario == 'rooms':
            obstacles += [dict(x=6., y=y, sx=.2, sy=sy, height=3., kind='wall')
                          for y, sy in ((1.5, 3.), (7.5, 5.))]
        else:
            obstacles += [dict(x=6., y=y, sx=.6, sy=sy, height=2.5, kind='shelf')
                          for y, sy in ((1.5, 3.), (7.5, 5.))]
        if variant == 'changed':
            obstacles.append(dict(x=6., y=4., sx=.8, sy=1.4, height=2., kind='crate'))
        # These are operator-defined inspection locations, not labels supplied to AI.
        checkpoints = [
            {'id': 'entry', 'position': [2.25, 1.25], 'yaw': .6},
            {'id': 'passage', 'position': [4.25, 4.25], 'yaw': 0.},
            {'id': 'far-room', 'position': [8.25, 4.25], 'yaw': math.pi/2},
        ]
    if scenario in ('workshop', 'realism'):
        obstacles = [
            dict(x=2.5, y=7.7, sx=2.3, sy=1., height=2.4, kind='stock-rack'),
            dict(x=8.5, y=7.6, sx=2.5, sy=1.2, height=2., kind='workbench'),
            dict(x=10.5, y=1.8, sx=1.4, sy=1.3, height=1.4, kind='drums'),
            dict(x=.6, y=4.9, sx=.7, sy=1.2, height=1.35, kind='tool-cabinet'),
            dict(x=10.7, y=5.3, sx=.7, sy=.8, height=1.6, kind='hand-truck'),
            dict(x=11.5, y=8.9, sx=.7, sy=.7, height=1.8, kind='plant'),
            dict(x=3.7, y=9.3, sx=.5, sy=.5, height=1.5, kind='extinguisher'),
            *[dict(x=6., y=y, sx=.25, sy=sy, height=3., kind='partition')
              for y, sy in ((1.5, 3.), (7.5, 5.))],
        ]
        if variant == 'changed':
            obstacles.append(dict(x=6., y=4., sx=.8, sy=1.4, height=2., kind='pallet-load'))
        checkpoints.insert(1, {'id': 'stock-rack', 'position': [2.25,4.25], 'yaw': math.pi/2})
        checkpoints[0]['yaw'] = 1.35
        # A narrower physical-camera view needs more standoff to see the doorway.
        checkpoints[2]['position'] = [3.25,4.25]
    if scenario == 'realism':
        for b in obstacles:
            if b['kind'] == 'workbench':
                b['kind'] = 'lab-bench'
        obstacles += [dict(x=2.5, y=2.8, sx=1.7, sy=.8, height=1.5, kind='bottle-table'),
                      dict(x=10.5, y=7.6, sx=.8, sy=.8, height=1.25, kind='office-chair'),
                      dict(x=8.7, y=1.9, sx=.8, sy=.8, height=.8, kind='safety-cones')]
        checkpoints[0]['yaw'] = math.pi/2
        for checkpoint in checkpoints:
            if checkpoint['id'] == 'passage':
                checkpoint['inspection_task'] = 'passage'
        # Authored inspection poses are mission inputs; object names never reach the model.
        checkpoints.insert(3, {'id':'equipment', 'position':[8.25,4.25], 'yaw':-.8})
        checkpoints.append({'id':'seating', 'position':[9.25,5.25], 'yaw':math.atan2(2.35,1.25)})
    camera = dict(CAMERAS['detail' if scenario in ('workshop','realism') else 'lean'])
    if scenario == 'realism':
        camera.update(id='inspection-720p', effects=dict(CAMERA_CONDITIONS[condition]),
                      condition=condition, jpeg_quality=.82, pitch_degrees=-10,
                      reference='Synthetic lens/exposure/noise/blur; not calibrated to hardware')
    return {"seed": seed, "scenario": scenario, "title": SCENARIOS[scenario],
            "variant": variant, "width": WIDTH, "depth": DEPTH, "height": 3,
            "obstacles": obstacles, "checkpoints": checkpoints,
            "lighting": .85+rng.random()*.3,
            "condition": condition,
            "visual_revision": 'realism-v1' if scenario == 'realism' else 'workshop-v1' if scenario == 'workshop' else 'blocks-v1',
            "camera": camera}


def clearance(scene, x, y):
    value = min(x, y, WIDTH-x, DEPTH-y)
    for b in scene["obstacles"]:
        dx, dy = abs(x-b['x'])-b['sx']/2, abs(y-b['y'])-b['sy']/2
        distance = math.hypot(max(0, dx), max(0, dy)) if dx > 0 or dy > 0 else max(dx, dy)
        value = min(value, distance)
    return value


def ray_distance(scene, x, y, angle, maximum=3.):
    """Intersect the world boundary and solid boxes; emulate 4 cm range bins."""
    dx, dy = math.cos(angle), math.sin(angle)
    candidates = []
    for position, direction, bound in ((x, dx, WIDTH), (y, dy, DEPTH)):
        if abs(direction) > 1e-12:
            candidates.append(((bound if direction > 0 else 0)-position)/direction)
    for box in scene['obstacles']:
        near, far = -math.inf, math.inf
        for position, direction, center, size in ((x, dx, box['x'], box['sx']), (y, dy, box['y'], box['sy'])):
            low, high = center-size/2, center+size/2
            if abs(direction) < 1e-12:
                if not low <= position <= high:
                    far = -math.inf
                    break
            else:
                first, last = sorted(((low-position)/direction, (high-position)/direction))
                near, far = max(near, first), min(far, last)
        if far >= max(near, 0):
            candidates.append(max(0., near))
    distance = min(candidates, default=maximum+1)
    hit = distance <= maximum
    return min(maximum, max(.04, math.ceil(distance/.04-1e-10)*.04)), hit
