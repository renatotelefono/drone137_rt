"""Perched watch: a docked aircraft's camera watched for events, with evidence, a fixed
question to the model, cooldowns and an alert flag. The detector decides that something
happened; the model only says what it was, from a before-and-after picture, in a fixed schema.
"""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

import cv2
import numpy as np

from app.watch_detector import ChangeDetector, KINDS

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('DRONE137_DATA_DIR', ROOT/'.local/data')).resolve()
CATEGORIES = ('person', 'object_added', 'object_removed', 'object_moved', 'lighting', 'nothing')
PROMPT = ('Two views from the same fixed indoor camera: left is before, right is now, and the region that '
          'changed is marked. Say what changed, as one category: person (a person or people appeared or '
          'moved), object_added, object_removed, object_moved, lighting (only the light level or shadows '
          'changed), nothing (no real change). Say whether security should look (matters): a person or a '
          'moved, added or removed object matters; lighting and nothing do not. Summary under 20 words. '
          'Never describe who a person is.')
SCHEMA = {'type': 'object', 'properties': {'category': {'type': 'string', 'enum': list(CATEGORIES)},
                                           'matters': {'type': 'boolean'}, 'summary': {'type': 'string', 'maxLength': 120}},
          'required': ['category', 'matters', 'summary'], 'additionalProperties': False}
MATTERS = {'person', 'object_added', 'object_removed', 'object_moved'}


def parse(raw):
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {'category', 'matters', 'summary'} or value['category'] not in CATEGORIES
            or not isinstance(value['matters'], bool) or not isinstance(value['summary'], str) or len(value['summary']) > 120):
        raise ValueError('Invalid event answer')
    return value


def composite(before, after, bbox, margin=.25):
    """Before and after side by side, the changed region boxed, sized for the model."""
    h, w = after.shape[:2]; x, y, bw, bh = bbox
    mx, my = int(bw*margin) + 10, int(bh*margin) + 10
    x0, y0, x1, y1 = max(0, x-mx), max(0, y-my), min(w, x+bw+mx), min(h, y+bh+my)
    if (x1-x0) < w*.4 or (y1-y0) < h*.4:   # keep context around small regions
        cx, cy = (x0+x1)//2, (y0+y1)//2; hw, hh = max(x1-x0, int(w*.4))//2, max(y1-y0, int(h*.4))//2
        x0, x1 = max(0, cx-hw), min(w, cx+hw); y0, y1 = max(0, cy-hh), min(h, cy+hh)
    panels = []
    for image in (before, after):
        crop = image[y0:y1, x0:x1].copy()
        cv2.rectangle(crop, (x-x0, y-y0), (x-x0+bw, y-y0+bh), (0, 220, 255), 2)
        panels.append(crop)
    out = np.hstack([panels[0], np.full((y1-y0, 6, 3), 255, np.uint8), panels[1]])
    if out.shape[1] > 960:
        out = cv2.resize(out, (960, int(out.shape[0]*960/out.shape[1])))
    return out


def encode(image, quality=80):
    return cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


class EventStore:
    def __init__(self, path=DATA/'watch.sqlite3'):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, at REAL NOT NULL, aircraft TEXT NOT NULL, kind TEXT NOT NULL,
                category TEXT, matters INTEGER NOT NULL, summary TEXT NOT NULL, bbox TEXT NOT NULL, evidence TEXT NOT NULL, model TEXT,
                latency_s REAL, acknowledged_at REAL);
                CREATE INDEX IF NOT EXISTS events_at ON events(at);''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10); db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, event):
        with self.connection() as db:
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)',
                       (event['id'], event['at'], event['aircraft'], event['kind'], event['category'], int(event['matters']), event['summary'],
                        json.dumps(event['bbox']), json.dumps(event['evidence']), event.get('model'), event.get('latency_s')))
        return event

    @staticmethod
    def row(r):
        return {'id': r['id'], 'at': r['at'], 'aircraft': r['aircraft'], 'kind': r['kind'], 'category': r['category'], 'matters': bool(r['matters']),
                'summary': r['summary'], 'bbox': json.loads(r['bbox']), 'evidence': json.loads(r['evidence']), 'model': r['model'],
                'latency_s': r['latency_s'], 'acknowledged_at': r['acknowledged_at']}

    def list(self, since=0., limit=50):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM events WHERE at>? ORDER BY at DESC LIMIT ?', (since, limit)).fetchall()
        return [self.row(r) for r in rows]

    def get(self, identity):
        with self.connection() as db:
            r = db.execute('SELECT * FROM events WHERE id=?', (identity,)).fetchone()
        if not r:
            raise ValueError('Unknown event')
        return self.row(r)

    def acknowledge(self, identity, at=None):
        with self.connection() as db:
            if not db.execute('UPDATE events SET acknowledged_at=? WHERE id=? AND acknowledged_at IS NULL', (at or time.time(), identity)).rowcount:
                raise ValueError('Unknown or already acknowledged event')
        return self.get(identity)

    def alerts(self):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM events WHERE matters=1 AND acknowledged_at IS NULL ORDER BY at DESC LIMIT 50').fetchall()
        return [self.row(r) for r in rows]


