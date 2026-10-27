"""Dock registry: versioned site objects a mission can end on, plus the dock controller client.

A dock record pins where dock A stands in a place (pose in the place frame), which tag ids
it carries (three per dock, from its index; two docks in one place must differ), and how to
reach its controller. Credentials stay in the local database and
never leave this process; listings strip them.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time

import aiohttp

from app.dock_tags import load_geometry, tag_ids

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get('DRONE137_DATA_DIR', ROOT/'.local/data')).resolve()/'docks.sqlite3'
MODES = ('off', 'charge', 'storage')
MAX_INDEX = 194   # tag36h11 has 587 ids; dock k uses 3k, 3k+1, 3k+2


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate(record, geometry=None):
    geometry = geometry or load_geometry()
    r = copy.deepcopy(record)
    if not isinstance(r, dict) or set(r) - {'id', 'name', 'place_id', 'index', 'pose', 'geometry', 'charge_policy', 'link', 'tag_ids', 'tags', 'tag_plane_m'}:
        raise ValueError('Unexpected dock fields')
    if not isinstance(r.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', r['id']):
        raise ValueError('Dock ID must be a lowercase slug')
    if not isinstance(r.get('name'), str) or not 1 <= len(r['name']) <= 100:
        raise ValueError('Give the dock a name of 1–100 characters')
    place = r.get('place_id')
    if place is not None and (not isinstance(place, str) or not 1 <= len(place) <= 64):
        raise ValueError('place_id must be a short string or null')
    index = r.get('index', 0)
    if type(index) is not int or not 0 <= index <= MAX_INDEX:
        raise ValueError(f'Dock index must be an integer from 0 to {MAX_INDEX}')
    pose = r.get('pose')
    if not isinstance(pose, dict) or set(pose) != {'x', 'y', 'z', 'yaw'} or not all(type(v) in (int, float) and math.isfinite(v) for v in pose.values()):
        raise ValueError('Pose needs finite x, y, z and yaw in the place frame')
    if r.get('geometry', geometry['geometry']) != geometry['geometry']:
        raise ValueError('Only ' + geometry['geometry'] + ' is supported')
    policy = {**geometry['charge_policy'], **(r.get('charge_policy') or {})}
    if set(policy) != set(geometry['charge_policy']) or not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in policy.values()):
        raise ValueError('Charge policy fields must be positive numbers')
    if not policy['storage_low_v'] < policy['storage_v'] < policy['storage_high_v'] < policy['full_v'] <= 4.2:
        raise ValueError('Charge policy voltages are out of order or above 4.20 V')
    link = r.get('link')
    if link is not None:
        if not isinstance(link, dict) or set(link) != {'endpoint', 'fingerprint', 'credential'}:
            raise ValueError('Link needs endpoint, fingerprint and credential')
        if not isinstance(link['endpoint'], str) or not re.fullmatch(r'https://(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}', link['endpoint']):
            raise ValueError('Link endpoint must be https://<ipv4>:<port> on the private network')
        if not isinstance(link['fingerprint'], str) or not re.fullmatch('[0-9a-f]{64}', link['fingerprint']):
            raise ValueError('Fingerprint must be the SHA-256 of the dock certificate, 64 hex characters')
        if not isinstance(link['credential'], str) or not 16 <= len(link['credential']) <= 128:
            raise ValueError('Credential must be 16–128 characters')
    return {'id': r['id'], 'name': r['name'], 'place_id': place, 'index': index,
            'pose': {k: float(pose[k]) for k in ('x', 'y', 'z', 'yaw')}, 'geometry': geometry['geometry'],
            'tag_ids': tag_ids(index), 'tags': copy.deepcopy(geometry['tags']), 'tag_plane_m': geometry['tag_plane_f_m'],
            'charge_policy': policy, 'link': link}


def public(record):
    out = copy.deepcopy(record)
    if out.get('link'):
        out['link'] = {'endpoint': out['link']['endpoint'], 'fingerprint': out['link']['fingerprint']}
    return out


class Docks:
    def __init__(self, path=DEFAULT_DB, geometry=None):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.geometry = geometry or load_geometry()
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS docks(id TEXT, revision INTEGER, name TEXT NOT NULL, content TEXT NOT NULL,
                    sha256 TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS landings(id INTEGER PRIMARY KEY AUTOINCREMENT, dock_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    at REAL NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL);''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10); db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, record, expected_revision=0):
        r = validate(record, self.geometry)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('expected_revision required')
        for other in self.list():
            d = other['dock']
            if d['id'] != r['id'] and d.get('place_id') == r['place_id'] and d['index'] == r['index']:
                raise ValueError(f"Dock index {r['index']} (tags {r['tag_ids']}) is already used by dock '{d['id']}' in this place; "
                                 "two docks in one place need distinct tags")
        content = encoded(r); digest = hashlib.sha256(content.encode()).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            latest = db.execute('SELECT COALESCE(MAX(revision),0) FROM docks WHERE id=?', (r['id'],)).fetchone()[0]
            if latest != expected_revision:
                raise ValueError('Dock changed; reload before saving a new revision')
            db.execute('INSERT INTO docks VALUES(?,?,?,?,?,?)', (r['id'], latest+1, r['name'], content, digest, time.time()))
        return self.get(r['id'], latest+1)

    def get(self, identity, revision=None):
        with self.connection() as db:
            row = db.execute('SELECT * FROM docks WHERE id=?' + (' AND revision=?' if revision is not None else '') + ' ORDER BY revision DESC LIMIT 1',
                             (identity, revision) if revision is not None else (identity,)).fetchone()
        if not row:
            raise ValueError('Unknown dock or revision')
        r = json.loads(row['content'])
        if hashlib.sha256(encoded(r).encode()).hexdigest() != row['sha256']:
            raise ValueError('Dock registry integrity failure')
        return {'dock': validate(r, self.geometry), 'revision': row['revision'], 'sha256': row['sha256'], 'created_at': row['created_at']}

    def list(self):
        with self.connection() as db:
            ids = [r[0] for r in db.execute('SELECT DISTINCT id FROM docks ORDER BY id')]
        return [self.get(i) for i in ids]

    def register(self, identity, name, pose, *, place_id=None, index=None, link=None):
        """A new revision with the aircraft's current pose as the dock pose; the index stays unless given."""
        try:
            current = self.get(identity)
            revision, previous = current['revision'], current['dock']
        except ValueError:
            revision, previous = 0, None
        record = {'id': identity, 'name': name, 'place_id': place_id if place_id is not None else (previous or {}).get('place_id'),
                  'index': index if index is not None else (previous or {}).get('index', 0), 'pose': pose,
                  'link': link if link is not None else (previous or {}).get('link')}
        return self.save(record, revision)

    def record_landing(self, identity, revision, outcome, detail):
        with self.connection() as db:
            db.execute('INSERT INTO landings(dock_id, revision, at, outcome, detail) VALUES(?,?,?,?,?)',
                       (identity, revision, time.time(), outcome, encoded(detail)))

    def landings(self, identity, limit=50):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM landings WHERE dock_id=? ORDER BY id DESC LIMIT ?', (identity, limit)).fetchall()
        return [{'at': r['at'], 'revision': r['revision'], 'outcome': r['outcome'], 'detail': json.loads(r['detail'])} for r in rows]


