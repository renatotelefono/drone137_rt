"""Dock A for the Scout 110-B: funnel body with the charge-contact boss, and the tag backboard.

Writes ASCII STL files directly, so no OpenSCAD is needed; dock-a.scad holds the same
geometry for editing. Table at Z=0, pocket floor at Z=floor_z, +Y toward the backboard,
which is the Scout's forward (camera) side when docked.
"""
import json, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
N = 64  # points per ring; a multiple of 8 so the square corners are exact

P = dict(pocket=150., run=25., slope_deg=30., wall=3., floor_z=25., floor_t=3.,
         boss_d=8., boss_h=4., pin_d=2., pin_y=9., pin_travel=2.5,
         board_w=140., board_t=3., board_h=240., board_foot=100., tags=((40., 82.), (40., 142.), (60., 205.)),   # (size, centre above table); quiet zones must not overlap
         camera_z=82., camera_y=12., strip_x=14., strip_w=6., strip_l=28.)
P['top'] = P['floor_z'] + P['run']*math.tan(math.radians(P['slope_deg']))
P['opening'] = P['pocket'] + 2*P['run']
P['outer'] = P['opening'] + 2*P['wall']


def square(side, z, cx=0., cy=0.):
    pts = []
    for i in range(N):
        a = 2*math.pi*i/N; c, s = math.cos(a), math.sin(a); m = max(abs(c), abs(s))
        pts.append((cx + side/2*c/m, cy + side/2*s/m, z))
    return np.array(pts)


def circle(d, z, cx=0., cy=0.):
    a = np.linspace(0, 2*math.pi, N, endpoint=False)
    return np.stack([cx + d/2*np.cos(a), cy + d/2*np.sin(a), np.full(N, z)], axis=1)


def loft(rings):
    """Closed surface through a cyclic sequence of rings with N points each."""
    tris = []
    for A, B in zip(rings, rings[1:] + rings[:1]):
        for i in range(N):
            j = (i+1) % N
            tris.append([A[i], A[j], B[j]]); tris.append([A[i], B[j], B[i]])
    return orient(np.array(tris))


def box(x, y, z, sx, sy, sz):
    p = np.array([[x, y, z], [x+sx, y, z], [x+sx, y+sy, z], [x, y+sy, z], [x, y, z+sz], [x+sx, y, z+sz], [x+sx, y+sy, z+sz], [x, y+sy, z+sz]], float)
    f = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return orient(np.array([[p[a], p[b], p[c]] for a, b, c in f]))


