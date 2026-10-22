"""Versioned local hardware registry. A run pins content, never a mutable name."""
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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get('DRONE137_DATA_DIR',ROOT/'.local/data')).resolve()/'airframes.sqlite3'
DEFAULTS = ROOT/'config/airframes.json'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate(profile):
    p = copy.deepcopy(profile)
    if not isinstance(p, dict) or set(p) != {'id','name','kind','airframe','camera','sensors','limits','evidence'}:
        raise ValueError('Expected id, name, kind, airframe, camera, sensors, limits and evidence')
    if not isinstance(p['id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', p['id']):
        raise ValueError('Profile ID must be a lowercase slug')
    if not isinstance(p['name'], str) or not 1 <= len(p['name']) <= 100 or p['kind'] != 'quad-x':
        raise ValueError('Provide a name and supported quad-x airframe kind')
    def number(value, low, high, label):
        if type(value) not in (float,int) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{label} must be finite and within {low}..{high}')
    fields = {
        'airframe': {'mass_kg':(.25,8), 'inertia_xx':(.001,1), 'inertia_yy':(.001,1), 'inertia_zz':(.001,2),
            'geometry_xy_scale':(.5,1.5), 'motor_constant':(1e-7,1e-3), 'moment_constant':(.001,.1),
            'motor_time_up_s':(.005,.2), 'motor_time_down_s':(.005,.3), 'max_rotor_rad_s':(300,2000),
            'rotor_drag':(0,.01), 'rotor_radius_m':(.06,.3), 'body_radius_m':(.15,.65)},
        'limits': {'speed_m_s':(.1,.6), 'acceleration_m_s2':(.2,1.2), 'clearance_margin_m':(.1,.4), 'mission_seconds':(30,600)},
        'sensors': {'range_m':(1,8), 'range_noise_m':(0,.05), 'range_dropout':(0,.2),
            'position_noise_m':(.005,.1), 'drift_m_per_s':(0,.002), 'position_delay_ms':(0,200), 'max_position_sigma_m':(.05,.3)},
    }
    for section, bounds in fields.items():
        if not isinstance(p[section],dict) or set(p[section]) != set(bounds):
            raise ValueError(f'Unexpected or missing {section} parameters')
        for name, (lo,hi) in bounds.items(): number(p[section][name],lo,hi,f'{section}.{name}')
    a=p['airframe']; inertias=[a['inertia_xx'],a['inertia_yy'],a['inertia_zz']]
    if 2*max(inertias)>sum(inertias)+1e-9: raise ValueError('Inertia violates triangle inequality')
    if 4*a['motor_constant']*a['max_rotor_rad_s']**2 < 1.5*a['mass_kg']*9.81:
        raise ValueError('Insufficient thrust reserve for this mass')
    # Enclose the scaled x500 rotor layout, including actual rotor collision radius.
    if a['body_radius_m'] < math.sqrt(2)*.174*a['geometry_xy_scale']+a['rotor_radius_m']:
        raise ValueError('Body radius must enclose the rotor envelope')
    c=p['camera']
    names={'width','height','fx','fy','cx','cy','distortion','pitch_degrees','offset_flu_m',
           'exposure_ms','rolling_shutter_ms','latency_ms','jitter_ms','drop_probability','burst_frames','jpeg_quality'}
    if not isinstance(c,dict) or set(c)!=names: raise ValueError('Unexpected or missing camera parameters')
    for k in ('width','height','burst_frames'):
        if type(c[k]) is not int: raise ValueError(f'{k} must be an integer')
    for k,lo,hi in [('width',320,1280),('height',240,720),('fx',200,2500),('fy',200,2500),
                    ('cx',0,c['width']),('cy',0,c['height']),('pitch_degrees',-45,20),
                    ('exposure_ms',.1,40),('rolling_shutter_ms',0,40),('latency_ms',0,300),
                    ('jitter_ms',0,100),('drop_probability',0,.2),('burst_frames',0,5),('jpeg_quality',.4,.95)]:
        number(c[k],lo,hi,'camera.'+k)
    for name, count,lo,hi in [('distortion',5,-.5,.5),('offset_flu_m',3,-.5,.5)]:
        if not isinstance(c[name],list) or len(c[name])!=count: raise ValueError('Invalid '+name)
        for v in c[name]: number(v,lo,hi,name)
    evidence=p['evidence']
    if not isinstance(evidence,dict) or set(evidence)!={'status','notes','files'} or evidence['status'] not in ('provisional','measured-unvalidated'):
        raise ValueError('Evidence status must be provisional or measured-unvalidated; qualification is a separate evaluation')
    if not isinstance(evidence['notes'],str) or not 1<=len(evidence['notes'])<=2000 or not isinstance(evidence['files'],list):
        raise ValueError('Evidence notes and file references required')
    for f in evidence['files']:
        if not isinstance(f,dict) or set(f)!={'path','sha256','purpose'} or not all(isinstance(v,str) for v in f.values()) or not re.fullmatch('[0-9a-f]{64}',f['sha256']):
            raise ValueError('Evidence files require path, SHA256 and purpose')
    if evidence['status']=='measured-unvalidated' and not evidence['files']: raise ValueError('Measured values require evidence references')
    encoded(p)
    return p


class Airframes:
    def __init__(self, path=DEFAULT_DB):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS profiles(id TEXT, revision INTEGER, name TEXT NOT NULL,
                    content TEXT NOT NULL, sha256 TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(id,revision));
                CREATE TABLE IF NOT EXISTS assignments(vehicle_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, FOREIGN KEY(profile_id,revision) REFERENCES profiles(id,revision));
                CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, created_at REAL NOT NULL,
                    snapshots TEXT NOT NULL, result_path TEXT);
            ''')
        for p in json.loads(DEFAULTS.read_text()):
            try:self.save(p,expected_revision=0)
            except ValueError:
                if not self.get(p['id']):raise

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:yield db
        finally:db.close()

    def save(self, profile, expected_revision):
        p=validate(profile)
        if type(expected_revision) is not int or expected_revision<0:raise ValueError('expected_revision required')
        content=encoded(p);digest=hashlib.sha256(content.encode()).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            latest=db.execute('SELECT COALESCE(MAX(revision),0) FROM profiles WHERE id=?',(p['id'],)).fetchone()[0]
            if latest!=expected_revision:raise ValueError('Profile changed; reload before saving a new revision')
            db.execute('INSERT INTO profiles VALUES(?,?,?,?,?,?)',(p['id'],latest+1,p['name'],content,digest,time.time()))
        return self.get(p['id'],latest+1)

    def get(self, identity, revision=None):
        with self.connection() as db:
            row=db.execute('SELECT * FROM profiles WHERE id=?'+(' AND revision=?' if revision is not None else '')+' ORDER BY revision DESC LIMIT 1',
                           (identity,revision) if revision is not None else (identity,)).fetchone()
        if not row:raise ValueError('Unknown airframe profile or revision')
        p=json.loads(row['content'])
        if hashlib.sha256(encoded(p).encode()).hexdigest()!=row['sha256']:raise ValueError('Airframe registry integrity failure')
        validate(p)
        return {'profile':p,'revision':row['revision'],'sha256':row['sha256'],'created_at':row['created_at']}

    def list(self):
        with self.connection() as db:ids=[r[0] for r in db.execute('SELECT DISTINCT id FROM profiles ORDER BY id')]
        return [self.get(i) for i in ids]

    def resolve(self, reference):
        if not isinstance(reference,str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}(?:@[1-9][0-9]*)?',reference):raise ValueError('Use a profile ID or ID@revision')
        identity,sep,rev=reference.partition('@')
        return self.get(identity,int(rev) if sep else None)

    def assign(self, vehicle_id, reference):
        if not isinstance(vehicle_id,str) or not re.fullmatch('[a-z][a-z0-9-]{1,63}',vehicle_id):raise ValueError('Invalid aircraft ID')
        p=self.resolve(reference)
        with self.connection() as db:
            db.execute('INSERT INTO assignments VALUES(?,?,?) ON CONFLICT(vehicle_id) DO UPDATE SET profile_id=excluded.profile_id,revision=excluded.revision',
                       (vehicle_id,p['profile']['id'],p['revision']))
        return p

    def assigned(self, vehicle_id):
        with self.connection() as db:row=db.execute('SELECT profile_id,revision FROM assignments WHERE vehicle_id=?',(vehicle_id,)).fetchone()
        return self.get(*row) if row else self.get('reference-quad')

    def freeze(self, identity, snapshots, result_path=None):
        # Caller already holds the exact revisions: no latest-name lookup here.
        for s in snapshots:
            stored=self.get(s['profile']['id'],s['revision'])
            if stored!=s:raise ValueError('Snapshot does not match stored revision')
        with self.connection() as db:
            db.execute('INSERT INTO experiments VALUES(?,?,?,?)',(identity,time.time(),encoded(snapshots),str(result_path) if result_path else None))
