"""Staged workshop events: every perch is in free space and sees the whole object; the cart runs across open floor."""
import math
import unittest

from sim.asset_world import build
from sim.hard_flight import cases
from sim.watch_render import (AFTER, BEFORE, CLEARANCE_M, EVENTS, HEIGHTS, RATE, PerchedPose, cart_box, clear_spot, scenario_seed,
                              sees, staged)


def ids(scene):
    return {p['id'] for p in scene['obstacles']}


class StagedEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = build(cases()[0])

    def test_every_staged_event_is_in_clear_view_from_a_free_perch(self):
        for event in EVENTS:
            for seed in range(4):
                with self.subTest(event=event, seed=seed):
                    self.check(event, seed)

    def check(self, event, seed):
        scene = self.scene
        before, after, perch, yaw, cart_before, cart_after, truth = staged(scene, event, scenario_seed(event, seed), HEIGHTS[seed % 2])
        self.assertTrue(.5 <= perch[0] <= scene['width'] - .5 and .5 <= perch[1] <= scene['depth'] - .5)
        self.assertEqual(perch[2], HEIGHTS[seed % 2])
        self.assertEqual((truth['at'], truth['frames'], truth['fps']), (BEFORE/RATE, BEFORE + AFTER, RATE))
        self.assertTrue(2. <= truth['distance_m'] <= 4.)
        self.assertAlmostEqual(math.atan2(truth['object_xy'][1] - perch[1], truth['object_xy'][0] - perch[0]), yaw)
        present = scene['obstacles'] + [cart_box(scene)]
        self.assertTrue(clear_spot(perch[0], perch[1], perch[2], present, CLEARANCE_M))
        if event == 'cart':
            self.assertEqual((truth['kind'], truth['category']), ('motion', 'object_moved'))
            for x, y in ((cart_after[0], cart_after[1]), (cart_after[2], cart_after[3])):
                self.assertTrue(sees(perch, cart_box(scene, x, y), present))
            self.assertAlmostEqual(math.hypot(cart_after[2] - cart_after[0], cart_after[3] - cart_after[1]), 2.4)
            self.assertEqual((cart_before[0], cart_before[1]), (cart_after[0], cart_after[1]))   # parked at the start before it rolls
            return
        self.assertIsNone(cart_before); self.assertIsNone(cart_after)
        visible_in = before if event == 'object_removed' else after
        target = next(p for p in visible_in['obstacles'] if p['id'] == truth['object_id'])
        self.assertTrue(.3 <= target['height'] <= 1.3 and target.get('bottom', 0) < .1)
        self.assertTrue(sees(perch, target, visible_in['obstacles'] + [cart_box(scene)]))
        if event == 'object_removed':
            self.assertEqual(ids(before) - ids(after), {truth['object_id']})
        elif event == 'object_added':
            self.assertEqual(ids(after) - ids(before), {truth['object_id']})
            if target['id'] == 'staged-crate':
                self.assertIn(target['yaw'], (0., math.pi/2))   # the renderer's bounds check passes only axis-aligned models
        elif event == 'object_moved':
            self.assertEqual(ids(before), ids(after)); self.assertTrue(.6 <= truth['moved_by_m'] <= 1.)
            was = next(p for p in before['obstacles'] if p['id'] == truth['object_id'])
            self.assertAlmostEqual(math.hypot(target['x'] - was['x'], target['y'] - was['y']), truth['moved_by_m'])
            self.assertTrue(sees(perch, was, before['obstacles'] + [cart_box(scene)]))
        else:
            self.assertEqual((truth['kind'], ids(before)), ('lighting', ids(after)))
            self.assertAlmostEqual(after['illumination']['ambient'], scene['illumination']['ambient']*.3)
            self.assertAlmostEqual(after['real_assets']['environment_intensity'], scene['real_assets']['environment_intensity']*.3)

    def test_heights_alternate_and_events_get_their_own_perches(self):
        perches = set()
        for event in EVENTS:
            for seed in range(2):
                *_, truth = staged(self.scene, event, scenario_seed(event, seed), HEIGHTS[seed % 2])
                perches.add((round(truth['perch'][0], 2), round(truth['perch'][1], 2)))
                self.assertEqual(truth['perch_height_m'], HEIGHTS[seed % 2])
        self.assertEqual(len(perches), 2*len(EVENTS))

    def test_perched_pose_reports_a_fixed_camera_and_a_rolling_cart(self):
        pose = PerchedPose(self.scene, [3., 4., 1.05], math.pi/2, cart=(1., 1., 3., 1., 2.))
        pose.started -= 1.   # one second in
        snap = pose.snapshot()
        self.assertEqual((snap['truth']['position'], snap['phase'], snap['speed']), ([3., 4., 1.05], 'perched', 0.))
        for got, want in zip(snap['truth']['quaternion'], [0., 0., math.sin(math.pi/4), math.cos(math.pi/4)]):
            self.assertAlmostEqual(got, want)
        self.assertAlmostEqual(snap['truth']['cart_position'][0], 2., delta=.05); self.assertEqual(snap['truth']['cart_position'][1], 1.)


if __name__ == '__main__':
    unittest.main()
