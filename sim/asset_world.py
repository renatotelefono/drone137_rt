"""Locally pinned CC0 props in the existing flight challenge.

Assembled room, not a scan of one building. Asset geometry and conservative
collision boxes share dimensions; the operator map remains known in advance.
"""
import hashlib
import json
import math
from pathlib import Path
from sim.hard_flight import build as procedural_scene

ASSET_ROOT = Path(__file__).resolve().parents[1]/'app/ui/real-assets'
MANIFEST = ASSET_ROOT/'manifest.json'


def verify_assets():
    manifest = json.loads(MANIFEST.read_text())
    for relative, record in manifest['files'].items():
        path = ASSET_ROOT/relative
        if not path.is_file() or path.stat().st_size != record['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'Missing or changed simulation asset: {relative}')
    return manifest


def place(prop, asset, manifest, scale=1., yaw=None):
    """Uniformly scale and rotate a grounded model; derive its enclosing AABB."""
    x, h, z = [v*scale for v in manifest['assets'][asset]['size_xyz_m']]
    yaw = prop.get('yaw', 0.) if yaw is None else yaw
    c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
    return {**prop, 'asset': asset, 'asset_scale': scale, 'yaw': yaw,
            'sx': x*c+z*s, 'sy': x*s+z*c, 'height': h}


def build(case):
    result = procedural_scene(case)
    manifest = json.loads(MANIFEST.read_text())
    props = []
    # Identify the authored search object by its construction position, solely
    # for rendering/scoring. Neither this ID nor the manifest reaches the models.
    target_xy = case.get('target_xy', [4.4, 8.9])
    for prop in result['obstacles']:
        kind = prop['kind']
        if kind == 'extinguisher' or (kind == 'red-canister' and [prop['x'], prop['y']] == target_xy):
            item = place(prop, 'korean_fire_extinguisher_01', manifest,
                         yaw=case.get('stress', {}).get('target_yaw_radians', 0.))
            # Present/absent twins share map bounds; absent keeps its plain canister.
            if kind != 'extinguisher':
                item.pop('asset'); item.pop('asset_scale')
            props.append(item)
        elif kind == 'stock-rack':
            for side in (-1, 1):
                props.append(place({**prop, 'id':prop['id']+str(side), 'x':prop['x']+side*.57},
                                   'steel_frame_shelves_01', manifest))
        elif kind == 'lab-bench':
            props.append(place(prop, 'industrial_storage_cart', manifest))
        elif kind == 'carton' and prop.get('detail') and prop['id'] != 'occluding-carton':
            size = manifest['assets']['wooden_crate_01']['size_xyz_m']
            scale = min(prop['sx']/size[0], prop['sy']/size[2], prop['height']/size[1])
            props.append(place(prop, 'wooden_crate_01', manifest, scale))
        else:
            props.append(prop)
    result.update(obstacles=props, title='CC0 workshop assets · native flight',
                  visual_revision=manifest['version'],
                  real_assets={'manifest':'/assets/real-assets/manifest.json',
                               'environment':'industrial_workshop_foundry', 'environment_intensity':.65,
                               'description':'Assembled room using CC0 models and photographed HDR lighting; not a reconstructed building.'})
    result['complexity'].update(props=len(props), ratio=len(props)/result['complexity']['baseline_props'],
                                imported_instances=sum('asset' in b for b in props))
    return result
