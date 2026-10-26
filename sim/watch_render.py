"""Staged object events rendered in the CC0 workshop from fixed dock poses, for the perched-watch gate.

The same service-owned Three.js camera the missions fly through renders a perched camera's view
before and after an event: an extinguisher, canister, bin, case, cone or chair removed, added or
moved, a full-size crate set down, the stock cart rolling through, the light dimmed. Real
textures, shadows and the camera's own noise, blur and frame drops. Nothing here is a person.

The dock sits at table or shelf height (0.75 or 1.05 m): the camera is pitched 9 degrees down,
so a floor-level dock sees mostly floor. A perch is chosen in free space, 2 to 3.5 m from the
object, with the object's foot and top inside the camera's field and nothing standing between.

  python -m sim.watch_render --output .local/validation/watch-rendered --seeds 4
"""
import argparse
import asyncio
import copy
import json
import math
from pathlib import Path
import shutil
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EVENTS = ('object_removed', 'object_added', 'object_moved', 'cart', 'lighting')
RATE = 2.5
BEFORE, AFTER = 15, 25
HEIGHTS = (.75, 1.05)
OBJECT_KINDS = ('extinguisher', 'red-canister', 'tool-case', 'storage-bin', 'paint-tin', 'safety-cones', 'office-chair')
PITCH_DEGREES, VERTICAL_FOV_DEGREES = -9., 41.   # the inspection camera as mounted
CLEARANCE_M = .35                                 # perch to any obstacle at its height
MOUNT_Z_M = .02
CART_REACH_M = 1.2
DIMMED = .3                                       # the lights mostly off: lamps and the HDR environment together


class PerchedPose:
    """What the renderer asks of a vehicle: a scene and a snapshot with truth. This one never moves."""
    def __init__(self, scene, position, yaw, cart=None):
        self.scene, self.position, self.yaw, self.cart = scene, list(position), float(yaw), cart
        self.started = time.time()

    def snapshot(self, include_trail=True):
        t = time.time() - self.started
        cart = None
        if self.cart:
            x0, y0, x1, y1, duration = self.cart
            f = min(1., max(0., t/duration)); cart = [x0 + (x1-x0)*f, y0 + (y1-y0)*f, 0.]
        truth = {'position': self.position, 'quaternion': [0., 0., math.sin(self.yaw/2), math.cos(self.yaw/2)], 'sim_time': t,
                 'cart_position': cart}
        return {'truth': truth, 'estimated': {'position': self.position, 'quaternion': truth['quaternion']}, 'wall_time': time.time(),
                'speed': 0., 'angular_speed': 0., 'phase': 'perched', 'message': 'Perched camera', 'trail': []}


def candidates(scene):
    """Floor-standing things a person would plausibly take, bring or move."""
    return [p for p in scene['obstacles'] if p['kind'] in OBJECT_KINDS and p.get('bottom', 0) < .1 and .3 <= p['height'] <= 1.3]


def cart_box(scene, x=None, y=None, reach_x=0., reach_y=0.):
    """The stock cart's box at a point, or the box it sweeps along a path (reach either side of the point)."""
    c = scene['moving_actor']['center']; w, d, h = scene['moving_actor']['size']
    return {'id': 'cart', 'kind': 'cart', 'x': c[0] if x is None else x, 'y': c[1] if y is None else y,
            'sx': w + 2*reach_x, 'sy': d + 2*reach_y, 'bottom': 0., 'height': h}


def cart_path(rng, scene, obstacles):
    """A straight 2.4 m run across open floor, along x or y: (centre, along_x, swept box); None if the room has none."""
    for _ in range(300):
        cx, cy = float(rng.uniform(1.5, scene['width'] - 1.5)), float(rng.uniform(1.5, scene['depth'] - 1.5)); along_x = bool(rng.random() < .5)
        swept = cart_box(scene, cx, cy, CART_REACH_M if along_x else 0., 0. if along_x else CART_REACH_M)
        if footprint_free(swept, obstacles, .2):
            return (cx, cy), along_x, swept
    return None, None, None


def inside(x, y, z, box, margin=0.):
    return (abs(x - box['x']) <= box['sx']/2 + margin and abs(y - box['y']) <= box['sy']/2 + margin
            and box.get('bottom', 0.) - margin <= z <= box.get('bottom', 0.) + box['height'] + margin)


def clear_spot(x, y, z, obstacles, margin=CLEARANCE_M):
    """Nothing within the margin of the perch at the perch's height."""
    return not any(inside(x, y, z, box, margin) for box in obstacles)


def line_clear(a, b, obstacles, step=.05):
    """No obstacle box between two points."""
    n = max(2, int(math.dist(a, b)/step))
    for i in range(1, n):
        t = i/n; x, y, z = (a[k] + (b[k]-a[k])*t for k in range(3))
        if any(inside(x, y, z, box) for box in obstacles):
            return False
    return True