def volume(tris):
    return float(np.einsum('ij,ij->i', tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum()/6)


def orient(tris):
    return tris if volume(tris) > 0 else tris[:, [0, 2, 1]]


def body():
    p = P; fz, ft, pin = p['floor_z'], p['floor_t'], (0., p['pin_y'])
    rings = [square(p['outer'], 0), square(p['outer'], p['top']), square(p['opening'], p['top']),
             square(p['pocket'], fz), circle(p['boss_d'], fz, *pin), circle(p['boss_d'], fz+p['boss_h'], *pin),
             circle(p['pin_d'], fz+p['boss_h'], *pin), circle(p['pin_d'], fz-ft, *pin),
             square(p['opening'], fz-ft), square(p['opening'], 0)]
    return loft(rings)


def backboard():
    """L-shaped tag stand: a foot that butts against the dock's +Y wall and a plate at board_foot from it.
    Boundary a..h of the L profile in (y, z); b, d, g split the straight edges so the caps stay manifold."""
    p = P; y0 = p['outer']/2; t = p['board_t']; L = p['board_foot']; H = p['board_h']; w = p['board_w']/2
    prof = [(0, 0), (L, 0), (L+t, 0), (L+t, t), (L+t, H), (L, H), (L, t), (0, t)]   # a b c d e f g h
    caps = [(0, 1, 6), (0, 6, 7), (1, 2, 3), (1, 3, 6), (6, 3, 4), (6, 4, 5)]
    pt = lambda x, i: np.array([x, y0 + prof[i][0], prof[i][1]], float)
    tris = []
    for a, b, c in caps:
        tris.append([pt(-w, a), pt(-w, c), pt(-w, b)]); tris.append([pt(w, a), pt(w, b), pt(w, c)])
    for i in range(8):
        j = (i+1) % 8
        tris.append([pt(-w, i), pt(-w, j), pt(w, j)]); tris.append([pt(-w, i), pt(w, j), pt(w, i)])
    return orient(np.array(tris))


def camera_profile():
    """Width, height, fx, fy and pitch of the Scout camera from config/airframes.json; a fixed fallback if absent."""
    try:
        profiles = json.loads((HERE.parents[4]/'config'/'airframes.json').read_text())
        profiles = profiles.get('profiles', profiles) if isinstance(profiles, dict) else profiles
        items = list(profiles.values()) if isinstance(profiles, dict) else profiles
        prof = next((p for p in items if 'light' in p.get('id', '')), items[0]); cam = prof['camera']
        return dict(width=cam['width'], height=cam['height'], fx=cam['fx'], fy=cam['fy'], pitch_deg=cam['pitch_degrees'], source='config/airframes.json:'+prof['id'])
    except Exception as e:
        return dict(width=960, height=540, fx=722.15, fy=722.15, pitch_deg=-10., source=f'fallback ({type(e).__name__})')


def tag_view():
    """Which tag of the column is fully inside the forward camera's view as the aircraft descends over the pocket."""
    p = P; cam = camera_profile(); d = p['outer']/2 + p['board_foot'] - p['camera_y']
    vfov_deg = 2*math.degrees(math.atan(cam['height']/2/cam['fy'])); hfov_deg = 2*math.degrees(math.atan(cam['width']/2/cam['fx']))
    shift = d*math.tan(math.radians(-cam['pitch_deg']))   # a camera pitched down sees lower tags
    def reach(size):
        return d*math.tan(math.radians(vfov_deg/2 - math.degrees(math.atan(size/2/d))))
    covered = sorted((z + shift - reach(size), z + shift + reach(size)) for size, z in p['tags'])
    lo, hi = covered[0]; gaps = []
    for a, b in covered[1:]:
        if a > hi: gaps.append((hi, a))
        hi = max(hi, b)
    return dict(tag_plane_from_camera_mm=d, fully_visible_centre_offset_mm={str(int(size)): reach(size) for size, _ in p['tags']},
                camera_height_covered_mm=[lo, hi], coverage_gaps_mm=gaps, camera_height_docked_mm=p['camera_z'],
                descent_covered_above_docked_mm=hi - p['camera_z'], docked_height_covered=lo <= p['camera_z'] <= hi,
                camera=cam, fov_deg=dict(vertical=vfov_deg, horizontal=hfov_deg), axis_drop_at_tag_plane_mm=shift,
                tag_width_px_at_1m={str(int(size)): cam['fx']*size/1000. for size, _ in p['tags']})


def write_stl(path, tris, name):
    out = [f'solid {name}']
    for t in tris:
        n = np.cross(t[1]-t[0], t[2]-t[0]); n = n/max(np.linalg.norm(n), 1e-12)
        out.append(f'  facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n    outer loop')
        out += [f'      vertex {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}' for v in t]
        out.append('    endloop\n  endfacet')
    out.append(f'endsolid {name}')
    path.write_text('\n'.join(out) + '\n')


def manifold(tris):
    from collections import Counter
    keys = [tuple(tuple(round(float(v), 4) for v in pt) for pt in f) for f in tris]; edges = Counter()
    for f in keys:
        for a, b in zip(f, (*f[1:], f[0])): edges[tuple(sorted((a, b)))] += 1
    return sum(n != 2 for n in edges.values())


def stl_bounds(path):
    import re
    v = np.array(re.findall(r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)', path.read_text()), dtype=float)
    return v.min(0), v.max(0)


if __name__ == '__main__':
    b = body(); k = backboard()
    assert manifold(b) == 0 and manifold(k) == 0
    write_stl(HERE/'dock-body-a.stl', b, 'dock_body_a'); write_stl(HERE/'dock-backboard-a.stl', k, 'dock_backboard_a')
    mech = HERE.parent/'mechanics'
    frame_lo, frame_hi = stl_bounds(mech/'scout-frame-a.stl'); cradle_lo, cradle_hi = stl_bounds(mech/'battery-cradle-a.stl')
    feet_z = float(frame_lo[2]); cradle_underside = float(cradle_lo[2]) - 12.   # assembly-a places the cradle at Z=-12
    scout_dz = P['floor_z'] - feet_z
    checks = dict(
        parameters_mm=P,
        scout_offset_z_mm=scout_dz,
        pocket_clearance_per_side_mm=(P['pocket'] - float(frame_hi[0]-frame_lo[0]))/2,
        cradle_underside_above_floor_mm=cradle_underside - feet_z,
        boss_top_below_cradle_mm=(cradle_underside - feet_z) - P['boss_h'],
        pin_compression_mm=P['boss_h'] + P['pin_travel'] - (cradle_underside - feet_z),
        foot_strip_margin_mm=dict(x=P['strip_w']/2, y=P['strip_l']/2 - 9.),
        body_solid_volume_cm3=volume(b)/1000, backboard_solid_volume_cm3=volume(k)/1000,
        body_footprint_mm=[P['outer'], P['outer'], P['top']],
        backboard_footprint_mm=[P['board_w'], P['board_foot']+P['board_t'], P['board_h']],
        tag_column=dict(family='tag36h11', tags_size_and_centre_above_table_mm=[list(t) for t in P['tags']], plane_y_from_dock_centre_mm=P['outer']/2+P['board_foot']),
        tag_view=tag_view(),
        scope='Nominal geometry from the STL files; print fit, slide friction and contact wear unmeasured')
    spans = sorted((z - size/2 - size/8, z + size/2 + size/8) for size, z in P['tags'])   # black border plus one-cell quiet zone
    checks['tag_quiet_zone_gaps_mm'] = [round(b[0] - a[1], 1) for a, b in zip(spans, spans[1:])]
    assert all(gap > 0 for gap in checks['tag_quiet_zone_gaps_mm']) and spans[-1][1] <= P['floor_z'] + P['board_h'] and spans[0][0] >= P['floor_z'], checks['tag_quiet_zone_gaps_mm']
    assert not checks['tag_view']['coverage_gaps_mm'] and checks['tag_view']['descent_covered_above_docked_mm'] >= 120 and checks['tag_view']['docked_height_covered'], checks['tag_view']
    assert checks['pocket_clearance_per_side_mm'] > 0.5 and 0.5 <= checks['pin_compression_mm'] <= P['pin_travel'] and checks['boss_top_below_cradle_mm'] >= 0.5, checks
    (HERE/'clearance-checks.json').write_text(json.dumps(checks, indent=2))
    print(json.dumps({k: v for k, v in checks.items() if k != 'parameters_mm'}, indent=1))
