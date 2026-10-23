"""Immutable SQLite component revisions, assemblies and frozen experiment inputs."""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from sim.component_defaults import seeds

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get('DRONE137_DATA_DIR', ROOT/'.local/data'))/'components.sqlite3'
BOUNDS = {
    'frame': {'mass_kg':(.001,.2),'motor_diagonal_m':(.04,.3),'guard_clearance_m':(0,.01),'drag_area_m2':(0,.1),'body_height_m':(.005,.08)},
    'propulsion': {'mass_kg':(.0001,.03),'prop_diameter_m':(.02,.15),'time_up_s':(.005,.3),'time_down_s':(.005,.5),
                   'torque_per_thrust_m':(.0001,.05),'max_voltage_v':(3,5)},
    'battery': {'mass_kg':(.001,.1),'capacity_mah':(50,3000),'resistance_ohm':(.001,2),'full_v':(3.5,4.35),'empty_v':(2.8,3.8),'cutoff_v':(2.5,3.6)},
    'avionics': {'mass_kg':(.001,.05),'idle_current_a':(0,2),'control_hz':(100,1000),'camera_width':(160,1920),
                 'camera_height':(120,1080),'camera_fps':(1,30),'camera_latency_ms':(0,1000),'link_timeout_s':(.1,2)},
    'imu': {'mass_kg':(.0001,.02),'gyro_noise_rad_s':(0,.2),'gyro_bias_rad_s':(0,.1)},
    'range': {'mass_kg':(.0001,.02),'noise_m':(0,.2),'max_range_m':(.2,3)},
    'driver': {'mass_kg':(.0001,.02),'resistance_ohm':(0,1)},
}


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def model_digest():
    return hashlib.sha256((ROOT/'app/ui/micro-physics.mjs').read_bytes()).hexdigest()


def slug(value):
    if not isinstance(value,str) or not re.fullmatch('[a-z][a-z0-9-]{1,63}',value):
        raise ValueError('ID must be a lowercase slug, 2–64 characters')


def number(value,lo,hi,label):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'{label} must be finite and within {lo}..{hi}')


def validate_component(c):
    if not isinstance(c,dict) or set(c)!={'id','name','kind','parameters','evidence'}:raise ValueError('Invalid component fields')
    slug(c['id'])
    if not isinstance(c['name'],str) or not 1<=len(c['name'])<=120 or c['kind'] not in BOUNDS:raise ValueError('Invalid component name/kind')
    p=c['parameters'];expected=set(BOUNDS[c['kind']])|({'curve'} if c['kind']=='propulsion' else set())
    if not isinstance(p,dict) or set(p)!=expected:raise ValueError('Unexpected component parameters')
    for k,(lo,hi) in BOUNDS[c['kind']].items():number(p[k],lo,hi,k)
    if c['kind']=='avionics':
        if p['control_hz'] not in (125,250):raise ValueError('The 4 ms lab supports 125 or 250 Hz control updates')
        if any(type(p[k]) is not int for k in ('control_hz','camera_width','camera_height','camera_fps')):
            raise ValueError('Control rate, image dimensions and frame rate must be integers')
    if c['kind']=='battery' and not p['cutoff_v']<=p['empty_v']<p['full_v']:raise ValueError('Invalid battery voltages')
    if c['kind']=='propulsion':
        curve=p['curve']
        if not isinstance(curve,list) or not 3<=len(curve)<=256 or curve[0]!=[0,0,0,0]:raise ValueError('Curve must start at zero with 3–256 samples')
        for row in curve:
            if not isinstance(row,list) or len(row)!=4:raise ValueError('Curve rows: motor volts, thrust N, motor current A, RPM')
            for x,hi in zip(row,(p['max_voltage_v'],5,20,100000)):number(x,0,hi,'curve')
        for a,b in zip(curve,curve[1:]):
            if b[0]<=a[0] or any(y<x for x,y in zip(a[1:],b[1:])):raise ValueError('Curve must be monotonic')
        if curve[-1][1]<=0:raise ValueError('Curve needs positive thrust')
    e=c['evidence']
    if not isinstance(e,dict) or set(e)!=expected:raise ValueError('Every parameter requires evidence')
    for item in e.values():
        if not isinstance(item,dict) or set(item)!={'status','source','note'}:raise ValueError('Invalid evidence record')
        if item['status'] not in ('estimated','specified','derived','measured'):raise ValueError('Invalid evidence status')
        if not isinstance(item['note'],str) or not 1<=len(item['note'])<=2000:raise ValueError('Evidence note required')
        if not isinstance(item['source'],str) or len(item['source'])>1000:raise ValueError('Invalid evidence source')
        if item['status']!='estimated' and not item['source']:raise ValueError('Non-estimated parameters need source references')
    encoded(c)
    return c


