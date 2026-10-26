"""End to end: scripted frames played by the protocol emulator, through the pinned link and the
sensor monitor, into the perched watch, out as an event with evidence."""
import asyncio
from pathlib import Path
import tempfile
import unittest

from aiohttp import web

from hardware.esp32.connection import AircraftConnection
from hardware.esp32.device_store import DeviceStore
from hardware.esp32.link_emulator import AircraftEmulator, provision, tls_context
from app.watch_events import EventStore, PerchedWatch
from sim.watch_scenes import jpeg, scenario
from tests.test_watch import FakeModel


class EmulatorWatch(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(); root = Path(self.folder.name)
        self.profile = provision(root/'identity')
        frames, self.truth = scenario('object_added', 21, duration_s=14., event_at_s=5.)
        self.emulator = AircraftEmulator(self.profile, frames=[jpeg(f) for t, f in frames])
        self.runner = web.AppRunner(self.emulator.app(), access_log=None); await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0, ssl_context=tls_context(root/'identity')); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        store = DeviceStore(root/'aircraft.sqlite3')
        record = store.add(profile=self.profile, address=f'https://127.0.0.1:{port}', name='Perched Scout', assembly='scout-110-bench-b@1')
        self.connection = AircraftConnection(store.get(record['id'], private=True))
        self.store = EventStore(root/'watch.sqlite3')

    async def asyncTearDown(self):
        await self.connection.close(); await self.runner.cleanup(); self.folder.cleanup()

    async def test_scripted_frames_reach_the_watch_and_raise_one_event(self):
        await self.connection.connect()
        def frames():
            try:
                image = self.connection.latest_frame()
            except Exception:
                return None
            return image['jpeg'], image['sequence'], image['capture_time_us']/1e6
        model = FakeModel('object_added', True)
        watch = PerchedWatch('perched', frames, self.store, Path(self.folder.name)/'watch', model, cooldown_s=30)
        await watch.start()
        try:
            async with asyncio.timeout(20):
                while watch.events < 1:
                    await asyncio.sleep(.1)
        finally:
            await watch.stop()
        event = self.store.list()[0]
        self.assertEqual(event['kind'], 'change'); self.assertEqual(event['category'], 'object_added'); self.assertTrue(event['matters'])
        self.assertGreater(watch.frames_seen, 5); self.assertEqual(model.calls, 1)
        self.assertTrue((Path(self.folder.name)/'watch'/event['id']/'composite.jpg').is_file())
        self.assertEqual(self.connection.state, 'connected')


if __name__ == '__main__':
    unittest.main()
