"""Render the Scout 110-B prototype A from its STL files and part envelopes.

Painter's algorithm with flat shading, orthographic views, no OpenSCAD needed.
Usage: python render_views.py <mechanics dir> <output dir>   (numpy + Pillow only)
"""
import math, re, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

M = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
MOTORS = [(38.8909, 38.8909), (38.8909, -38.8909), (-38.8909, -38.8909), (-38.8909, 38.8909)]

def stl(path):
    v = np.array(re.findall(r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)', path.read_text()), dtype=float)
    return v.reshape(-1, 3, 3)

def box(x, y, z, sx, sy, sz):
    p = np.array([[x, y, z], [x+sx, y, z], [x+sx, y+sy, z], [x, y+sy, z], [x, y, z+sz], [x+sx, y, z+sz], [x+sx, y+sy, z+sz], [x, y+sy, z+sz]], float)
    f = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return np.array([[p[a], p[b], p[c]] for a, b, c in f])

def cyl(x, y, z, h, d, n=40):
    r = d/2; a = np.linspace(0, 2*math.pi, n, endpoint=False); t = []
    for i in range(n):
        a0, a1 = a[i], a[(i+1) % n]
        p0 = [x+r*math.cos(a0), y+r*math.sin(a0)]; p1 = [x+r*math.cos(a1), y+r*math.sin(a1)]
        t.append([[*p0, z], [*p1, z], [*p1, z+h]]); t.append([[*p0, z], [*p1, z+h], [*p0, z+h]])
        t.append([[x, y, z+h], [*p0, z+h], [*p1, z+h]]); t.append([[x, y, z], [*p1, z], [*p0, z]])
    return np.array(t, float)

def ring(x, y, z, r0, r1, n=72):
    a = np.linspace(0, 2*math.pi, n+1); t = []
    for i in range(n):
        p = lambda r, k: [x+r*math.cos(a[k]), y+r*math.sin(a[k]), z]
        t.append([p(r0, i), p(r1, i), p(r1, i+1)]); t.append([p(r0, i), p(r1, i+1), p(r0, i+1)])
    return np.array(t, float)

def rot_z(tris, deg, cx, cy):
    a = math.radians(deg); R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    return (tris - [cx, cy, 0]) @ R.T + [cx, cy, 0]

def propeller(x, y, z, angle, d=65):
    blades = [rot_z(box(x, y-4, z, d/2, 8, 1.2), angle + k, x, y) for k in (0, 180)]
    return np.concatenate(blades + [cyl(x, y, z-2, 4.5, 6, 24)])

parts = []  # (triangles, rgb, alpha, legend label)
frame = stl(M/'scout-frame-a.stl')
parts.append((frame, (82, 100, 104), 1, 'printed frame with prop guards'))
parts.append((box(-21, -20, 5, 42, 40, 1), (46, 139, 87), 1, 'carrier PCB 42 x 40 mm'))
parts.append((stl(M/'electronics-bridge-a.stl') + [0, 0, 7], (196, 200, 204), 1, 'electronics bridge'))
parts.append((stl(M/'camera-cradle-a.stl') + [0, 8, 23], (235, 150, 40), 1, 'camera cradle'))
parts.append((box(-11.5, 5, 25, 23, 7, 19), (0, 128, 128), 1, 'XIAO ESP32-S3 Sense, camera forward'))
parts.append((stl(M/'imu-tray-a.stl') + [0, -7, 23], (235, 150, 40), 1, 'IMU tray'))
parts.append((box(-11, -15.5, 24.2, 22, 17, 1.6), (40, 70, 220), 1, 'MPU-6050 board'))
parts.append((stl(M/'battery-cradle-a.stl') + [0, 0, -12], (235, 150, 40), 1, 'battery cradle'))
parts.append((box(-9, -31, -10.8, 18, 62, 8), (218, 165, 32), 1, '1S battery under the frame'))
for px, py in MOTORS:
    parts.append((cyl(px, py, -9, 20, 8.5), (175, 180, 190), 1, '8520 motor'))
parts.append((cyl(6, 15.5, 6, 12, 6.3, 24), (55, 55, 60), 1, 'electrolytic capacitor'))
parts.append((cyl(13, -1, 6, 11, 5, 24), (55, 55, 60), 1, 'electrolytic capacitor'))
for (px, py), ang in zip(MOTORS, (25, 70, 115, 160)):
    parts.append((propeller(px, py, 12, ang), (60, 70, 90), 1, '65 mm propeller'))
    parts.append((ring(px, py, 12.3, 32.0, 32.6), (110, 130, 230), .8, 'propeller sweep'))

allpts = np.concatenate([t.reshape(-1, 3) for t, _, _, _ in parts])
lo, hi = allpts.min(0), allpts.max(0)
print('bounding box mm: x %.1f..%.1f  y %.1f..%.1f  z %.1f..%.1f' % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
fx = frame.reshape(-1, 3); print('frame extents mm: %.1f x %.1f x %.1f' % tuple(fx.max(0) - fx.min(0)))

def rotation(az, el):
    a, e = math.radians(az), math.radians(el)
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, math.cos(e), -math.sin(e)], [0, math.sin(e), math.cos(e)]])
    return rx @ rz

