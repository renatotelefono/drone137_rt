import math
import asyncio
import time
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from app.contracts import Telemetry
import xml.etree.ElementTree as ET
from adapters.native_flight import NativeFlight,quaternion,rotate,preflight_settled,takeoff_confirmed
from app.flight_localization import detection,triangulate
from sim.flight_world import scene,route,segment_clear,HOME,VIEWS,sdf


class FlightGeometry(unittest.TestCase):
    def test_tenfold_props_and_deterministic_assets(self):
        a,b=scene(),scene()
        self.assertEqual(a,b)
        self.assertEqual(a['complexity']['props'],10*a['complexity']['baseline_props'])
        self.assertEqual(len({x['id'] for x in a['obstacles']}),120)
        self.assertFalse(any(x['kind']=='extinguisher' for x in scene(target=False)['obstacles']))

    def test_route_segments_inflate_drone_and_do_not_cut_partition(self):
        world=scene();last=HOME
        for destination in VIEWS+[HOME]:
            points=route(world,last,destination)
            for point in points:
                self.assertTrue(segment_clear(world,last,point));last=point
        self.assertRaises(ValueError,route,world,HOME,[6,7])

    def test_pixel_right_is_body_right_and_tilt_changes_ray(self):
        estimate={'position':[2,3,1.5],'quaternion':[0,0,0,1]}
        center=detection(estimate,[490,490,510,510],'a')
        right=detection(estimate,[700,490,720,510],'b')
        self.assertLess(right['ray'][1],0)
        self.assertAlmostEqual(center['ray'][2],math.sin(math.radians(-10)))
        self.assertEqual(center['origin'],[2.12,3,1.52])
        q=quaternion(0,0,math.pi/2)
        self.assertAlmostEqual(rotate(q,[1,0,0])[1],1)

    def test_triangulate_real_attitude_rays_and_fail_closed(self):
        target=[4.4,8.9,.7]
        def ray(p,name):
            delta=[a-b for a,b in zip(target,p)];length=math.sqrt(sum(v*v for v in delta))
            return {'origin':p,'ray':[v/length for v in delta],'view_id':name}
        a,b=ray([4.3,5.8,1.5],'a'),ray([3.5,5.8,1.5],'b')
        location=triangulate(a,b)
        self.assertLess(math.dist(location['xyz_m'],target),1e-9)
        self.assertIsNone(triangulate(a,a))
        self.assertIsNone(triangulate(a,{**b,'ray':a['ray']}))
        self.assertIsNone(triangulate(a,{**b,'ray':[-v for v in b['ray']]}))

    def test_native_scene_retains_physical_collisions_and_sensor_units(self):
        px4=Path(__file__).resolve().parents[1]/'.local/build/PX4-Autopilot'
        if not px4.is_dir():self.skipTest('Pinned native simulator not installed')
        with tempfile.TemporaryDirectory() as directory:
            p=sdf(scene(),px4,Path(directory)/'world.sdf');root=ET.parse(p)
        models=root.findall('.//world/model')
        self.assertEqual(sum(m.get('name','').startswith('prop-') for m in models),120)
        for m in models:
            if m.get('name','').startswith('prop-'):self.assertIsNotNone(m.find('link/collision/geometry/box/size'))
        magnet=root.find('.//plugin[@name="gz::sim::systems::Magnetometer"]')
        self.assertEqual(magnet.findtext('use_units_gauss'),'false')
        self.assertEqual(magnet.findtext('use_earth_frame_ned'),'false')
        self.assertEqual(len(root.findall('.//plugin[@name="gz::sim::systems::MulticopterMotorModel"]')),4)


class FlightScheduling(unittest.IsolatedAsyncioTestCase):
    def test_altitude_drift_while_landed_does_not_confirm_takeoff(self):
        health=SimpleNamespace(is_armable=True,is_local_position_ok=True)
        ground=Telemetry((0,0,0),.02,time.monotonic(),True,False)
        drift=Telemetry((0,0,2.2),.02,time.monotonic(),True,False)
        airborne=Telemetry((0,0,1.5),.02,time.monotonic(),True,True)
        self.assertTrue(preflight_settled(health,ground))
        self.assertFalse(preflight_settled(health,drift))
        self.assertFalse(takeoff_confirmed(drift))
        self.assertTrue(takeoff_confirmed(airborne))

    async def test_dense_route_does_not_starve_sensor_heartbeat(self):
        flight=NativeFlight.__new__(NativeFlight)
        flight.scene={};flight.estimated=lambda:{'position':[1.25,1.25,1.5]}
        flight.check=lambda:None
        async def reach(*args):pass
        flight.reach=reach
        beats=[]
        async def heartbeat():
            while True:beats.append(time.monotonic());await asyncio.sleep(.01)
        def slow_plan(*args):time.sleep(.15);return [[2,2]]
        task=asyncio.create_task(heartbeat())
        try:
            with patch('adapters.native_flight.route',slow_plan):await flight.fly([2,2,1.5,0])
            self.assertGreaterEqual(len(beats),5)
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
