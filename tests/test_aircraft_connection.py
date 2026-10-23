import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from aiohttp import web

from hardware.esp32.connection import AircraftConnection
from hardware.esp32.device_store import DeviceStore
from hardware.esp32.link_emulator import AircraftEmulator, provision, tls_context
from hardware.esp32.link_protocol import ProtocolError


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.profile = provision(root/'identity')
        self.emulator = AircraftEmulator(self.profile)
        self.runner = web.AppRunner(self.emulator.app(), access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0, ssl_context=tls_context(root/'identity'))
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.store = DeviceStore(root/'aircraft.sqlite3')
        self.record = self.store.add(profile=self.profile, address=f'https://127.0.0.1:{port}',
                                     name='Test Scout', assembly='scout-110-bench-b@1')
        self.connection = AircraftConnection(self.store.get(self.record['id'], private=True))

    async def asyncTearDown(self):
        await self.connection.close()
        await self.runner.cleanup()
        self.folder.cleanup()

    async def wait_fault(self):
        async with asyncio.timeout(2):
            while self.connection.state != 'fault':
                await asyncio.sleep(.01)

    async def test_pairing_persists_without_returning_credentials(self):
        reopened = DeviceStore(self.store.path)
        self.assertEqual(self.store.list(), reopened.list())
        self.assertNotIn(self.profile['credential'], json.dumps(reopened.list()))
        self.assertEqual(os.stat(self.store.path).st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            self.store.add(profile=self.profile, address=self.record['endpoint'], name='Replacement',
                           assembly='scout-110-bench-b@1')
        snapshot = await self.connection.connect()
        self.assertTrue(snapshot['camera_ready'])
        self.assertFalse(snapshot['mission_ready'])
        self.assertEqual(self.emulator.core.state, 'disarmed')
        self.assertIsNone(self.emulator.core.owner)

    async def test_sensor_stop_invalidates_buffer_and_explicit_reconnect_works(self):
        await self.connection.connect()
        self.emulator.freeze_imu = True
        await self.wait_fault()
        self.assertEqual(len(self.connection.imu_samples), 0)
        with self.assertRaises(ProtocolError):self.connection.latest_frame()
        self.emulator.freeze_imu = False
        await asyncio.sleep(.03)
        await self.connection.connect()
        self.assertEqual(self.connection.state, 'connected')
        self.assertTrue(self.connection.take_imu()['samples'])

    async def test_camera_failure_does_not_disable_emergency_channel(self):
        await self.connection.connect()
        await self.connection.link.claim()
        await self.connection.link.command('arm')
        self.emulator.replay_frame = True
        await self.wait_fault()
        reply = await self.connection.stop('disarm')
        self.assertEqual(reply['state'], 'disarmed')
        self.assertIsNone(self.emulator.core.owner)

    async def test_bounded_imu_queue_reports_overflow_to_pose_consumer(self):
        await self.connection.connect()
        # Small buffer exercises the same overflow path without a long wait.
        from collections import deque
        self.connection.imu_samples = deque(maxlen=4)
        await asyncio.sleep(.15)
        packet = self.connection.take_imu()
        self.assertGreater(packet['dropped_samples'], 0)
        self.assertLessEqual(len(packet['samples']), 4)
        self.assertEqual(self.connection.take_imu()['dropped_samples'], 0)

    async def test_pairing_identity_mismatch_is_not_accepted(self):
        self.connection.identity = 'different-aircraft'
        with self.assertRaisesRegex(ProtocolError, 'identity'):
            await self.connection.connect()
        self.assertEqual(self.connection.state, 'fault')
        self.assertIsNone(self.connection.link.session)


if __name__ == '__main__':
    unittest.main()
