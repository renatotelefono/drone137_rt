import asyncio
import math
import unittest

import numpy as np

from app.dock_tags import load_geometry
from sim.dock_world import DockSimulation, DockWorld, Estimator, KinematicDockVehicle, kinematic_docking, return_gate_start

CAMERA = {'width': 960, 'height': 540, 'vertical_fov': 41, 'effects': {'distortion': -.025, 'blur': .6, 'noise': .018},
          'jpeg_quality': .72, 'latency_ms': 120, 'drop_every_n': 9}


def run(coro):
    return asyncio.run(coro)


class KinematicDocking(unittest.TestCase):
    def setUp(self):
        self.g = load_geometry()

    def test_docks_from_return_gate_errors_with_one_attempt(self):
        for seed in range(5):
            sim, error = kinematic_docking(seed, self.g, CAMERA)
            result = run(sim.phase().run())
            truth = sim.truth()
            self.assertEqual(result['outcome'], 'docked', (seed, result['states'], result.get('error')))
            self.assertEqual(result['attempts'], 1, seed)
            self.assertLess(abs(truth['f_m']), .02); self.assertLess(abs(truth['l_m']), .02); self.assertLess(abs(truth['yaw_deg']), 5)
            self.assertTrue(truth['landed']); self.assertEqual(truth['stand_contacts'], 0)
            self.assertTrue(result['dock_status']['contact']); self.assertGreaterEqual(result['dock_status']['pin_current_ma'], 20)
            self.assertTrue(result['estimate_reset'])
            est_p, est_yaw = sim.vehicle.estimate()
            self.assertLess(np.linalg.norm(est_p - sim.vehicle.position), .02)
            self.assertLess(result['duration_s'], 120)

    def test_return_gate_draw_stays_inside_the_gate(self):
        rng = np.random.default_rng(3)
        for _ in range(200):
            e = return_gate_start(rng, self.g)
            self.assertLessEqual(math.hypot(e[0], e[1]), .4); self.assertLessEqual(abs(e[3]), math.radians(15))

    def test_dock_not_found_lands_in_place(self):
        sim, error = kinematic_docking(1, self.g, CAMERA)
        sim.camera.renderer.corners = {}   # the stand carries no tags
        result = run(sim.phase().run())
        self.assertEqual(result['outcome'], 'dock_not_found')
        self.assertEqual([s['state'] for s in result['states']][-2:], ['acquire', 'land-in-place'])
        self.assertTrue(sim.vehicle.landed); self.assertEqual(result['detections'], 0)

    def test_no_contact_retries_then_reports(self):
        sim, error = kinematic_docking(2, self.g, CAMERA)
        sim.controller.supply_v = 0.
        sim.controller.five_volts_on = lambda: False   # dock electronics dead: never 5 V, never contact
        result = run(sim.phase().run())
        self.assertEqual(result['outcome'], 'docked_without_contact')
        self.assertEqual(result['attempts'], self.g['procedure']['retries'] + 1)
        truth = sim.truth()
        self.assertTrue(truth['landed']); self.assertLess(abs(truth['f_m']), .02); self.assertLess(abs(truth['l_m']), .02)
        self.assertEqual([s['state'] for s in result['states']].count('retry'), self.g['procedure']['retries'])

    def test_tag_loss_during_descent_recovers(self):
        sim, error = kinematic_docking(4, self.g, CAMERA)
        phase = sim.phase()
        # Blank four frames once the descent starts: the controller must climb back and re-align, then dock.
        descend_seen = {'count': 0}
        def frames_with_loss():
            async def frames():
                jpeg, meta = await DockSimulation.frames(sim)
                if any(e['state'] == 'descend' for e in phase.log) and descend_seen['count'] < 4 and jpeg is not None:
                    descend_seen['count'] += 1
                    return None, {**meta, 'dropped': False}
                return jpeg, meta
            return frames
        phase.frames = frames_with_loss()
        result = run(phase.run())
        self.assertEqual(result['outcome'], 'docked', (result['states'], result.get('error')))
        self.assertGreaterEqual([s['state'] for s in result['states']].count('align'), 2)
        self.assertEqual(descend_seen['count'], 4)

    def test_stand_contact_is_detected_by_the_world(self):
        world = DockWorld(self.g, 0, (1.25, 1.25, 0.), 0.)
        self.assertFalse(world.stand_contact([1.25, 1.25, .1]))
        self.assertTrue(world.stand_contact([1.25 + .20, 1.25, .1]))
        self.assertFalse(world.stand_contact([1.25 + .20, 1.25, .5]))

    def test_dock_controller_faults_and_modes(self):
        world = DockWorld(self.g, 0, (1.25, 1.25, 0.), 0.)
        vehicle = KinematicDockVehicle(world, [1.25, 1.25, 0., 0.], Estimator())
        sim = DockSimulation(self.g, CAMERA, lambda w, e: vehicle, Estimator())
        sim.vehicle = vehicle
        status = sim.observe()
        self.assertFalse(status['contact']); self.assertEqual(status['mode'], 'off'); self.assertEqual(status['supply_v'], 0.)
        sim.controller.set_mode('charge'); status = sim.observe()
        self.assertTrue(status['contact']); self.assertEqual(status['pin_current_ma'], 450.)
        sim.controller.pad_temp_c = 50; status = sim.observe()
        self.assertEqual(status['fault'], 'pad overtemperature'); self.assertFalse(status['contact']); self.assertEqual(status['supply_v'], 0.)
        sim.controller.pad_temp_c = 22; sim.controller.set_mode('storage'); sim.controller.cell_v = 3.9; status = sim.observe()
        self.assertFalse(status['contact'])   # storage hold: cell above the low threshold, 5 V off
        sim.controller.cell_v = 3.7; status = sim.observe()
        self.assertTrue(status['contact'])


if __name__ == '__main__':
    unittest.main()
