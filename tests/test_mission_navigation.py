import unittest
from app.mission_navigation import clearance, segment_clear, flight_path
from sim.flight_world import _RouteGeometry


class HeightAwareFlight(unittest.TestCase):
    def scene(self, height=.5):
        return {'width':6,'depth':6,'obstacles':[dict(x=3,y=3,sx=5,sy=.5,height=height)],
                'fixtures':[], 'moving_actor':{'center':[5.8,5.8],'size':[.1,.1,1],'amplitude_m':0}}

    def test_flies_over_low_box_with_unchanged_clearance(self):
        scene=self.scene();start,end=[2,1,1.2],[2,5,1.2]
        path=flight_path(scene,start,end)
        self.assertGreaterEqual(max(p[2] for p in path),1.5)
        self.assertTrue(all(segment_clear(scene,a,b,.58) for a,b in zip([start,*path],path)))
        self.assertFalse(segment_clear(scene,[2,1,.9],[2,5,.9],.58))

    def test_full_height_wall_cannot_be_overflown(self):
        with self.assertRaisesRegex(ValueError,'No route'):
            flight_path(self.scene(3),[2,1,1.2],[2,5,1.2])

    def test_measured_altitude_overshoot_never_becomes_a_command(self):
        scene=self.scene();start=[2,1,1.8000061511993408]
        path=flight_path(scene,start,[2,5,1.8])
        self.assertTrue(all(0<=p[2]<=1.8 for p in path))
        self.assertTrue(all(segment_clear(scene,a,b,.58) for a,b in zip([start,*path],path)))
        with self.assertRaisesRegex(ValueError,'command altitude'):
            flight_path(scene,start,[2,5,1.8000061511993408])

    def test_overhead_shelf_blocks_vertical_ascent(self):
        scene=self.scene();scene['obstacles']=[]
        scene['fixtures']=[dict(x=2,y=2,sx=1,sy=1,bottom=1.7,height=.1)]
        self.assertGreaterEqual(clearance(scene,[2,2,.9]),.58)
        self.assertFalse(segment_clear(scene,[2,2,.9],[2,2,1.5]))

    def test_height_slice_and_monitor_share_distance_threshold(self):
        scene=self.scene()
        for altitude in (.9,1.2,1.5,1.8):
            geometry=_RouteGeometry(scene,altitude)
            for x,y in ((2,2.7),(2,3),(2,3.4),(.5,2),(.7,2)):
                self.assertEqual(geometry.point_clear([x,y],.58),clearance(scene,[x,y,altitude])>=.58)
