"""Render dock A alone and with the Scout docked. Usage: python render_dock.py <output dir>"""
import sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent/'mechanics'))
import generate_dock as G
from render_views import scout_parts, render, sheet, box, cyl

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE; OUT.mkdir(parents=True, exist_ok=True)
P = G.P; fz = P['floor_z']; yb = P['outer']/2 + P['board_foot']
dock = [(G.body(), (205, 207, 212), 1, 'printed dock body, funnel and bay'),
        (G.backboard(), (228, 229, 232), 1, 'tag stand, 100 mm in front of the dock wall'),
        (cyl(0, P['pin_y'], fz+P['boss_h'], P['pin_travel'], P['pin_d'], 16), (212, 175, 55), 1, 'spring contact pin, +5 V')]
for sx in (-1, 1):
    dock.append((box(sx*P['strip_x']-P['strip_w']/2, -P['strip_l']/2, fz, P['strip_w'], P['strip_l'], .3), (184, 115, 51), 1, 'copper foot strips, GND'))
rng = np.random.default_rng(137)
for size, tz in P['tags']:
    dock.append((box(-size/2, yb-.6, tz-size/2, size, .6, size), (25, 25, 28), 1, 'tag36h11 column: 40, 40 and 60 mm'))
    inner = size*.75; c = inner/6
    dock.append((box(-inner/2, yb-.8, tz-inner/2, inner, .6, inner), (240, 240, 240), 1, 'tag interior'))
    for i in range(6):
        for j in range(6):
            if rng.random() < .45:
                dock.append((box(-inner/2 + i*c, yb-1.0, tz-inner/2 + j*c, c, .6, c), (25, 25, 28), 1, 'tag interior'))
scout = scout_parts(HERE.parent/'mechanics', dz=P['floor_z'] - (-17.))
T = 'Scout 110-B on dock A  |  %s  |  backboard and tag at +Y, the camera side'
render(dock + scout, OUT/'dock-a-docked-three-quarter.png', T % 'three-quarter from behind', az=215, el=-32, legend=True)
render(dock + scout, OUT/'dock-a-docked-side.png', T % 'side view', az=90, el=0,
       dims=[('%.0f mm dock' % P['outer'], (0, -P['outer']/2, -8), (0, P['outer']/2, -8)), ('tag plane %.0f mm from the pocket centre' % yb, (0, 0, -20), (0, yb, -20)),
             ('lowest tag at camera height, %.0f mm' % P['camera_z'], (0, yb+14, 0), (0, yb+14, P['camera_z']))])
render(dock + scout, OUT/'dock-a-docked-top.png', T % 'top view', az=0, el=-90,
       dims=[('%.0f mm pocket' % P['pocket'], (-P['pocket']/2, -P['pocket']/2-6, 60), (P['pocket']/2, -P['pocket']/2-6, 60))])
render(dock, OUT/'dock-a-empty.png', 'Dock A alone  |  funnel, pocket, contact pin and foot strips', az=215, el=-40, legend=True)
sheet([OUT/n for n in ('dock-a-docked-three-quarter.png', 'dock-a-docked-top.png', 'dock-a-docked-side.png', 'dock-a-empty.png')], OUT/'dock-a-views.png')
