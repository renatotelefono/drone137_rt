import math
import unittest

import cv2
import numpy as np

from app.dock_tags import (TagDetector, TagRenderer, body_pose, body_rotation, extrinsics, load_geometry,
                           optics_from_scene_camera, tag_corners, tag_ids)

CAMERA = {'width': 960, 'height': 540, 'vertical_fov': 41, 'effects': {'distortion': -.025, 'blur': .6, 'noise': .018}}


class TagGeometry(unittest.TestCase):
    def setUp(self):
        self.g = load_geometry(); self.mount = self.g['aircraft']

    def test_tag_ids_and_corners_follow_the_dock_index(self):
        self.assertEqual(tag_ids(0), [0, 1, 2]); self.assertEqual(tag_ids(7), [21, 22, 23])
        corners = tag_corners(self.g, 2)
        self.assertEqual(sorted(corners), [6, 7, 8])
        low = corners[6]
        self.assertTrue((low[:, 0] == self.g['tag_plane_f_m']).all())
        self.assertAlmostEqual(low[:, 2].mean(), self.g['tags'][0]['height_m'])
        self.assertAlmostEqual(np.linalg.norm(low[0]-low[1]), self.g['tags'][0]['size_m'])

    def test_extrinsics_and_body_pose_are_inverse(self):
        for position, yaw, pitch, roll in [((-.4, .05, .3), .1, 0, 0), ((0, 0, .15), -.2, .05, -.03), ((-1, .3, .5), 2.9, 0, .1)]:
            R_db = body_rotation(yaw, pitch, roll)
            R_cd, t = extrinsics(position, R_db, self.mount)
            pose = body_pose(R_cd, t, self.mount)
            np.testing.assert_allclose(pose['position_m'], position, atol=1e-9)
            self.assertAlmostEqual(pose['yaw_rad'], yaw); self.assertAlmostEqual(pose['pitch_rad'], pitch); self.assertAlmostEqual(pose['roll_rad'], roll)

    def test_camera_optical_axis_points_forward_and_down(self):
        R_cd, t = extrinsics((0, 0, 0), body_rotation(0), {'camera_pitch_deg': -10, 'camera_offset_flu_m': [0, 0, 0]})
        axis = R_cd.T @ np.array([0, 0, 1.])
        self.assertGreater(axis[0], .98); self.assertLess(axis[2], -.17); self.assertAlmostEqual(axis[1], 0)


class RenderAndDetect(unittest.TestCase):
    def setUp(self):
        self.g = load_geometry(); self.mount = self.g['aircraft']
        self.optics = optics_from_scene_camera(CAMERA)
        self.renderer = TagRenderer(self.g, 0, self.optics, CAMERA['effects'], seed=1)
        self.detector = TagDetector(self.g, 0, self.optics)

    def pose_error(self, position, yaw):
        R_cd, t = extrinsics(position, body_rotation(yaw), self.mount)
        jpeg = self.renderer.render(R_cd, t, jpeg_quality=.72)
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        m = self.detector.measure(image, self.mount)
        self.assertIsNotNone(m['pose'], f'no pose at {position}')
        return np.linalg.norm(np.array(m['pose']['position_m'])-position), abs(m['pose']['yaw_rad']-yaw), m

    def test_pose_within_five_millimetres_near_the_dock(self):
        for position, yaw in [((0, 0, .15), 0), ((-.05, .02, .15), math.radians(-8)), ((0, 0, .04), 0), ((-.2, -.05, .25), math.radians(6))]:
            err, yaw_err, m = self.pose_error(position, yaw)
            self.assertLess(err, .005, (position, err)); self.assertLess(yaw_err, math.radians(1)); self.assertLess(m['reprojection_px'], 1)

    def test_pose_at_the_approach_point_within_two_centimetres(self):
        err, yaw_err, m = self.pose_error((-.45, .05, .3), math.radians(5))
        self.assertLess(err, .02); self.assertLess(yaw_err, math.radians(1)); self.assertIn(2, m['detected'])

    def test_no_pose_when_facing_away_or_without_tags(self):
        R_cd, t = extrinsics((-.45, 0, .3), body_rotation(math.pi), self.mount)
        image = cv2.imdecode(np.frombuffer(self.renderer.render(R_cd, t, jpeg_quality=.72), np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNone(self.detector.measure(image, self.mount)['pose'])
        blank = np.full((540, 960, 3), 90, np.uint8)
        self.assertEqual(self.detector.measure(blank, self.mount), {'detected': [], 'pose': None})

    def test_other_docks_tags_are_ignored(self):
        other = TagRenderer(self.g, 5, self.optics, CAMERA['effects'], seed=1)
        R_cd, t = extrinsics((0, 0, .15), body_rotation(0), self.mount)
        image = cv2.imdecode(np.frombuffer(other.render(R_cd, t, jpeg_quality=.9), np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNone(self.detector.measure(image, self.mount)['pose'])
        detected = TagDetector(self.g, 5, self.optics).measure(image, self.mount)['detected']
        self.assertTrue(detected and set(detected) <= {15, 16, 17}, detected)


if __name__ == '__main__':
    unittest.main()
