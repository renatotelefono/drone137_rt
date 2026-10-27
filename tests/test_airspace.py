"""Shared airspace rules: separation on reported positions, right of way by number, holds on link loss, corridors, keep-out boxes."""
import asyncio
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.airspace import Airspace, number, segment_distance
from app.airspace_api import install
from app.mission_navigation import flight_path


def room():
    return {'width': 12., 'depth': 10., 'obstacles': [], 'fixtures': [], 'moving_actor': {'center': [11., 9.], 'amplitude_m': 0., 'size': [.1, .1, .1]}}


class Rules(unittest.TestCase):
    def test_right_of_way_is_the_lower_number(self):
        self.assertLess(number('scout-01'), number('scout-02')); self.assertLess(number('drone-2'), number('drone-10'))
        self.assertLess(number('scout-07'), number('alpha')); self.assertLess(number('alpha'), number('beta'))

    def test_segment_distance(self):
        self.assertAlmostEqual(segment_distance((0, 1), (-1, 0), (1, 0)), 1.); self.assertAlmostEqual(segment_distance((3, 0), (-1, 0), (1, 0)), 2.)

    def test_alone_proceeds_and_separation_is_none(self):
        a = Airspace(); a.report('scout-01', (2, 2, 1.5), 0., t=10.)
        self.assertEqual(a.advice('scout-01', (8, 2, 1.5), now=10.)['action'], 'proceed'); self.assertIsNone(a.separation('scout-01'))

    def test_the_lower_number_proceeds_and_the_other_holds_near_its_leg(self):
        a = Airspace(); a.report('scout-01', (5, 5, 1.5), 0., 10.); a.report('scout-02', (5, 8, 1.5), 0., 10.)
        self.assertEqual(a.advice('scout-01', (5, 2, 1.5), 10.)['action'], 'proceed')          # 02 is 3 m away, off the leg
        hold = a.advice('scout-02', (5, 2, 1.5), 10.)                                         # 01 sits on 02's leg
        self.assertEqual(hold['action'], 'hold'); self.assertEqual(hold['other'], 'scout-01'); self.assertIn('right of way', hold['reason'])
        self.assertEqual(a.advice('scout-02', (9, 9, 1.5), 10.)['action'], 'proceed')          # a leg away from 01
        self.assertAlmostEqual(a.separation('scout-02'), 3.)

    def test_within_separation_the_lower_number_still_proceeds_and_the_other_holds(self):
        a = Airspace(); a.report('scout-01', (5, 5, 1.5), 0., 10.); a.report('scout-02', (6, 5, 1.5), 0., 10.)
        self.assertEqual(a.advice('scout-02', (6, 8, 1.5), 10.)['action'], 'hold')
        self.assertEqual(a.advice('scout-01', (2, 5, 1.5), 10.)['action'], 'proceed')
        self.assertTrue(a.status(10.)['flights'][1]['holding'])

    def test_different_heights_do_not_conflict(self):
        a = Airspace(); a.report('scout-01', (5, 5, .5), 0., 10.); a.report('scout-02', (5.5, 5, 1.5), 0., 10.)
        self.assertEqual(a.advice('scout-02', (5, 2, 1.5), 10.)['action'], 'proceed'); self.assertIsNone(a.separation('scout-02'))

    def test_a_lost_link_holds_everyone_until_the_reports_return(self):
        a = Airspace(); a.report('scout-01', (2, 2, 1.5), 0., 10.); a.report('scout-02', (8, 8, 1.5), 0., 10.); a.report('scout-03', (2, 8, 1.5), 0., 10.)
        for k in ('scout-01', 'scout-02'):
            a.report(k, a.flights[k]['position'], 0., 11.5)
        self.assertEqual(a.lost(11.5), ['scout-03'])
        self.assertEqual(a.advice('scout-01', (8, 2, 1.5), 11.5), {'action': 'hold', 'reason': 'link lost on scout-03', 'other': 'scout-03'})
        self.assertEqual(a.advice('scout-02', (2, 8, 1.5), 11.5)['action'], 'hold')
        a.report('scout-03', (2, 8, 1.5), 0., 11.6)
        self.assertEqual(a.advice('scout-01', (8, 2, 1.5), 11.6)['action'], 'proceed')
        a.landed('scout-03', 12.)
        for k in ('scout-01', 'scout-02'):
            a.report(k, a.flights[k]['position'], 0., 20.)
        self.assertEqual(a.lost(20.), []); self.assertEqual(a.status(20.)['in_the_air'], 2)   # a landed flight is never lost
        self.assertEqual([e['text'] for e in a.events][-1], 'landed')

    def test_corridors_refuse_goals_outside(self):
        a = Airspace(); a.assign('scout-01', {'x0': 0, 'y0': 0, 'x1': 6, 'y1': 10}); a.report('scout-01', (2, 2, 1.5), 0., 10.)
        self.assertEqual(a.advice('scout-01', (8, 2, 1.5), 10.)['action'], 'refuse'); self.assertEqual(a.advice('scout-01', (5, 2, 1.5), 10.)['action'], 'proceed')
        with self.assertRaises(ValueError):
            a.assign('scout-01', {'x0': 6, 'y0': 0, 'x1': 2, 'y1': 10})

    def test_the_planner_routes_round_the_other_aircraft_at_the_separation(self):
        a = Airspace(); a.report('scout-01', (6, 5, 1.5), 0., 10.); a.report('scout-02', (2, 5, 1.5), 0., 10.)
        boxes = a.keep_out('scout-02')
        self.assertEqual(len(boxes), 1); self.assertEqual(boxes[0]['keep_out_for'], 'scout-01'); self.assertAlmostEqual(boxes[0]['sx'], 2*(1.8 - .58))
        path = flight_path(a.map_for('scout-02', room()), (2, 5, 1.5), (10, 5, 1.5))
        self.assertGreaterEqual(min(segment_distance((6, 5), p, q) for p, q in zip([(2, 5, 1.5), *path], path)), 1.5 - 1e-6)
        self.assertEqual(path[-1][:2], [10, 5])


