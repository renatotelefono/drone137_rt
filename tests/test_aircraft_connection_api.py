import asyncio
from pathlib import Path
import unittest

import aiohttp
from aiohttp import web

from app.components import Components
from hardware.esp32.connection_api import install
from tests import test_aircraft_connection as connection_fixtures


class ConnectionAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await connection_fixtures.ConnectionTests.asyncSetUp(self)
        root = Path(self.folder.name)
        app = web.Application(client_max_size=4096)
        self.registry, self.connections = install(app, root/'api-aircraft.sqlite3', Components(root/'parts.sqlite3'))
        self.api = web.AppRunner(app, access_log=None)
        await self.api.setup()
        site = web.TCPSite(self.api, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.address = f'http://127.0.0.1:{port}'
        self.client = aiohttp.ClientSession(headers={'X-Drone137-Control': 'local'})

    async def asyncTearDown(self):
        await self.client.close()
        await self.api.cleanup()
        await connection_fixtures.ConnectionTests.asyncTearDown(self)

    async def post(self, path, body=None, **options):
        async with self.client.post(self.address+'/api/aircraft'+path,
                                    json={} if body is None else body, **options) as response:
            return response.status, await response.json()

    async def pair(self):
        status, record = await self.post('/pair', {'profile': self.profile, 'address': self.record['endpoint'],
                'name': 'Workshop Scout', 'assembly': 'scout-110-bench-b@1'})
        self.assertEqual(status, 200, record)
        self.assertNotIn('credential', record)
        return record['id']

    async def test_pair_connect_preview_disconnect_and_forget(self):
        identity = await self.pair()
        status, result = await self.post('/'+identity+'/connect')
        self.assertEqual(status, 200, result)
        self.assertTrue(result['camera_ready'])
        self.assertFalse(result['mission_ready'])
        async with self.client.get(self.address+'/api/aircraft/'+identity+'/frame') as response:
            self.assertEqual(response.status, 200)
            self.assertTrue((await response.read()).startswith(b'\xff\xd8'))
        async with self.client.get(self.address+'/api/aircraft') as response:
            self.assertNotIn(self.profile['credential'], await response.text())
        self.assertEqual((await self.post('/'+identity+'/forget'))[0], 409)
        self.assertEqual((await self.post('/'+identity+'/disconnect'))[0], 200)
        self.assertEqual((await self.post('/'+identity+'/forget'))[0], 200)
        self.assertEqual(self.registry.list(), [])

    async def test_wrong_certificate_never_creates_pairing(self):
        status, _ = await self.post('/pair', {'profile': dict(self.profile, certificate_sha256='0'*64),
                'address': self.record['endpoint'], 'name': 'Scout', 'assembly': 'scout-110-bench-b@1'})
        self.assertEqual(status, 503)
        self.assertEqual(self.registry.list(), [])

    async def test_cross_origin_and_missing_local_header_cannot_control(self):
        for headers in ({'Origin': 'https://untrusted.example'}, {'X-Drone137-Control': ''}):
            async with self.client.post(self.address+'/api/aircraft/pair', json={}, headers=headers) as response:
                self.assertEqual(response.status, 403)

    async def test_emergency_route_does_not_wait_for_delayed_camera(self):
        identity = await self.pair()
        await self.post('/'+identity+'/connect')
        connection = self.connections[identity]
        await connection.link.claim()
        await connection.link.command('arm')
        self.emulator.camera_delay = 1.
        capture = asyncio.create_task(connection.link.capture())
        try:
            status, result = await asyncio.wait_for(self.post('/'+identity+'/disarm'), .5)
            self.assertEqual(status, 200, result)
            self.assertEqual(result['state'], 'disarmed')
        finally:
            capture.cancel()
            await asyncio.gather(capture, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
