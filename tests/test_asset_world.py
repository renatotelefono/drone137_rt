import unittest
from sim.asset_world import build, verify_assets
from sim.hard_flight import cases
from sim.flight_world import HOME, VIEWS, route, segment_clear


class AssetWorld(unittest.TestCase):
    def test_assets_have_verified_bytes_and_physical_dimensions(self):
        manifest = verify_assets()
        self.assertEqual(len(manifest['assets']), 5)
        self.assertLess(sum(f['bytes'] for f in manifest['files'].values()), 12*1024**2)
        target = manifest['assets']['korean_fire_extinguisher_01']
        self.assertAlmostEqual(target['size_xyz_m'][1], .65925, places=4)
        shelf = manifest['assets']['steel_frame_shelves_01']
        self.assertAlmostEqual(shelf['unit_scale_to_m'], .1, places=5)

    def test_twin_rooms_share_collision_geometry_and_only_one_has_target(self):
        for positive, negative in zip(cases()[::2], cases()[1::2]):
            a, b = build(positive), build(negative)
            self.assertEqual(len(a['obstacles']), len(b['obstacles']))
            imported = [p for p in a['obstacles'] if p.get('asset') == 'korean_fire_extinguisher_01']
            self.assertEqual(len(imported), 1)
            self.assertFalse(any(p.get('asset') == 'korean_fire_extinguisher_01' for p in b['obstacles']))
            for pa, pb in zip(a['obstacles'], b['obstacles']):
                for k in ('id', 'x', 'y', 'bottom', 'sx', 'sy', 'height'):
                    self.assertEqual(pa[k], pb[k])
            self.assertNotIn('views', positive)

    def test_all_routes_clear_imported_asset_bounds(self):
        for case in cases()[::2]:
            world = build(case); previous = HOME
            for destination in VIEWS+[HOME]:
                for point in route(world, previous, destination):
                    self.assertTrue(segment_clear(world, previous, point), case['id'])
                    previous = point
