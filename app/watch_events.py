"""Perched watch: a docked aircraft's camera watched for events, with evidence, a fixed
question to the model, cooldowns and an alert flag. The detector decides that something
happened; the model only says what it was, from a before-and-after picture, in a fixed schema.
"""
import asyncio
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import sqlite3
import time
import uuid

import cv2
import numpy as np

from app.person_detector import PersonDetector, person_in
from app.watch_classify import classify_change, union_box
from app.watch_detector import ChangeDetector, KINDS

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('DRONE137_DATA_DIR', ROOT/'.local/data')).resolve()
CATEGORIES = ('person', 'object_added', 'object_removed', 'object_moved', 'lighting', 'nothing')
PROMPT = ('Two views from the same fixed indoor camera. The left panel is labelled BEFORE and the right panel '
          'NOW; the region that changed is boxed in both. First describe in one sentence of at most 20 words what '
          'is different in NOW compared with BEFORE. Then give one category: person (a human figure appeared, left '
          'or moved; any walking or standing human shape counts as person, not as an object; a cart, trolley, box, '
          'machine or piece of furniture is not a person), object_added (a thing is in NOW that was not in BEFORE), '
          'object_removed (a thing in BEFORE is gone in NOW, even when the wall, shelf or floor it uncovered looks '
          'new), object_moved (the same thing is in both but in a different place), lighting (only brightness or '
          'shadows changed), nothing. Then say whether security should look (matters): a person or an added, removed '
          'or moved object matters; lighting and nothing do not. Never describe who a person is. ')
PERSON_WORDS = re.compile(r"\b(person|people|someone|somebody|human|figure|man|woman|worker|intruder)\b")
NO_PERSON = re.compile(r"\b(no|not a|without a|no longer a|nobody|no one)\s*(person|people|human|figure)?\b")


def says_person(summary):
    """The model's own sentence names a person: its free text is a second reading, more reliable than its category pick."""
    low = (summary or '').lower()
    return bool(PERSON_WORDS.search(low)) and not NO_PERSON.search(low)


def schema(categories):
    return {'type': 'object', 'properties': {'summary': {'type': 'string', 'maxLength': 120},
                                             'category': {'type': 'string', 'enum': list(categories)},
                                             'matters': {'type': 'boolean'}},
            'required': ['summary', 'category', 'matters'], 'additionalProperties': False}


SCHEMA = schema(CATEGORIES)
SCHEMA_MOTION = schema(('person', 'object_moved', 'nothing'))   # a region that moved across the frame is a person or a moving object
VERDICT_WORDS = {'object_removed': 'the thing was taken away', 'object_added': 'something arrived', 'object_moved': 'the thing moved'}
PANEL_WIDTH = 448


def hint(candidate, frame_shape, verdict=None):
    """What the detector itself knows about the region, in words the model can use."""
    x, y, w, h = candidate['bbox']; fraction = candidate.get('area_fraction', w*h/(frame_shape[0]*frame_shape[1]))
    motion = candidate['kind'] == 'motion'
    shape = 'taller than wide' if h > 1.3*w else 'wider than tall' if w > 1.3*h else 'about square'
    note = (f"Detector note: the boxed region {'moved across the frame' if motion else 'appeared and stayed still'}, "
            f"covers {fraction*100:.0f} % of the picture and is {shape}.")
    if verdict is not None:
        if verdict['category']:
            note += f" From the pixels, {VERDICT_WORDS[verdict['category']]}: {verdict['reason']}."
        else:
            note += ' The pixels do not settle whether something was added, taken away or moved.'
    return note
MATTERS = {'person', 'object_added', 'object_removed', 'object_moved'}


def parse(raw):
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {'category', 'matters', 'summary'} or value['category'] not in CATEGORIES
            or not isinstance(value['matters'], bool) or not isinstance(value['summary'], str) or len(value['summary']) > 120):
        raise ValueError('Invalid event answer')
    return value


