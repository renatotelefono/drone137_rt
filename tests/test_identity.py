import io
import json
import unittest
import math
try:
    from PIL import Image
except ImportError:
    Image = None
from app.identity import crop_candidate, guarded_actions, guarded_state, parse, supported, needs_detail, reinspection_needed
from app.flight_localization import detail_view, planned_parallax, active_detail_views, retained_observation
from sim.flight_world import inspection_sightline_clear, scene


class IdentityContracts(unittest.TestCase):
    def test_small_uncut_candidate_gets_elevated_views_not_a_descent_behind_box(self):
        p=[3.65,5.75,1.5];location={'xyz_m':[4.8,8.5,.6]}
        poses=active_detail_views(p,location,elevated=True)
        self.assertTrue(poses)
        self.assertAlmostEqual(poses[0][2],1.65)
        for pose in poses:
            self.assertGreaterEqual(pose[2],p[2]-.02)
            self.assertLess(math.dist(pose[:2],p[:2]),1)
        # No manufactured view outside an upward-looking camera's field of view.
        camera={'pitch_degrees':30,'height':540,'cy':270,'fy':720}
        self.assertEqual(active_detail_views(p,location,camera,elevated=True),[])

    def test_two_uncertain_small_views_can_request_detail_without_authorizing_found(self):
        detail={'crop':{'source_box_pixels':[54,40]}};bbox=[784,725,840,800];location={'xy_m':[4.8,8.7]}
        self.assertTrue(reinspection_needed(1,location,False,False,detail,bbox))
        self.assertFalse(reinspection_needed(4,location,False,False,detail,bbox))
        self.assertFalse(reinspection_needed(1,None,False,False,detail,bbox))
        self.assertFalse(reinspection_needed(1,location,True,True,detail,bbox))
        self.assertNotIn('found',guarded_actions(remaining=2,confirmation_available=True,
                         location=location,first_supported=False,current_supported=False))

    def test_reinspection_preserves_bounds_and_centres_low_objects(self):
        position=[3,4,1.5];location={'xyz_m':[3,7,.6]}
        poses=active_detail_views(position,location)
        self.assertTrue(poses)
        for pose in poses:
            self.assertLess(math.dist(position[:2],pose[:2]),1)
            self.assertLessEqual(abs(position[2]-pose[2]),.300001)
            self.assertGreaterEqual(math.dist(pose[:2],location['xyz_m'][:2]),1.4)
            self.assertGreaterEqual(pose[2],.9)
            self.assertLessEqual(pose[2],1.8)
            self.assertAlmostEqual(pose[3],math.atan2(7-pose[1],3-pose[0]))
        self.assertLess(poses[0][2],position[2])
        self.assertLess(math.dist(poses[0][:2],location['xyz_m'][:2]),3)
        self.assertEqual(active_detail_views(position,{'xyz_m':[3,4.5,.6]}),[])
        with self.assertRaises(ValueError):active_detail_views(position,{'xyz_m':[3,float('nan'),.6]})

    def test_reinspection_uses_the_reference_that_next_capture_will_keep(self):
        first={'view_id':'first'};current={'view_id':'second'}
        self.assertIs(retained_observation(first,True,current,False),first)
        self.assertIs(retained_observation(first,False,current,True),current)
        self.assertIs(retained_observation(first,False,current,False),current)

    def test_small_or_clipped_pixels_request_evidence_but_never_pass_identity(self):
        small={'crop':{'source_box_pixels':[57.6,43.2]}}
        self.assertTrue(needs_detail(small,[825,708,885,788]))
        large={'crop':{'source_box_pixels':[80,130]}}
        self.assertFalse(needs_detail(large,[300,300,450,700]))
        self.assertTrue(needs_detail(large,[300,700,450,999]))
        self.assertFalse(needs_detail(None,None))
        self.assertNotIn('found',guarded_actions(remaining=1,confirmation_available=True,
                         location={'xy_m':[4,8]},first_supported=False,current_supported=False))

    def test_extra_view_does_not_return_to_retained_first_view(self):
        # Regression: the third camera returned 18 cm from the retained first
        # camera, so two positive identity checks could not localize the target.
        reference={'origin':[4.29,5.90,1.52],'ray':[.175,.939,-.296]}
        position=[3.58,5.78,1.50];location={'xyz_m':[4.78,8.43,.62]}
        self.assertIsNone(planned_parallax(reference,detail_view(position,location,-1),location))
        self.assertIsNotNone(planned_parallax(reference,detail_view(position,location,1),location))

    def test_detail_view_retains_parallax_and_bounds_without_truth(self):
        position=[3,4,1.5];location={'xyz_m':[3,7,.7]}
        a=detail_view(position,location);b=detail_view(position,location,-1)
        self.assertLessEqual(math.dist(a[:2],position[:2]),.72)
        self.assertGreaterEqual(abs(a[0]-position[0]),.45)
        self.assertAlmostEqual(a[2],1.65)
        self.assertAlmostEqual(a[0]-position[0],-(b[0]-position[0]))
        self.assertIsNone(detail_view(position,{'xyz_m':[3,4.5,.7]}))
        self.assertEqual(detail_view(position,{'xyz_m':[3,7,-3]})[2],.9)
        with self.assertRaises(ValueError):detail_view(position,{'xyz_m':[3,float('nan'),.7]})

    def test_extra_view_rejects_shelf_occlusion_without_object_labels(self):
        world=scene();target=[4.4,8.9,.6]
        self.assertFalse(inspection_sightline_clear(world,[3.0,6.3,1.5],target))
        self.assertTrue(inspection_sightline_clear(world,[4.3,6.1,1.5],target))
        # Semantic object names cannot leak target identity into view planning.
        for obj in world['obstacles']:obj['kind']='unknown';obj['id']='anonymous'
        self.assertTrue(inspection_sightline_clear(world,[4.3,6.1,1.5],target))

    def test_ray_intersection_alone_never_enables_found(self):
        for first, current in ((False, False), (True, False), (False, True)):
            actions = guarded_actions(remaining=2, confirmation_available=False,
                                      location={'xy_m': [4, 8]}, first_supported=first, current_supported=current)
            self.assertNotIn('found', actions)
            self.assertIn('scan', actions)
        self.assertNotIn('found', guarded_actions(remaining=0, confirmation_available=False,
                          location=None, first_supported=True, current_supported=True))
        self.assertEqual({'found'}, set(guarded_actions(remaining=2, confirmation_available=True,
                       location={'xy_m': [4, 8]}, first_supported=True, current_supported=True)))

    def test_unknown_or_lid_fails_closed_even_with_a_hose(self):
        parts = {'body': 'cylinder', 'side': 'attached curved tube', 'top': 'projecting bar', 'evidence': 'Visible parts'}
        self.assertTrue(supported(parse(json.dumps(parts))))
        for key in ('body', 'side', 'top'):
            self.assertFalse(supported({**parts, key: 'unknown'}))
        self.assertFalse(supported({**parts, 'top': 'flat round lid'}))
        for value in ({**parts, 'label': 'extinguisher'}, {**parts, 'top': 'handle'}, {**parts, 'evidence': True}):
            with self.assertRaises(ValueError):
                parse(json.dumps(value))

    @unittest.skipUnless(Image, 'Install requirements-flight.txt for camera crop tests')
    def test_crop_uses_only_predicted_pixels_and_preserves_resolution(self):
        image = Image.new('RGB', (960, 540), '#999999')
        buf = io.BytesIO(); image.save(buf, format='JPEG')
        crop, meta = crop_candidate(buf.getvalue(), [0, 0, 100, 200])
        self.assertEqual(meta['bounds_pixels'], [0, 0, 120, 125])
        self.assertEqual(Image.open(io.BytesIO(crop)).size, (120, 125))
        self.assertFalse(meta['upscaled'])
        self.assertTrue(meta['adequate_pixels'])
        _, tiny = crop_candidate(buf.getvalue(), [100, 100, 110, 120])
        self.assertFalse(tiny['adequate_pixels'])
        for bbox in ([0, 0, 0, 100], [0, 0, 1001, 200], [0, True, 100, 200], [0, 0, float('nan'), 200]):
            with self.assertRaises(ValueError):
                crop_candidate(buf.getvalue(), bbox)

    def test_exhaustion_stays_unresolved_and_geometry_is_not_identity(self):
        actions = guarded_actions(remaining=0, confirmation_available=False,
                                  location={'xy_m': [4, 8]}, first_supported=False, current_supported=False)
        self.assertEqual(set(actions), {'unresolved'})
        state = guarded_state({'status': 'present', 'evidence': 'claimed hose', 'bbox': [1, 1, 20, 80]},
                              None, 0, False, {'xy_m': [4, 8]}, False)
        self.assertIn('Candidate rays intersect: True', state)
        self.assertIn('Required visual checks supported in both views: False', state)


if __name__ == '__main__':
    unittest.main()