class GiveWay(unittest.TestCase):
    def test_a_blocked_priority_flight_makes_the_holder_back_off_and_the_request_lapses(self):
        a = Airspace(); a.report('scout-01', (5, 5, 1.5), 0., 10.); a.report('scout-02', (6.2, 5, 1.5), 0., 10.)
        a.blocked('scout-01', 'scout-02', 10.)
        advice = a.advice('scout-02', (9, 5, 1.5), 10.)
        self.assertEqual(advice['action'], 'give_way'); self.assertEqual(advice['away_from'], [5., 5., 1.5]); self.assertEqual(advice['other'], 'scout-01')
        a.blocked('scout-02', 'scout-01', 10.)   # the lower number is never asked to give way
        self.assertIsNone(a.flights['scout-01']['give_way'])
        a.report('scout-02', (6.9, 5, 1.5), 0., 10.1)
        self.assertEqual(a.advice('scout-02', (9, 5, 1.5), 10.1)['action'], 'give_way')   # not yet 1.5 m away from where it was asked
        a.report('scout-02', (7.7, 5, 1.5), 0., 10.2)
        self.assertEqual(a.advice('scout-02', (9, 5, 1.5), 10.2)['action'], 'proceed')    # backed off 1.5 m, and 01 is now clear of its leg
        self.assertIsNone(a.flights['scout-02']['give_way'])
        a.report('scout-01', (5, 5, 1.5), 0., 16.); a.report('scout-02', (6.2, 5, 1.5), 0., 16.)
        a.flights['scout-02']['give_way'] = {'from': [5., 5., 1.5], 'for': 'scout-01', 't': 10., 'at': [6.2, 5., 1.5]}
        a.advice('scout-02', (9, 9, 1.5), 16.)
        self.assertIsNone(a.flights['scout-02']['give_way'])                               # lapsed after GIVE_WAY_S


class FakeRuntime:
    def __init__(self):
        self.busy = True; self.pose = {'x': 2., 'y': 3., 'z': 1.5, 'yaw': .1}

    def current_pose(self):
        return self.pose


class Api(unittest.IsolatedAsyncioTestCase):
    async def test_status_shows_the_runtime_flight_and_its_landing(self):
        runtime = FakeRuntime(); app = web.Application()
        airspace = install(app, runtime, period_s=.02)
        client = TestClient(TestServer(app)); await client.start_server()
        try:
            await asyncio.sleep(.1)
            body = await (await client.get('/api/airspace')).json()
            self.assertEqual(body['in_the_air'], 1); self.assertEqual(body['flights'][0]['aircraft'], 'mission-aircraft')
            self.assertEqual(body['flights'][0]['position'], [2., 3., 1.5]); self.assertFalse(body['flights'][0]['lost'])
            self.assertEqual(body['rules']['right_of_way'], 'lower aircraft number')
            runtime.busy = False
            await asyncio.sleep(.1)
            body = await (await client.get('/api/airspace')).json()
            self.assertEqual(body['in_the_air'], 0); self.assertEqual(body['flights'][0]['state'], 'landed')
        finally:
            await client.close()


if __name__ == '__main__':
    unittest.main()