BG = (236, 239, 241); INK = (30, 36, 40); DIM = (200, 90, 20)

def render(name, az, el, size=(1400, 1000), legend=False, dims=()):
    R = rotation(az, el); light = np.array([.35, -.45, .82]); light /= np.linalg.norm(light)
    pts = allpts @ R.T; vlo, vhi = pts.min(0), pts.max(0); span = (vhi - vlo)
    s = min((size[0]-200)/span[0], (size[1]-200)/span[2]); cx, cy = size[0]/2, size[1]/2; mid = (vlo + vhi)/2
    proj = lambda p: (cx + (p[0]-mid[0])*s, cy - (p[2]-mid[2])*s)
    img = Image.new('RGBA', size, BG + (255,)); draw = ImageDraw.Draw(img, 'RGBA')
    tris = []
    for t, color, alpha, _ in parts:
        v = t @ R.T; n = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]); nn = np.linalg.norm(n, axis=1)
        n = n/np.maximum(nn, 1e-9)[:, None]; shade = .5 + .5*np.abs(n @ light); depth = v[:, :, 1].mean(1)
        for i in range(len(t)):
            if nn[i] > 1e-9: tris.append((depth[i], v[i], color, alpha, shade[i]))
    tris.sort(key=lambda x: x[0])
    for _, v, color, alpha, sh in tris:
        col = tuple(int(c*sh) for c in color) + (int(255*alpha),)
        draw.polygon([proj(p) for p in v], fill=col, outline=col)
    font = ImageFont.load_default()
    x0, y0 = 70, size[1]-70; draw.line([(x0, y0), (x0 + 50*s, y0)], fill=INK, width=3)
    draw.text((x0, y0-16), '50 mm', fill=INK, font=font)
    draw.text((70, 36), 'Scout 110-B prototype A  |  %s view  |  forward is +Y (camera side)' % name, fill=INK, font=font)
    for text, a, b in dims:
        pa, pb = proj(np.array(a) @ R.T), proj(np.array(b) @ R.T)
        draw.line([pa, pb], fill=DIM, width=2)
        for p in (pa, pb): draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill=DIM)
        draw.text(((pa[0]+pb[0])/2+8, (pa[1]+pb[1])/2-16), text, fill=DIM, font=font)
    if legend:
        seen = set(); y = 70
        for _, color, alpha, label in parts:
            if label in seen: continue
            seen.add(label); draw.rectangle([size[0]-330, y, size[0]-314, y+14], fill=tuple(color)+(255,))
            draw.text((size[0]-306, y), label, fill=INK, font=font); y += 20
    img.convert('RGB').save(OUT/f'scout-110b-{name}.png'); print('saved', name)

w = fx.max(0)[0] - fx.min(0)[0]; h = hi[2] - lo[2]
render('isometric', az=-35, el=-60, legend=True)
render('top', az=0, el=-90, dims=[('110 mm motor to motor', (-38.89, -38.89, 50), (38.89, 38.89, 50)),
                                   ('%.0f mm over the guards' % w, (fx.min(0)[0], -78, 50), (fx.max(0)[0], -78, 50))])
render('front', az=0, el=0, dims=[('%.0f mm battery bottom to board top' % h, (88, 0, lo[2]), (88, 0, hi[2]))])
render('side', az=90, el=0, dims=[('%.0f mm over the guards' % (fx.max(0)[1]-fx.min(0)[1]), (0, fx.min(0)[1], -22), (0, fx.max(0)[1], -22))])
render('three-quarter-low', az=30, el=-25)
tiles = [Image.open(OUT/f'scout-110b-{n}.png').resize((700, 500), Image.LANCZOS) for n in ('isometric', 'top', 'front', 'side')]
sheet = Image.new('RGB', (1400, 1000), BG)
for i, t in enumerate(tiles): sheet.paste(t, ((i % 2)*700, (i//2)*500))
sheet.save(OUT/'scout-110b-views.png'); print('sheet saved')
