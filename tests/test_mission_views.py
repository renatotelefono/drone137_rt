import math
import unittest
from app.mission_views import next_views, visible_ray
from app.mission_navigation import clearance


class ViewAcquisition(unittest.TestCase):
    def geometry(self):
        return {'width': 12, 'depth': 10, 'obstacles': [], 'fixtures': [],
                'moving_actor': {'center': [10, 9], 'size': [.3, .3, 1], 'amplitude_m': .1}}

    def test_near_candidate_occluder_is_not_discarded(self):
        g = self.geometry()
        g['obstacles'] = [{'x': 5, 'y': 5, 'sx': .3, 'sy': .3, 'height': .7},
                          {'x': 5, 'y': 4.5, 'sx': 1, 'sy': .2, 'height': .8}]
        self.assertFalse(visible_ray(g, [5, 2, 1], [5, 5, .4]))
        self.assertTrue(visible_ray(g, [3, 5, 1], [5, 5, .4]))

    def test_safe_bounded_parallax_stations(self):
        g = self.geometry()
        reference = {'origin': [4, 2, 1.5], 'ray': [0, 1, 0], 'view_id': 'first'}
        position = [5, 2, 1.5]
        plans = next_views(g, position, {'xyz_m': [5, 5, .4]}, reference)
        self.assertTrue(plans)
        for plan in plans:
            p = plan['pose']
            self.assertGreaterEqual(clearance(g, p), .58)
            self.assertLessEqual(abs(position[2]-p[2]), .300001)
            self.assertLessEqual(math.dist(position[:2], p[:2]), 3.5)
            self.assertGreaterEqual(math.dist(p[:2], [5, 5]), 1.4)
            self.assertTrue(plan['path'])

    def test_observed_hover_overshoot_cannot_escape_command_limits(self):
        plans=next_views(self.geometry(),[5,2,1.8000061511993408],
                         {'xyz_m':[5,5,1.4]},
                         {'origin':[4,2,1.8],'ray':[0,1,0],'view_id':'first'})
        self.assertTrue(plans)
        self.assertTrue(all(.9<=p['pose'][2]<=1.8 for p in plans))
        self.assertTrue(all(0<=xyz[2]<=1.8 for p in plans for xyz in p['path']))