class PerchedWatch:
    """One watched camera. frames: () -> (jpeg, sequence, capture_time_s) or None. model: .image(jpeg, prompt, schema, ...) or None."""
    def __init__(self, aircraft, frames, store, folder, model=None, *, clock=time.time, cooldown_s=30., period_s=.4, detector=None, question=True):
        self.aircraft, self.frames, self.store, self.folder, self.model = aircraft, frames, store, Path(folder), model
        self.clock, self.cooldown_s, self.period_s, self.question = clock, cooldown_s, period_s, question
        self.detector = detector or ChangeDetector()
        self.state = 'idle'; self.error = None; self.task = None
        self.frames_seen = self.candidates = self.events = self.suppressed = 0
        self.last_sequence = None; self.last_event = None; self.last_frame = None
        self.cooldown_until = {k: 0. for k in KINDS}
        self.started = None

    def status(self):
        return {'aircraft': self.aircraft, 'state': self.state, 'error': self.error, 'frames': self.frames_seen, 'candidates': self.candidates,
                'events': self.events, 'suppressed': self.suppressed, 'reference_ready': self.detector.reference is not None,
                'last_event': self.last_event, 'started': self.started, 'cooldown_s': self.cooldown_s}

    async def start(self):
        if self.state == 'watching':
            raise RuntimeError('Already watching')
        self.state, self.error, self.started = 'watching', None, self.clock()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.state = 'stopped'
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def run(self):
        try:
            while self.state == 'watching':
                try:
                    await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.error = f'{type(exc).__name__}: {exc}'[:160]
                await asyncio.sleep(self.period_s)
        except asyncio.CancelledError:
            raise

    async def step(self):
        frame = self.frames()
        if frame is None:
            return
        jpeg, sequence, captured = frame
        if sequence == self.last_sequence:
            return
        self.last_sequence = sequence; self.frames_seen += 1
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Undecodable frame')
        before = self.detector.reference_image()
        candidates = self.detector.update(image)
        self.last_frame = image
        for candidate in candidates:
            self.candidates += 1
            await self.handle(candidate, before, image, captured)

    async def handle(self, candidate, before, after, captured):
        kind = candidate['kind']; now = self.clock()
        if now < self.cooldown_until[kind]:
            self.suppressed += 1
            if kind == 'change':
                self.detector.absorb()
            return None
        self.cooldown_until[kind] = now + self.cooldown_s
        identity = uuid.uuid4().hex
        folder = self.folder/identity; folder.mkdir(parents=True, exist_ok=True)
        before_bgr = cv2.resize(before, (after.shape[1], after.shape[0])) if before is not None else after
        pair = composite(before_bgr, after, candidate['bbox'])
        evidence = {'before': 'before.jpg', 'after': 'after.jpg', 'composite': 'composite.jpg'}
        (folder/'before.jpg').write_bytes(encode(before_bgr)); (folder/'after.jpg').write_bytes(encode(after)); (folder/'composite.jpg').write_bytes(encode(pair))
        answer, latency, model_name = None, None, None
        if self.model is not None and self.question and kind != 'lighting':
            began = time.monotonic()
            try:
                raw = await self.model.image(encode(pair, 85), PROMPT, SCHEMA, timeout=12, max_tokens=120)
                answer = parse(raw); model_name = getattr(self.model, 'name', 'local')
            except Exception as exc:
                answer = None; self.error = f'model: {type(exc).__name__}: {exc}'[:160]
            latency = time.monotonic() - began
        if answer is None:
            category = 'lighting' if kind == 'lighting' else None
            matters = kind in ('motion', 'change')
            summary = {'motion': 'Movement in view, unreviewed', 'change': 'Something changed in view, unreviewed', 'lighting': 'Light level changed'}[kind]
        else:
            category, matters, summary = answer['category'], bool(answer['matters']) and answer['category'] in MATTERS, answer['summary']
        event = {'id': identity, 'at': captured if captured is not None else now, 'aircraft': self.aircraft, 'kind': kind, 'category': category,
                 'matters': matters, 'summary': summary, 'bbox': list(candidate['bbox']), 'evidence': evidence, 'model': model_name, 'latency_s': latency}
        self.store.add(event); self.events += 1; self.last_event = {k: event[k] for k in ('id', 'at', 'kind', 'category', 'matters', 'summary')}
        if kind == 'change':
            self.detector.absorb()   # the new state is normal from here on
        return event
