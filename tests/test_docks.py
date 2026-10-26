import asyncio
from pathlib import Path
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.dock_api import install
from app.docks import Docks, check_status, public, validate
from app.server import local_only

POSE = {'x': 1.25, 'y': 1.25, 'z': 0., 'yaw': 0.}


class Registry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.docks = Docks(Path(self.temp.name)/'docks.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def test_validation_fills_geometry_and_rejects_bad_records(self):
        record = validate({'id': 'hall-dock', 'name': 'Hall', 'pose': POSE, 'index': 2})
        self.assertEqual(record['tag_ids'], [6, 7, 8]); self.assertEqual(record['geometry'], 'dock-a@1')
        self.assertEqual(record['charge_policy']['full_v'], 4.2); self.assertIsNone(record['link'])
        for bad in [{'id': 'Hall', 'name': 'x', 'pose': POSE}, {'id': 'hall', 'name': 'x', 'pose': {'x': 1, 'y': 2}},
                    {'id': 'hall', 'name': 'x', 'pose': POSE, 'index': 999}, {'id': 'hall', 'name': 'x', 'pose': POSE, 'charge_policy': {'full_v': 4.35}},
                    {'id': 'hall', 'name': 'x', 'pose': POSE, 'link': {'endpoint': 'http://10.0.0.5:8443', 'fingerprint': 'a'*64, 'credential': 'c'*20}},
                    {'id': 'hall', 'name': 'x', 'pose': POSE, 'extra': 1}]:
            with self.assertRaises(ValueError, msg=bad):
                validate(bad)

    def test_revisions_registration_and_landings(self):
        first = self.docks.save({'id': 'hall-dock', 'name': 'Hall', 'pose': POSE, 'index': 1})
        self.assertEqual(first['revision'], 1)
        with self.assertRaises(ValueError):
            self.docks.save({'id': 'hall-dock', 'name': 'Hall', 'pose': POSE}, expected_revision=0)
        second = self.docks.register('hall-dock', 'Hall', {'x': 2, 'y': 3, 'z': 0, 'yaw': .5})
        self.assertEqual(second['revision'], 2); self.assertEqual(second['dock']['index'], 1); self.assertEqual(second['dock']['pose']['yaw'], .5)
        self.assertEqual(self.docks.get('hall-dock', 1)['dock']['pose'], {'x': 1.25, 'y': 1.25, 'z': 0., 'yaw': 0.})
        self.docks.record_landing('hall-dock', 2, 'docked', {'touchdown_mm': 7})
        self.assertEqual(self.docks.landings('hall-dock')[0]['detail'], {'touchdown_mm': 7})
        self.assertEqual([e['dock']['id'] for e in self.docks.list()], ['hall-dock'])

    def test_credentials_never_leave_in_listings(self):
        link = {'endpoint': 'https://10.0.0.5:8443', 'fingerprint': 'a'*64, 'credential': 'secret-credential-x'}
        entry = self.docks.save({'id': 'hall-dock', 'name': 'Hall', 'pose': POSE, 'link': link})
        self.assertEqual(entry['dock']['link']['credential'], 'secret-credential-x')
        self.assertNotIn('credential', public(entry['dock'])['link'])
        self.assertEqual(public(entry['dock'])['link']['fingerprint'], 'a'*64)

    def test_status_shape_is_checked(self):
        good = {'mode': 'charge', 'supply_v': 5., 'pin_current_ma': 150, 'pad_temp_c': 24, 'contact': True, 'fault': None, 'uptime_s': 3}
        self.assertEqual(check_status(good), good)
        for bad in [{**good, 'mode': 'boost'}, {**good, 'contact': 'yes'}, {**good, 'fault': 3}, {'mode': 'off'}, 'text']:
            with self.assertRaises(RuntimeError):
                check_status(bad)


class FakeClient:
    def __init__(self):
        self.mode = 'off'

    async def status(self):
        return {'mode': self.mode, 'supply_v': 5. if self.mode != 'off' else 0., 'pin_current_ma': 0, 'pad_temp_c': 23, 'contact': False, 'fault': None, 'uptime_s': 1}

    async def set_mode(self, mode):
        self.mode = mode
        return await self.status()


class FakeRuntime:
    async def stop(self, return_home=False, dock=False):
        return {'docking': dock}


class Api(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.docks = Docks(Path(self.temp.name)/'docks.sqlite3')
        app = web.Application(middlewares=[local_only])
        self.clients = install(app, self.docks, runtime=FakeRuntime(), current_pose=lambda: {'x': 3., 'y': 4., 'z': 0., 'yaw': 1.})
        self.client = TestClient(TestServer(app)); await self.client.start_server()
        self.headers = {'X-Drone137-Control': 'local'}

    async def asyncTearDown(self):
        await self.client.close(); self.temp.cleanup()

    async def test_register_from_aircraft_pose_status_and_mode(self):
        r = await self.client.post('/api/docks/register', json={'id': 'hall-dock', 'name': 'Hall', 'index': 3}, headers=self.headers)
        self.assertEqual(r.status, 200); body = await r.json()
        self.assertEqual(body['dock']['pose'], {'x': 3., 'y': 4., 'z': 0., 'yaw': 1.}); self.assertEqual(body['dock']['tag_ids'], [9, 10, 11])
        self.assertEqual((await (await self.client.get('/api/docks')).json())[0]['dock']['id'], 'hall-dock')
        r = await self.client.get('/api/docks/hall-dock/status')
        self.assertEqual(r.status, 404)
        self.clients['hall-dock'] = FakeClient()
        r = await self.client.get('/api/docks/hall-dock/status'); body = await r.json()
        self.assertEqual(body['status']['mode'], 'off'); self.assertEqual(body['landings'], [])
        r = await self.client.post('/api/docks/hall-dock/mode', json={'mode': 'charge'}, headers=self.headers)
        self.assertEqual((await r.json())['status']['mode'], 'charge')
        r = await self.client.post('/api/docks/hall-dock/mode', json={'mode': 'boost'}, headers=self.headers)
        self.assertEqual(r.status, 409)
        r = await self.client.post('/api/mission/dock', json={}, headers=self.headers)
        self.assertEqual(await r.json(), {'docking': True})

    async def test_post_requires_the_local_header(self):
        r = await self.client.post('/api/docks/register', json={'id': 'hall-dock', 'name': 'Hall'})
        self.assertEqual(r.status, 403)


if __name__ == '__main__':
    unittest.main()