def sees(perch, target, obstacles, heights=(.05, None)):
    """The target's foot and top (or the given heights above its bottom) are inside the camera's vertical field
    and nothing stands in the way."""
    cam = (perch[0], perch[1], perch[2] + MOUNT_Z_M)
    d = math.hypot(target['x'] - cam[0], target['y'] - cam[1])
    others = [b for b in obstacles if b['id'] != target['id']]
    for z in (target.get('bottom', 0.) + (target['height'] - .05 if h is None else h) for h in heights):
        off_axis = math.degrees(math.atan2(z - cam[2], d)) - PITCH_DEGREES
        if abs(off_axis) > VERTICAL_FOV_DEGREES/2 - 2 or not line_clear(cam, (target['x'], target['y'], z), others):
            return False
    return True


def perch_for(target, rng, scene, height, obstacles, distance=(2., 3.5)):
    """A dock position 2 to 3.5 m from the object, in free space, with the object in clear view; None if the room has none."""
    far = min(distance[1], max(distance[0], target['height']*10))
    for _ in range(300):
        d = rng.uniform(distance[0], far); a = rng.uniform(0, 2*math.pi)
        x, y = target['x'] + d*math.cos(a), target['y'] + d*math.sin(a)
        if not (.5 <= x <= scene['width'] - .5 and .5 <= y <= scene['depth'] - .5):
            continue
        perch = [float(x), float(y), height]
        if clear_spot(x, y, height, obstacles) and sees(perch, target, obstacles):
            return perch, float(math.atan2(target['y'] - y, target['x'] - x))
    return None, None


def footprint_free(prop, obstacles, margin):
    return not any(abs(prop['x'] - b['x']) < (prop['sx'] + b['sx'])/2 + margin and abs(prop['y'] - b['y']) < (prop['sy'] + b['sy'])/2 + margin
                   and b.get('bottom', 0.) < prop.get('bottom', 0.) + prop['height'] and b.get('bottom', 0.) + b['height'] > prop.get('bottom', 0.)
                   for b in obstacles if b['id'] != prop['id'])


def moved_copy(prop, rng, scene, obstacles, perch):
    """The object 0.6 to 1 m away along an axis, onto free floor the camera still sees."""
    for direction in rng.permutation(4):
        dx, dy = ((1, 0), (-1, 0), (0, 1), (0, -1))[direction]; step = float(rng.uniform(.6, 1.))
        moved = {**prop, 'x': float(prop['x'] + dx*step), 'y': float(prop['y'] + dy*step)}
        if not (.3 <= moved['x'] <= scene['width'] - .3 and .3 <= moved['y'] <= scene['depth'] - .3):
            continue
        if footprint_free(moved, obstacles, .05) and sees(perch, moved, obstacles):
            return moved, step
    return None, None


def spawn_crate(rng, scene, obstacles):
    """A full-size wooden crate set down on free floor, square to the room (the renderer checks a rotated model's
    bounds exactly, and only axis-aligned placements of this model pass), or None if there is no room."""
    from sim.asset_world import MANIFEST, place
    manifest = json.loads(MANIFEST.read_text())
    for _ in range(100):
        crate = place({'id': 'staged-crate', 'kind': 'carton', 'x': float(rng.uniform(1.5, scene['width'] - 1.5)),
                       'y': float(rng.uniform(1.5, scene['depth'] - 1.5)), 'bottom': 0., 'yaw': float(rng.choice([0., math.pi/2]))},
                      'wooden_crate_01', manifest)
        if footprint_free(crate, obstacles, .3):
            return crate
    return None


