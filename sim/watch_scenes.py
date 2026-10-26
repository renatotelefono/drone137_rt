"""Staged events on a fixed camera, for the perched-watch gate: a real photo as the room,
synthetic objects and a walking figure drawn into it, sensor noise and lamp flicker on every
frame. Nothing here is a person; the figure is a dark silhouette."""
import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'sim/assets/fixture-01.jpg'
RATE = 2.5
CATEGORIES = ('object_removed', 'object_added', 'object_moved', 'person', 'lighting')


def room():
    image = cv2.imread(str(FIXTURE))
    return cv2.resize(image, (640, 480), interpolation=cv2.INTER_CUBIC)


def draw_object(image, x, y, kind, rng):
    if kind == 'box':
        cv2.rectangle(image, (x, y), (x+70, y+50), (60, 110, 160), -1); cv2.rectangle(image, (x, y), (x+70, y+50), (30, 60, 90), 2)
    else:
        cv2.rectangle(image, (x+18, y), (x+40, y+90), (30, 30, 200), -1); cv2.circle(image, (x+29, y), 11, (30, 30, 200), -1)
        cv2.rectangle(image, (x+22, y-16), (x+36, y), (40, 40, 40), -1)


def draw_figure(image, x, y, h):
    w = int(h*.36)
    cv2.ellipse(image, (x, y - h + int(h*.1)), (int(h*.08), int(h*.1)), 0, 0, 360, (35, 35, 40), -1)
    cv2.rectangle(image, (x - w//2, y - int(h*.8)), (x + w//2, y - int(h*.4)), (45, 45, 55), -1)
    cv2.rectangle(image, (x - w//2, y - int(h*.4)), (x - 2, y), (40, 40, 50), -1); cv2.rectangle(image, (x + 2, y - int(h*.4)), (x + w//2, y), (40, 40, 50), -1)


def sensor(image, rng, gain=1.):
    noisy = image.astype(np.float32)*gain + rng.normal(0, 2.5, image.shape)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def scenario(category, seed, *, duration_s=30., event_at_s=12.):
    """Frames [(t, bgr)] and the truth {'category', 'at', 'bbox', 'kind'} for one staged event."""
    rng = np.random.default_rng(seed)
    base = room(); h, w = base.shape[:2]
    kind = rng.choice(['box', 'extinguisher'])
    ox, oy = int(rng.integers(60, w-160)), int(rng.integers(150, h-120))
    size = (70, 50) if kind == 'box' else (58, 106)
    obj_bbox = (ox, oy-16 if kind != 'box' else oy, size[0], size[1])
    frames = []; n = int(duration_s*RATE)
    figure_h = int(rng.integers(200, 320)); figure_dir = rng.choice([-1, 1]); figure_y = int(rng.integers(h-60, h-10))
    walk_s = 4.
    truth = {'category': category, 'at': event_at_s, 'kind': {'person': 'motion', 'lighting': 'lighting'}.get(category, 'change')}
    for i in range(n):
        t = i/RATE; image = base.copy()
        flicker = 1 + .01*math.sin(t*1.3) + rng.normal(0, .003)
        gain = flicker
        if category == 'lighting' and t >= event_at_s:
            gain *= .55
        present = {'object_removed': t < event_at_s, 'object_added': t >= event_at_s}.get(category, category in ('object_moved',))
        if category == 'object_moved':
            dx = 90 if t >= event_at_s else 0
            draw_object(image, ox+dx, oy, kind, rng)
            truth['bbox'] = (ox, obj_bbox[1], size[0]+90, size[1])
        elif present:
            draw_object(image, ox, oy, kind, rng); truth['bbox'] = obj_bbox
        else:
            truth['bbox'] = obj_bbox
        if category == 'person' and event_at_s <= t < event_at_s + walk_s:
            progress = (t - event_at_s)/walk_s
            x = int(w*(progress if figure_dir > 0 else 1-progress))
            draw_figure(image, x, figure_y, figure_h)
            if abs(progress-.5) < .06:
                truth['bbox'] = (x-int(figure_h*.18), figure_y-figure_h, int(figure_h*.36), figure_h)   # the figure at mid-walk
        frames.append((t, sensor(image, rng, gain)))
    if category == 'lighting':
        truth['bbox'] = (0, 0, w, h)
    return frames, truth


def quiet(seed, hours=8., drift=True, size=(320, 240)):
    """A quiet night: noise, lamp flicker and a slow illumination drift, no events. Yields (t, frame).
    Frames come at the detector's processing size so a night of 72,000 frames is affordable."""
    rng = np.random.default_rng(seed)
    base = cv2.resize(room(), size, interpolation=cv2.INTER_AREA); n = int(hours*3600*RATE)
    for i in range(n):
        t = i/RATE
        gain = 1 + .01*math.sin(t*1.3) + rng.normal(0, .003) + (.06*math.sin(t/3600*math.pi) if drift else 0)
        yield t, sensor(base, rng, gain)


def jpeg(frame, quality=72):
    return cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
