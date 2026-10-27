"""Three aircraft on the shared airspace, first-order plants: separation kept, every goal reached, a lost link holds the others."""
import asyncio
import unittest

from sim.asset_world import build
from sim.hard_flight import cases
from sim.swarm_world import AIRCRAFT, BLACKOUT_S, check_scene, run_swarm, scenario


class Swarm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = build(cases()[0]); check_scene(cls.scene)

    def test_scenario_draws_a_blackout_and_delays(self):
        plan = scenario(3)
        self.assertIn(plan['blackout']['aircraft'], AIRCRAFT); self.assertTrue(8. <= plan['blackout']['t0'] <= 20.)
        self.assertEqual(set(plan['legs']), set(AIRCRAFT)); self.assertTrue(all(0. <= d <= 3. for d in plan['delays'].values()))

    def test_three_aircraft_cross_keep_apart_reach_their_goals_and_hold_on_a_lost_link(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                r = asyncio.run(run_swarm(seed, self.scene, vehicle='kinematic'))
                self.assertGreaterEqual(r['min_separation_m'], 1.2, (seed, r['min_separation_pair'], r['min_separation_t']))
                for k, f in r['flights'].items():
                    self.assertIsNone(f['error'], (seed, k, f)); self.assertTrue(f['finished']); self.assertEqual(f['goals_reached'], f['goals'])
                    self.assertLess(f['home_error_m'], .3); self.assertEqual(f['envelope_violations'], 0)
                self.assertIsNotNone(r['blackout']['reaction_s'], (seed, r['blackout'])); self.assertLessEqual(r['blackout']['reaction_s'], 2.5)
                self.assertLess(r['duration_s'], 180.); self.assertGreater(r['holds_total'], 0)


if __name__ == '__main__':
    unittest.main()