def staged(scene, event, seed, height=None):
    """(before scene, after scene, perch, yaw, cart before, cart after, truth) for one staged event."""
    rng = np.random.default_rng(seed)
    height = HEIGHTS[seed % 2] if height is None else height
    before, after = copy.deepcopy(scene), copy.deepcopy(scene)
    cart_before = cart_after = None; truth = {'category': event, 'kind': 'change', 'perch_height_m': height}
    if event == 'cart':
        for _ in range(20):
            centre, along_x, swept = cart_path(rng, scene, scene['obstacles'] + [cart_box(scene)])
            if centre is None:
                continue
            ends = [cart_box(scene, centre[0] + s*CART_REACH_M, centre[1]) if along_x else cart_box(scene, centre[0], centre[1] + s*CART_REACH_M) for s in (-1, 1)]
            present = scene['obstacles'] + [cart_box(scene)]
            perch, yaw = perch_for(cart_box(scene, *centre), rng, scene, height, present + [swept], distance=(2., 4.))
            if perch is not None and all(sees(perch, end, present) for end in ends):
                break
        else:
            raise RuntimeError(f'No perch sees a cart path for seed {seed}')
        truth.update(kind='motion', category='object_moved', object='rolling stock cart', object_xy=list(centre), object_height_m=ends[0]['height'],
                     distance_m=math.hypot(centre[0] - perch[0], centre[1] - perch[1]))
        cart_before = (ends[0]['x'], ends[0]['y'], ends[0]['x'], ends[0]['y'], 1.)
        cart_after = (ends[0]['x'], ends[0]['y'], ends[1]['x'], ends[1]['y'], AFTER/RATE*.6)
    else:
        props = candidates(scene); order = [int(i) for i in rng.permutation(len(props))]
        if event == 'object_added' and rng.random() < .5:
            crate = spawn_crate(rng, scene, scene['obstacles'] + [cart_box(scene)])
            if crate is not None:
                props = [crate] + props; order = [0] + [i + 1 for i in order]
        for i in order:
            prop = copy.deepcopy(props[i])
            present = [p for p in scene['obstacles'] if p['id'] != prop['id']] + [prop, cart_box(scene)]
            perch, yaw = perch_for(prop, rng, scene, height, present)
            if perch is None:
                continue
            others = [p for p in present if p['id'] not in (prop['id'], 'cart')]
            if event == 'object_removed':
                before['obstacles'], after['obstacles'] = others + [prop], others
            elif event == 'object_added':
                before['obstacles'], after['obstacles'] = others, others + [prop]
            elif event == 'object_moved':
                moved, step = moved_copy(prop, rng, scene, present, perch)
                if moved is None:
                    continue
                before['obstacles'], after['obstacles'] = others + [prop], others + [moved]; truth['moved_by_m'] = step
            else:
                truth['kind'] = 'lighting'
                after['illumination'] = {**scene['illumination'], 'ambient': scene['illumination']['ambient']*DIMMED,
                                         'directional': scene['illumination']['directional']*DIMMED}
                after['real_assets'] = {**scene['real_assets'], 'environment_intensity': scene['real_assets']['environment_intensity']*DIMMED}
            truth.update(object=prop.get('asset') or prop['kind'], object_id=prop['id'], object_xy=[prop['x'], prop['y']],
                         object_height_m=prop['height'], distance_m=math.hypot(prop['x'] - perch[0], prop['y'] - perch[1]))
            break
        else:
            raise RuntimeError(f'No perch sees any object for {event} seed {seed}')
    truth.update(perch=perch, yaw=yaw, at_index=BEFORE, at=BEFORE/RATE, fps=RATE, frames=BEFORE + AFTER)
    return before, after, perch, yaw, cart_before, cart_after, truth


async def capture_frames(scene, perch, yaw, cart, count, folder, start_index):
    from app.mission_camera import MissionCamera
    camera = MissionCamera(); work = folder/'render'; work.mkdir(parents=True, exist_ok=True)
    vehicle = PerchedPose(scene, perch, yaw, cart)
    try:
        await camera.open(vehicle, work)
    except Exception as exc:
        await camera.close()
        log = (work/'camera.log').read_text(errors='replace')[-400:] if (work/'camera.log').is_file() else ''
        raise RuntimeError(f'Renderer failed to open ({type(exc).__name__}): {log.strip()}') from exc
    try:
        await asyncio.sleep(1.5)   # let the first frames and the telemetry history settle
        for i in range(count):
            due = time.monotonic() + 1/RATE
            for attempt in range(5):
                try:
                    result = await camera.call(op='capture'); break
                except Exception:
                    if attempt == 4:
                        raise
                    await asyncio.sleep(.2)
            shutil.copyfile(work/result['image'], folder/f'{start_index + i:05}.jpg')
            await asyncio.sleep(max(0., due - time.monotonic()))
    finally:
        await camera.close()
    shutil.rmtree(work, ignore_errors=True)


def scenario_seed(event, seed):
    return 200 + 10*seed + EVENTS.index(event)


async def render(output, events, seeds, case_index=0):
    from sim.asset_world import build, verify_assets
    from sim.hard_flight import cases
    verify_assets()
    scene = build(cases()[case_index])
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    made = []
    for event in events:
        for seed in range(seeds):
            name = f'{event}-{seed}'; folder = output/name
            if (folder/'truth.json').is_file():
                made.append(name); continue
            shutil.rmtree(folder, ignore_errors=True); folder.mkdir(parents=True)
            before, after, perch, yaw, cart_before, cart_after, truth = staged(scene, event, scenario_seed(event, seed), HEIGHTS[seed % 2])
            started = time.time()
            await capture_frames(before, perch, yaw, cart_before, BEFORE, folder, 0)
            await capture_frames(after, perch, yaw, cart_after, AFTER, folder, BEFORE)
            truth.update(scene=cases()[case_index]['id'], rendered_at=time.strftime('%Y-%m-%d %H:%M'), seconds=time.time() - started)
            (folder/'truth.json').write_text(json.dumps(truth, indent=2))
            print(json.dumps({'scenario': name, 'object': truth.get('object'), 'perch_height_m': truth['perch_height_m'],
                              'distance_m': round(truth.get('distance_m', 0), 2), 'seconds': round(truth['seconds'])}), flush=True)
            made.append(name)
    return made


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT/'.local/validation/watch-rendered'))
    parser.add_argument('--seeds', type=int, default=4)
    parser.add_argument('--events', default=','.join(EVENTS))
    parser.add_argument('--case', type=int, default=0)
    args = parser.parse_args()
    asyncio.run(render(args.output, args.events.split(','), args.seeds, args.case))