class DockLinkClient:
    """Pinned HTTPS to a dock controller on the private network: GET /status, POST /mode."""
    def __init__(self, link, timeout_s=3.):
        self.endpoint, self.credential = link['endpoint'], link['credential']
        self.fingerprint = aiohttp.Fingerprint(bytes.fromhex(link['fingerprint']))
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self.session = None

    async def open(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self.fingerprint), timeout=self.timeout,
                                                 headers={'Authorization': 'Bearer ' + self.credential})

    async def status(self):
        await self.open()
        async with self.session.get(self.endpoint + '/status') as response:
            if response.status != 200:
                raise RuntimeError(f'Dock controller answered {response.status}')
            return check_status(await response.json())

    async def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError('Mode must be off, charge or storage')
        await self.open()
        async with self.session.post(self.endpoint + '/mode', json={'mode': mode}) as response:
            if response.status != 200:
                raise RuntimeError(f'Dock controller refused mode {mode}: {response.status}')
            return check_status(await response.json())

    async def close(self):
        if self.session:
            await self.session.close(); self.session = None


def check_status(status):
    """Shape of a dock status, from the controller or the simulator; anything else is an error, not data."""
    keys = {'mode', 'supply_v', 'pin_current_ma', 'pad_temp_c', 'contact', 'fault', 'uptime_s'}
    if not isinstance(status, dict) or not keys <= set(status) or status['mode'] not in MODES or not isinstance(status['contact'], bool):
        raise RuntimeError('Malformed dock status')
    for k in ('supply_v', 'pin_current_ma', 'pad_temp_c', 'uptime_s'):
        if type(status[k]) not in (int, float) or not math.isfinite(status[k]):
            raise RuntimeError('Malformed dock status')
    if status['fault'] is not None and not isinstance(status['fault'], str):
        raise RuntimeError('Malformed dock status')
    return status
