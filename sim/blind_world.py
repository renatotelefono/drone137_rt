"""Privileged simulator construction/scoring. Never imported by the explorer."""
import copy
import random
import math
from sim.asset_world import build
from sim.hard_flight import cases


def scene(seed):
    rng = random.Random(seed)
    case = copy.deepcopy(cases()[0])
    case.update(seed=seed, condition='nominal', target=True)
    case.pop('stress', None)
    result = build(case)
    # Entire furniture items and collision boxes move together. Peripheral
    # clutter/assets are retained. These layouts are unknown to the controller.
    moves = {'stock-rack': (rng.uniform(4.5, 5.5), rng.uniform(6, 7)),
             'lab-bench': (rng.uniform(7, 8), rng.uniform(2.5, 3.5))}
    anchors = {kind: next((b['x'], b['y']) for b in result['obstacles'] if b['kind'] == kind) for kind in moves}
    for b in result['obstacles']:
        if b['kind'] in moves:
            # Preserve the spacing of repeated furniture instead of stacking it.
            x, y = moves[b['kind']]
            ax, ay = anchors[b['kind']]
            b['x'], b['y'] = x+b['x']-ax, y+b['y']-ay
        if b['kind'] == 'extinguisher':
            b['x'], b['y'] = rng.uniform(6, 9), rng.uniform(7.7, 8.6)
    result['home'] = [1.3, 1.3]
    result['title'] = 'Unknown workshop / blind exploration'
    result['navigation_mode'] = 'blind-camera-imu'
    # A level forward camera retains floor texture in the lower half of this
    # wide lens while observing the airspace/upper surfaces needed to certify
    # a forward flight corridor. Mounting remains a provisional build choice.
    result['camera_mount'] = {'pitch_degrees': 0, 'body_offset_flu_m': [.035, 0, .015]}
    result['camera']['vertical_fov'] = 100
    camera = result['camera']
    focal = camera['height']/(2*math.tan(math.radians(camera['vertical_fov']/2)))
    camera['optics'] = {'width': camera['width'], 'height': camera['height'],
                        'fx': focal, 'fy': focal, 'cx': camera['width']/2, 'cy': camera['height']/2,
                        'distortion': [-.025, 0, 0, 0, 0], 'exposure_ms': 4, 'rolling_shutter_ms': 5,
                        'jitter_ms': 0, 'drop_probability': 0, 'burst_frames': 0}
    result['camera']['reference'] += '; provisional wide-angle lens for simultaneous floor and forward visibility'
    result['wind']['mean_enu_m_s'] = [.08, .03, 0]
    result['calibration_note'] = 'First blind-mapping baseline; nominal camera and mild draft, not the prior hard-flight qualification'
    return result
