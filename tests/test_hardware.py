import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from app.airframes import Airframes,validate
from app.camera_geometry import distort,undistort
from app.observed_navigation import ObservedNavigation
from sim.hardware import apply_profile
from sim.flight_world import sdf,clear,VIEWS
from sim.asset_world import build
from sim.hard_flight import cases
from sim.range_sensor import RangeSensor
from sim.room_assets import load_room,inspect_glb,validate_room

ROOT=Path(__file__).resolve().parents[1]


class HardwareRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Airframes(Path(self.tmp.name)/'airframes.sqlite3')
    def tearDown(self):self.tmp.cleanup()
    def test_revision_pinning_and_assignments_survive_restart(self):
        first=self.db.assign('scout-one','reference-quad');p=copy.deepcopy(first['profile']);p['camera']['latency_ms']=200
        second=self.db.save(p,expected_revision=1)
        self.assertEqual(second['revision'],2);self.assertEqual(self.db.assigned('scout-one'),first)
        again=Airframes(self.db.path);self.assertEqual(again.resolve('reference-quad@1'),first)
        self.assertEqual(again.resolve('reference-quad'),second)
        with self.assertRaises(ValueError):again.save(p,expected_revision=1)
        again.freeze('trial',[first,second]);bad=copy.deepcopy(first);bad['profile']['airframe']['mass_kg']=3
        with self.assertRaises(ValueError):again.freeze('tampered',[bad])
    def test_invalid_physics_and_nonfinite_inputs_rejected(self):
        original=self.db.resolve('reference-quad')['profile']
        for section,key,value in [('airframe','mass_kg',100),('airframe','inertia_zz',1),('airframe','body_radius_m',.15),('camera','fx',float('nan')),('sensors','range_dropout',.5)]:
            p=copy.deepcopy(original);p[section][key]=value
            with self.assertRaises(ValueError):validate(p)
        p=copy.deepcopy(original);p['evidence']['status']='measured-unvalidated'
        with self.assertRaises(ValueError):validate(p)
    def test_sdf_applies_mass_thrust_and_removes_gps_for_each_airframe(self):
        px4=ROOT/'.local/build/PX4-Autopilot'
        if not px4.exists():self.skipTest('Native models absent')
        for snapshot in self.db.list():
            scene=apply_profile(build(cases()[0]),snapshot,True)
            folder=Path(self.tmp.name)/snapshot['profile']['id'];folder.mkdir()
            tree=ET.parse(sdf(scene,px4,folder/'world.sdf'));base=ET.parse(folder/'x500-base-draft.sdf')
            a=snapshot['profile']['airframe']
            self.assertAlmostEqual(sum(float(m.text) for m in base.findall('.//inertial/mass')),a['mass_kg'])
            self.assertEqual(base.findall('.//sensor[@type="navsat"]'),[])
            self.assertEqual(len(tree.findall('.//plugin[@name="gz::sim::systems::MulticopterMotorModel"]')),4)
            self.assertTrue(all(float(m.text)==a['motor_constant'] for m in tree.findall('.//motorConstant')))
            self.assertAlmostEqual(float(base.find('.//link[@name="rotor_0"]/collision/geometry/box/size').text.split()[0]),2*a['rotor_radius_m'])
    def test_calibrated_projection_round_trip_and_native_ray(self):
        from app.flight_localization import detection
        c=self.db.resolve('reference-quad')['profile']['camera']
        for x in (-.5,-.25,0,.25,.5):
            for y in (-.3,0,.3):
                xd,yd=distort(x,y,c['distortion']);actual=undistort(xd*c['fx']+c['cx'],yd*c['fy']+c['cy'],c)
                self.assertLess(math.dist(actual,(x,y)),1e-7)
        pose={'position':[2,3,1.5],'quaternion':[0,0,0,1]};ray=detection(pose,[490,490,510,510],'v',c)
        self.assertAlmostEqual(ray['ray'][2],math.sin(math.radians(c['pitch_degrees'])))

    def test_snapshot_read_is_independent_of_caller_mutations(self):
        a=self.db.resolve('reference-quad');a['profile']['camera']['fx']=1
        self.assertNotEqual(self.db.resolve('reference-quad')['profile']['camera']['fx'],1)


class SensorOnlyNavigation(unittest.TestCase):
    def setUp(self):
        self.world=build(cases()[0]);self.p=json.loads((ROOT/'config/airframes.json').read_text())[0]
        self.sensor=RangeSensor(self.world,self.p['sensors']);self.nav=ObservedNavigation(12,10,[4.4,1.25],.38,.26)
    def scan(self,position,turns=8):
        for _ in range(turns):self.nav.integrate([*position,0],self.sensor.scan({'position':position+[1.5],'quaternion':[0,0,0,1]},1),1)
    def test_unknown_stale_or_missing_ranges_never_authorize_motion(self):
        with self.assertRaises(RuntimeError):self.nav.next_step([4.4,1.25],VIEWS[0])
        self.assertFalse(self.nav.motion_clear([4.4,1.25],VIEWS[0],0,1))
        self.scan([4.4,1.25]);self.assertFalse(self.nav.motion_clear([4.4,1.25],VIEWS[0],0,2))
        self.assertLess(self.nav.report()['observed_fraction'],.5)
    def test_unknown_map_routes_around_occluders_and_returns_without_geometry_access(self):
        p=[4.4,1.25]
        for goal in VIEWS+[[4.4,1.25]]:
            for _ in range(100):
                self.scan(p)
                if math.dist(p,goal[:2])<.18:break
                step=self.nav.next_step(p,goal)
                # Independent hidden-world grader checks the entire swept path.
                for i in range(21):self.assertGreater(clear(self.world,[p[j]+(step[j]-p[j])*i/20 for j in (0,1)]),.6)
                p=step
            else:self.fail('Observed navigation failed to reach a view')
        self.assertLess(math.dist(p,[4.4,1.25]),.18)
        self.assertFalse(hasattr(self.nav,'world'));self.assertFalse(hasattr(self.nav,'boxes'))
    def test_fault_and_changed_obstacle_stop_motion(self):
        p=[4.4,1.25];self.scan(p);raw=self.sensor.scan({'position':p+[1.5],'quaternion':[0,0,0,1]},2)
        for r in raw:r['distance']=.4;r['hit']=True
        for _ in range(3):self.nav.integrate([*p,0],raw,2)
        self.assertFalse(self.nav.motion_clear(p,[4.4,2],.4,2))
        with self.assertRaises(RuntimeError):self.nav.next_step(p,[4.4,2])
