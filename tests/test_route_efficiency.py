import copy
import math
import random
import unittest
from sim.flight_world import _RouteGeometry, clear, segment_clear, route, HOME
from sim.asset_world import build
from sim.hard_flight import cases


class RouteEquivalence(unittest.TestCase):
    def test_endpoint_can_connect_when_rounded_grid_cell_is_blocked(self):
        world={'width':6,'depth':6,'obstacles':[dict(x=2.58,y=2,sx=.2,sy=2,height=3)],
               'moving_actor':{'center':[5.8,5.8],'size':[.1,.1,1],'amplitude_m':0}}
        start,end=[1.89,2.12],[4.5,2.12]
        self.assertGreaterEqual(clear(world,start),.58)
        self.assertFalse(segment_clear(world,start,[2,2]))
        for a,b in ((start,end),(end,start)):
            points=route(world,a,b)
            self.assertEqual(points[-1],b)
            self.assertTrue(all(segment_clear(world,p,q) for p,q in zip([a,*points],points)))

    def test_threshold_matches_original_distance_at_edges_and_random_points(self):
        rng=random.Random(719)
        for case in cases()[::2]:
            world=build(case);geometry=_RouteGeometry(world)
            for margin in (0., .35, .58, .65):
                points=[[rng.uniform(-.2,12.2),rng.uniform(-.2,10.2)] for _ in range(100)]
                for b in world['obstacles']:
                    edge=b['x']+b['sx']/2+margin
                    points.extend([[x,b['y']] for x in (math.nextafter(edge,-math.inf),edge,math.nextafter(edge,math.inf))])
                for point in points:
                    self.assertEqual(geometry.point_clear(point,margin),clear(world,point)>=margin,(case['id'],point,margin))

    def test_segment_keeps_original_sample_positions(self):
        world=build(cases()[0]);rng=random.Random(721)
        for _ in range(80):
            start=[rng.uniform(0,12),rng.uniform(0,10)];end=[rng.uniform(0,12),rng.uniform(0,10)]
            n=max(1,math.ceil(math.dist(start,end)/.06))
            expected=all(clear(world,[start[0]+(end[0]-start[0])*i/n,start[1]+(end[1]-start[1])*i/n])>=.58 for i in range(n+1))
            self.assertEqual(segment_clear(world,start,end),expected)

    def test_new_plan_does_not_reuse_stale_geometry(self):
        world=build(cases()[0]);destination=[2.5,4.8]
        self.assertTrue(route(world,HOME,destination))
        changed=copy.deepcopy(world)
        changed['obstacles'].append(dict(x=2.5,y=4.8,sx=1.,sy=1.))
        with self.assertRaisesRegex(ValueError,'clearance'):
            route(changed,HOME,destination)
        self.assertTrue(route(world,HOME,destination))
