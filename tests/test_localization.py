import json
import math
import unittest

from app.localization import available_actions, bearing, parse_visual, triangulate, validate_action


class LocalizationContracts(unittest.TestCase):
    def test_no_location_without_two_view_evidence(self):
        actions = available_actions(remaining=3, confirmation_available=True, location=None)
        self.assertEqual(set(actions), {'scan', 'confirm'})
        self.assertIsNotNone(validate_action('found', remaining=3, confirmation_available=True, location=None))

    def test_exhaustion_is_not_absence_proof(self):
        self.assertEqual(set(available_actions(remaining=0, confirmation_available=False, location=None)), {'unresolved'})

    def test_invalid_boxes_fail_closed(self):
        for box in ([0, 0, 1001, 10], [500, 500, 200, 600], [0, 0, float('nan'), 300], [True, 0, 20, 40]):
            with self.assertRaises(ValueError):
                parse_visual(json.dumps({'status': 'present', 'evidence': 'red cylinder', 'bbox': box}))
        with self.assertRaises(ValueError):
            parse_visual(json.dumps({'status': 'absent', 'evidence': 'not seen', 'bbox': [1, 2, 3, 4]}))

    def test_two_camera_rays_localize_without_scene_access(self):
        target = [4., 6.]
        a, b = [2., 2., 1.4, math.atan2(4, 2)], [3., 2., 1.4, math.atan2(4, 1)]
        result = triangulate({'pose': a, 'bbox': [480, 480, 520, 520], 'view_id': 'a'},
                             {'pose': b, 'bbox': [480, 480, 520, 520], 'view_id': 'b'})
        self.assertLess(math.dist(result['xy_m'], target), 1e-8)

    def test_duplicate_and_parallel_rays_cannot_verify_location(self):
        a = {'pose': [2, 2, 1.4, 0], 'bbox': [480, 480, 520, 520], 'view_id': 'a'}
        self.assertIsNone(triangulate(a, a))
        b = {**a, 'pose': [2, 3, 1.4, 0], 'view_id': 'b'}
        self.assertIsNone(triangulate(a, b))

    def test_pixel_to_bearing_matches_camera_handedness(self):
        a = bearing([2, 2, 1.4, math.pi/2], [700, 450, 800, 550])
        self.assertLess(a[0], 0)
        self.assertGreater(a[1], 0)


if __name__ == '__main__':
    unittest.main()