class Components:
    def __init__(self,path=DEFAULT_DB):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS revisions(
                type TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, content TEXT NOT NULL,
                sha256 TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(type,id,revision));
                CREATE TABLE IF NOT EXISTS trials(id TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                sha256 TEXT NOT NULL, created_at REAL NOT NULL, result TEXT);''')
        parts,configs=seeds()
        for kind,items in [('component',parts),('configuration',configs)]:
            for item in items:
                with self.connection() as db:exists=db.execute('SELECT 1 FROM revisions WHERE type=? AND id=?',(kind,item['id'])).fetchone()
                if not exists:self.save(kind,item,0)

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def get(self,kind,reference):
        if kind not in ('component','configuration'):raise ValueError('Invalid record type')
        if not isinstance(reference,str) or not re.fullmatch('[a-z][a-z0-9-]{1,63}(?:@[1-9][0-9]*)?',reference):raise ValueError('Invalid component/configuration reference')
        identity,_,revision=reference.partition('@')
        with self.connection() as db:
            row=db.execute('SELECT * FROM revisions WHERE type=? AND id=?'+(' AND revision=?' if revision else '')+' ORDER BY revision DESC LIMIT 1',
                (kind,identity,int(revision)) if revision else (kind,identity)).fetchone()
        if not row:raise ValueError('Unknown component/configuration revision')
        content=json.loads(row['content'])
        if digest(content)!=row['sha256']:raise ValueError('Registry checksum mismatch')
        return dict(content=content,revision=row['revision'],sha256=row['sha256'])

    def validate_config(self,c):
        if not isinstance(c,dict) or set(c)!={'id','name','components','notes'}:raise ValueError('Invalid configuration fields')
        slug(c['id'])
        if not isinstance(c['name'],str) or not 1<=len(c['name'])<=120 or not isinstance(c['notes'],str) or len(c['notes'])>2000:raise ValueError('Invalid configuration name/notes')
        refs=c['components'];required={'frame','propulsion','battery','avionics','imu','driver'}
        if not isinstance(refs,dict) or not required<=set(refs)<=required|{'range'}:raise ValueError('Required component slots missing')
        parts={}
        for slot,ref in refs.items():
            if not isinstance(ref,str) or '@' not in ref:raise ValueError('Pin every component to ID@revision')
            part=self.get('component',ref)['content'];validate_component(part)
            if part['kind']!=slot:raise ValueError('Component does not fit slot')
            parts[slot]=part['parameters']
        if parts['battery']['full_v']>parts['propulsion']['max_voltage_v']:raise ValueError('Battery exceeds propulsion voltage limit')
        if parts['frame']['motor_diagonal_m']/math.sqrt(2)<=parts['propulsion']['prop_diameter_m']+2*parts['frame']['guard_clearance_m']:
            raise ValueError('Adjacent propeller/guard envelopes overlap')
        encoded(c)

    def save(self,kind,content,expected_revision):
        if kind=='component':validate_component(content)
        elif kind=='configuration':self.validate_config(content)
        else:raise ValueError('Invalid record type')
        if type(expected_revision) is not int or expected_revision<0:raise ValueError('expected_revision required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            last=db.execute('SELECT COALESCE(MAX(revision),0) FROM revisions WHERE type=? AND id=?',(kind,content['id'])).fetchone()[0]
            if last!=expected_revision:raise ValueError('Revision changed; reload before saving')
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)',(kind,content['id'],last+1,encoded(content),digest(content),time.time()))
        return self.get(kind,content['id'])

    def list(self,kind):
        with self.connection() as db:ids=[r[0] for r in db.execute('SELECT DISTINCT id FROM revisions WHERE type=? ORDER BY id',(kind,))]
        return [self.get(kind,i) for i in ids]

    def assemble(self,reference):
        c=self.get('configuration',reference);self.validate_config(c['content'])
        parts={slot:self.get('component',ref) for slot,ref in c['content']['components'].items()}
        count=lambda slot:4 if slot=='propulsion' else 1
        mass=sum(p['content']['parameters']['mass_kg']*count(s) for s,p in parts.items())
        evidence=[v for p in parts.values() for v in p['content']['evidence'].values()]
        result=dict(configuration=c,components=parts,mass_kg=mass,physical_enabled=False,
            evidence_counts={s:sum(e['status']==s for e in evidence) for s in ('estimated','specified','derived','measured')},
            propulsion_evidence=parts['propulsion']['content']['evidence']['curve']['status'])
        result['sha256']=digest(result)
        return result

    def freeze(self,reference,scenario,seed=137,dt_s=.004):
        if scenario not in ('nominal','low-battery','gust','link-loss','weak-motor','pessimistic'):raise ValueError('Unknown scenario')
        if type(seed) is not int or not 0<=seed<=4294967295:raise ValueError('Seed must be an unsigned 32-bit integer')
        if dt_s not in (.002,.004):raise ValueError('Qualification timestep must be 2 or 4 ms')
        snapshot=dict(assembly=self.assemble(reference),scenario=scenario,engine='rapier-0.21.0',dt_s=dt_s,seed=seed,
                      model_sha256=model_digest())
        identity=uuid.uuid4().hex
        with self.connection() as db:db.execute('INSERT INTO trials VALUES(?,?,?,?,NULL)',(identity,encoded(snapshot),digest(snapshot),time.time()))
        return dict(id=identity,sha256=digest(snapshot),snapshot=snapshot)

    def record(self,identity,result):
        if not isinstance(result,dict) or len(encoded(result))>200000:raise ValueError('Invalid result')
        with self.connection() as db:
            row=db.execute('SELECT sha256,result,snapshot FROM trials WHERE id=?',(identity,)).fetchone()
            if not row or row['result'] is not None:raise ValueError('Unknown/already completed trial')
            if result.get('trial_sha256')!=row['sha256']:raise ValueError('Result does not match frozen trial')
            snapshot=json.loads(row['snapshot']);assembly=snapshot['assembly']
            for key,expected in [('configuration',assembly['configuration']['content']['id']),('scenario',snapshot['scenario']),
                                 ('engine',snapshot['engine']),('assembly_sha256',assembly['sha256']),
                                 ('seed',snapshot['seed']),('configuration_revision',assembly['configuration']['revision'])]:
                if result.get(key)!=expected:raise ValueError('Result identity does not match frozen trial')
            required={'liftoff','hover','transit','landed','controlled_attitude','no_obstacle_contact','battery_valid','landing_speed','thrust_reserve'}
            if snapshot['scenario']=='link-loss':required.add('command_expiry')
            gates=result.get('gates')
            if not isinstance(gates,dict) or set(gates)!=required or any(type(v) is not bool for v in gates.values()):raise ValueError('Incomplete simulation gates')
            flight=all(v for k,v in gates.items() if k!='thrust_reserve' and not(k=='transit' and snapshot['scenario']=='link-loss'))
            if result.get('flight_passed') is not flight or result.get('engineering_passed') is not (flight and gates['thrust_reserve']):
                raise ValueError('Pass flags disagree with simulation gates')
            # This records simulation output, never a hardware/recognition qualification.
            result={**result,'physical_enabled':False,'recognition_tested':False,
                    'model_sha256':snapshot.get('model_sha256','legacy')}
            db.execute('UPDATE trials SET result=? WHERE id=?',(encoded(result),identity))

    def history(self):
        with self.connection() as db:
            return [dict(id=r['id'],sha256=r['sha256'],created_at=r['created_at'],result=json.loads(r['result']) if r['result'] else None)
                    for r in db.execute('SELECT * FROM trials ORDER BY created_at DESC LIMIT 100')]