def composite(before, after, bbox, margin=1.):
    """Side by side, labelled BEFORE and NOW, the box drawn in both: a crop around the box grown by `margin` of its size
    each side, at least 160 by 120 and no narrower than three quarters of its height, scaled to PANEL_WIDTH so a small
    thing is legible."""
    h, w = after.shape[:2]; x, y, bw, bh = (int(v) for v in bbox)
    cw, ch = max(160, int(bw*(1 + 2*margin))), max(120, int(bh*(1 + 2*margin)))
    cw = max(cw, int(ch*.75)); ch = max(ch, int(cw*.5))
    cw, ch = min(w, cw), min(h, ch)
    x0 = min(max(0, x + bw//2 - cw//2), w - cw); y0 = min(max(0, y + bh//2 - ch//2), h - ch)
    panels = []
    for image, label in ((before, 'BEFORE'), (after, 'NOW')):
        crop = image[y0:y0 + ch, x0:x0 + cw].copy()
        cv2.rectangle(crop, (x - x0, y - y0), (x - x0 + bw, y - y0 + bh), (0, 220, 255), max(1, cw//200))
        scale = PANEL_WIDTH/cw
        crop = cv2.resize(crop, (PANEL_WIDTH, max(1, int(ch*scale))), interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
        band = 26
        crop = np.vstack([np.zeros((band, crop.shape[1], 3), np.uint8), crop])
        cv2.putText(crop, label, (8, band - 7), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2, cv2.LINE_AA)
        panels.append(crop)
    return np.hstack([panels[0], np.full((panels[0].shape[0], 6, 3), 255, np.uint8), panels[1]])


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
    def __init__(self, aircraft, frames, store, folder, model=None, *, clock=time.time, cooldown_s=30., period_s=.4, detector=None, question=True,
                 people=None):
        self.aircraft, self.frames, self.store, self.folder, self.model = aircraft, frames, store, Path(folder), model
        self.clock, self.cooldown_s, self.period_s, self.question = clock, cooldown_s, period_s, question
        self.detector = detector or ChangeDetector()
        self.people = people or PersonDetector()
        self.state = 'idle'; self.error = None; self.task = None
        self.frames_seen = self.candidates = self.events = self.suppressed = 0
        self.last_sequence = None; self.last_event = None; self.last_frame = None
        self.cooldown_until = {k: 0. for k in KINDS}
        self.started = None

    def status(self):
        return {'aircraft': self.aircraft, 'state': self.state, 'error': self.error, 'frames': self.frames_seen, 'candidates': self.candidates,
                'events': self.events, 'suppressed': self.suppressed, 'reference_ready': self.detector.reference is not None,
                'person_detector': self.people.backend,
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
        self.candidates += len(candidates)
        changes = [c for c in candidates if c['kind'] == 'change']
        for candidate in candidates:
            if candidate['kind'] != 'change':
                await self.handle(candidate, before, image, captured)
        if changes:
            # Still regions of one frame are one event: a moved thing leaves one box and fills another.
            boxes = [tuple(c['bbox']) for c in changes]
            merged = {'kind': 'change', 'bbox': union_box(boxes), 'boxes': boxes, 'area_fraction': sum(c['area_fraction'] for c in changes),
                      'frames': max(c['frames'] for c in changes)}
            await self.handle(merged, before, image, captured)

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
        verdict = None
        if kind == 'change' and before is not None:
            # What kind of change, from the pixels at the detector's working size; the model names the thing.
            small = np.clip(self.detector.prepare(after), 0, 255).astype(np.uint8); s = self.detector.scale
            verdict = classify_change(before, small, [(b[0]*s, b[1]*s, b[2]*s, b[3]*s) for b in candidate.get('boxes', [candidate['bbox']])])
        pair = composite(before_bgr, after, candidate['bbox'])
        evidence = {'before': 'before.jpg', 'after': 'after.jpg', 'composite': 'composite.jpg', 'boxes': [list(b) for b in candidate.get('boxes', [candidate['bbox']])],
                    'detector_category': verdict['category'] if verdict else None, 'reason': verdict['reason'] if verdict else None, 'model_category': None}
        (folder/'before.jpg').write_bytes(encode(before_bgr)); (folder/'after.jpg').write_bytes(encode(after)); (folder/'composite.jpg').write_bytes(encode(pair))
        answer, latency, model_name = None, None, None
        # A person is the detector's call, made for that and nothing else; the model is not asked then.
        person = person_in(self.people.detect(after), candidate['bbox']) if kind != 'lighting' else None
        evidence['person_detector'] = {'backend': self.people.backend, 'seen': person is not None,
                                       **({'confidence': person['confidence'], 'bbox': list(person['bbox'])} if person else {})}
        if person is None and self.model is not None and self.question and kind != 'lighting':
            began = time.monotonic()
            try:
                raw = await self.model.image(encode(pair, 85), PROMPT + hint(candidate, after.shape, verdict),
                                             SCHEMA_MOTION if kind == 'motion' else SCHEMA, timeout=12, max_tokens=160)
                answer = parse(raw); model_name = getattr(self.model, 'name', 'local')
            except Exception as exc:
                answer = None; self.error = f'model: {type(exc).__name__}: {exc}'[:160]
            latency = time.monotonic() - began
        model_category = answer['category'] if answer else None; evidence['model_category'] = model_category
        if answer is not None and model_category != 'person' and says_person(answer['summary']):
            model_category = 'person'; evidence['model_says_person'] = True
        detector_category = verdict['category'] if verdict else None
        # The person detector's sighting wins, then the model's word for a person; the pixels decide added, taken away or moved; the model fills the rest.
        if kind == 'lighting':
            category = 'lighting'
        elif person is not None or model_category == 'person':
            category = 'person'
        else:
            category = detector_category or model_category
        if person is not None:
            matters, summary = True, 'A person is in view'          # never who
        elif answer is not None and category == model_category:
            matters, summary = bool(answer['matters']) and category in MATTERS, answer['summary']
        elif answer is not None:
            matters, summary = category in MATTERS, answer['summary']
        else:
            matters = category in MATTERS if category else kind in ('motion', 'change')
            summary = {'object_removed': 'Something was taken away, unreviewed', 'object_added': 'Something arrived, unreviewed',
                       'object_moved': 'Something moved, unreviewed'}.get(category) or {'motion': 'Movement in view, unreviewed',
                       'change': 'Something changed in view, unreviewed', 'lighting': 'Light level changed'}[kind]
        event = {'id': identity, 'at': captured if captured is not None else now, 'aircraft': self.aircraft, 'kind': kind, 'category': category,
                 'matters': matters, 'summary': summary, 'bbox': list(candidate['bbox']), 'evidence': evidence, 'model': model_name, 'latency_s': latency}
        self.store.add(event); self.events += 1; self.last_event = {k: event[k] for k in ('id', 'at', 'kind', 'category', 'matters', 'summary')}
        if kind == 'change':
            self.detector.absorb()   # the new state is normal from here on
        return event
