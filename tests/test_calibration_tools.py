import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from scripts.identify_airframe import motor_fit,trajectory_agreement
from scripts.reconstruct_room import reconstruct
from sim.room_assets import load_room,inspect_glb


class CalibrationTools(unittest.TestCase):
    def test_motor_fit_recovers_known_parameters_and_needs_excitation(self):
        rpm=0;samples=[]
        for i in range(900):
            command=600 if i<300 else 900 if i<600 else 100
            samples.append(dict(time_s=i*.005,rotor_rad_s=rpm,command_rad_s=command,thrust_n=8.5e-6*rpm*rpm))
            rpm=command+(rpm-command)*math.exp(-.005/(.025 if command>rpm else .045))
        r=motor_fit(samples)
        self.assertAlmostEqual(r['motor_constant'],8.5e-6,places=10)
        self.assertLess(abs(r['motor_time_up_s']-.025),.0003);self.assertLess(abs(r['motor_time_down_s']-.045),.0003)
        with self.assertRaises(ValueError):motor_fit(samples[:10])
    def test_trajectory_comparison_does_not_align_away_errors(self):
        a=[dict(time_s=i*.1,position_m=[i*.01,0,0]) for i in range(30)]
        b=[dict(time_s=i*.1,position_m=[i*.01,.05,0]) for i in range(30)]
        self.assertAlmostEqual(trajectory_agreement(a,b)['position_rmse_m'],.05)
        with self.assertRaises(ValueError):trajectory_agreement(a,b[::-1])
    def test_rgbd_reconstruction_packaging_coordinates_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);Image.fromarray(np.full((24,32,3),150,dtype=np.uint8)).save(root/'rgb.png')
            Image.fromarray(np.full((24,32),2000,dtype=np.uint16)).save(root/'depth.png')
            points=[[1,4,1],[3,4,1],[1,4,2]]
            room={'source_kind':'synthetic-fixture','provenance':'Known plane fixture for an independent geometric test.',
                  'dimensions_m':[12,10,3],'coordinate_frame':'ENU-metres; GLB is x=east,y=up,z=south',
                  'collision_boxes':[dict(x=6,y=4,sx=3,sy=.1,bottom=0,height=3)],'unknown_boxes':[],
                  'control_points':[dict(mesh_enu_m=p,measured_enu_m=p) for p in points]}
            spec={'room':room,'camera':dict(width=32,height=24,fx=30,fy=30,cx=16,cy=12,rectified=True),
                  'depth_scale_m':.001,'stride':4,'frames':[{'rgb':'rgb.png','depth':'depth.png',
                  'camera_to_enu':[[1,0,0,6],[0,0,1,2],[0,-1,0,1.5],[0,0,0,1]]}]}
            source=root/'manifest.json';source.write_text(json.dumps(spec));audit=reconstruct(source,root/'package')
            self.assertEqual(audit['triangles'],70)
            result,asset,audit=load_room(root/'package/room.json')
            self.assertFalse(audit['physical_agreement_verified']);self.assertEqual(len(result['sources']),2)
            self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(),result['visual_sha256'])
            asset.write_bytes(asset.read_bytes()+b'tamper')
            with self.assertRaises(ValueError):load_room(root/'package/room.json')
            with self.assertRaises(ValueError):inspect_glb(b'not a model')
