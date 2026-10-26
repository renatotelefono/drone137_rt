import asyncio
import unittest

import aiohttp
from aiohttp import web

from app.components import Components
from hardware.esp32.connection_api import install as install_aircraft
from hardware.esp32.link_protocol import MAX_TILT_RAD, ProtocolError
from hardware.esp32.manual_api import install as install_manual
from hardware.esp32.manual_control import INPUT_LOST_S, MANUAL_LIMITS, STICK_RELEASE_S, ManualSession
from tests import test_aircraft_connection as fixtures


async def until(predicate, timeout=3.):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.01)


class ManualSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.ConnectionTests.asyncSetUp(self)
        await self.connection.connect()
        self.session = ManualSession(self.connection)

    async def asyncTearDown(self):
        await self.session.close()
        await fixtures.ConnectionTests.asyncTearDown(self)

    async def test_start_arms_and_streams_clamped_setpoints_at_twenty_hertz(self):
        snapshot = await self.session.start()
        self.assertEqual(snapshot['state'], 'armed'); self.assertEqual(self.emulator.core.state, 'armed')
        self.assertEqual(self.emulator.core.owner, 'drone137-manual')
        s = self.session.input({'roll_rad': .5, 'pitch_rad': -.5, 'yaw_rate_rad_s': 3., 'thrust': .95})
        self.assertEqual(s['setpoint'], {'roll_rad': MANUAL_LIMITS['tilt_rad'], 'pitch_rad': -MANUAL_LIMITS['tilt_rad'],
                                         'yaw_rate_rad_s': MANUAL_LIMITS['yaw_rate_rad_s'], 'thrust': MANUAL_LIMITS['thrust']})
        self.assertLess(MANUAL_LIMITS['tilt_rad'], MAX_TILT_RAD)
        for _ in range(5):
            await asyncio.sleep(.1)
            self.session.input({'roll_rad': .05, 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4})
        self.assertGreaterEqual(self.session.commands, 8)
        self.assertEqual(self.emulator.core.state, 'armed')
        self.assertAlmostEqual(self.emulator.core.setpoint.roll_rad, .05); self.assertAlmostEqual(self.emulator.core.setpoint.thrust, .4)

    async def test_release_levels_and_silence_lands(self):
        await self.session.start()
        self.session.input({'roll_rad': .1, 'pitch_rad': .1, 'yaw_rate_rad_s': .2, 'thrust': .4})
        await asyncio.sleep(STICK_RELEASE_S + .2)
        self.assertEqual(self.session.state, 'armed')
        self.assertEqual(self.emulator.core.setpoint.roll_rad, 0.); self.assertEqual(self.emulator.core.setpoint.pitch_rad, 0.)
        self.assertAlmostEqual(self.emulator.core.setpoint.thrust, .4)
        await until(lambda: self.session.state == 'ended', INPUT_LOST_S + 1.5)
        self.assertIn('No operator input', self.session.error)
        self.assertIn(self.emulator.core.state, ('landing', 'disarmed'))
        self.assertIsNone(self.session.link.session_id)
        self.assertIsNone(self.connection.link.session_id)   # the sensor monitor never claims

    async def test_refusals(self):
        busy = ManualSession(self.connection, mission_busy=lambda: True)
        with self.assertRaises(ProtocolError):
            await busy.start()
        self.assertEqual(self.emulator.core.state, 'disarmed')
        await self.session.start()
        with self.assertRaises(ProtocolError):
            await self.session.start()
        with self.assertRaises(ValueError):
            self.session.input({'roll_rad': float('nan'), 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .3})
        with self.assertRaises(ValueError):
            self.session.input({'roll': 0.})
        await self.session.land()
        with self.assertRaises(ProtocolError):
            self.session.input({'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .3})
        with self.assertRaises(ValueError):
            ManualSession(self.connection, limits={'tilt_rad': .5})

    async def test_land_ends_the_session_and_a_new_one_can_start_after_the_ramp(self):
        await self.session.start()
        self.session.input({'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .5})
        snapshot = await self.session.land()
        self.assertEqual(snapshot['state'], 'ended'); self.assertEqual(self.emulator.core.state, 'landing')
        self.assertEqual(snapshot['aircraft_state'], 'landing')
        await until(lambda: self.emulator.core.state == 'disarmed', 3.)
        again = ManualSession(self.connection)
        self.assertEqual((await again.start())['state'], 'armed')
        await again.close()

    async def test_sensor_monitor_fault_does_not_take_the_sticks_away(self):
        await self.session.start()
        self.session.input({'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4})
        self.emulator.replay_frame = True   # the camera monitor faults on a replayed frame and closes its own link
        await fixtures.ConnectionTests.wait_fault(self)
        for _ in range(4):
            await asyncio.sleep(.1)
            self.session.input({'roll_rad': .02, 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4})
        self.assertEqual(self.session.state, 'armed'); self.assertEqual(self.emulator.core.state, 'armed')
        self.assertEqual(self.connection.state, 'fault')

    async def test_one_lost_setpoint_is_retried_and_a_run_of_losses_lands(self):
        await self.session.start()
        self.session.input({'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4})
        original = self.session.link.command
        calls = {'n': 0}
        async def flaky(operation, **extra):
            calls['n'] += 1
            if calls['n'] in (3, 7):
                raise ProtocolError('Expired or excessive command deadline', 409)
            return await original(operation, **extra)
        self.session.link.command = flaky
        for _ in range(4):
            await asyncio.sleep(.1)
            self.session.input({'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4})
        self.assertEqual(self.session.state, 'armed'); self.assertGreaterEqual(self.session.failures, 1); self.assertIn('retry', self.session.error)
        async def dead(operation, **extra):
            raise TimeoutError('link gone')
        self.session.link.command = dead
        await until(lambda: self.session.state == 'fault', 3.)
        self.assertIn(self.emulator.core.state, ('landing', 'disarmed'))

    async def test_not_connected_is_refused(self):
        await self.connection.close()
        with self.assertRaises(ProtocolError):
            await self.session.start()


class ManualApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.ConnectionTests.asyncSetUp(self)
        from pathlib import Path
        root = Path(self.folder.name)
        app = web.Application(client_max_size=4096)
        self.registry, self.connections = install_aircraft(app, root/'api-aircraft.sqlite3', Components(root/'parts.sqlite3'))
        self.busy = False
        self.sessions = install_manual(app, self.connections, mission_busy=lambda: self.busy)
        self.api = web.AppRunner(app, access_log=None); await self.api.setup()
        site = web.TCPSite(self.api, '127.0.0.1', 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.address = f'http://127.0.0.1:{port}'
        self.client = aiohttp.ClientSession(headers={'X-Drone137-Control': 'local'})
        status, record = await self.post('/pair', {'profile': self.profile, 'address': self.record['endpoint'], 'name': 'Workshop Scout', 'assembly': 'scout-110-bench-b@1'})
        self.identity = record['id']

    async def asyncTearDown(self):
        await self.client.close(); await self.api.cleanup()
        await fixtures.ConnectionTests.asyncTearDown(self)

    async def post(self, path, body=None, **options):
        async with self.client.post(self.address + '/api/aircraft' + path, json={} if body is None else body, **options) as response:
            return response.status, await response.json()

    async def get(self, path):
        async with self.client.get(self.address + '/api/aircraft' + path) as response:
            return response.status, await response.json()

    async def test_start_input_status_land_over_the_api(self):
        self.assertEqual((await self.post(f'/{self.identity}/manual/start'))[0], 409)   # not connected yet
        self.assertEqual((await self.post(f'/{self.identity}/connect'))[0], 200)
        self.busy = True
        self.assertEqual((await self.post(f'/{self.identity}/manual/start'))[0], 409)
        self.busy = False
        status, s = await self.post(f'/{self.identity}/manual/start')
        self.assertEqual(status, 200, s); self.assertEqual(s['state'], 'armed'); self.assertEqual(s['limits']['tilt_rad'], MANUAL_LIMITS['tilt_rad'])
        status, s = await self.post(f'/{self.identity}/manual/input', {'roll_rad': .3, 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4})
        self.assertEqual(status, 200); self.assertEqual(s['setpoint']['roll_rad'], MANUAL_LIMITS['tilt_rad'])
        self.assertEqual((await self.post(f'/{self.identity}/manual/input', {'roll_rad': 'x'}))[0], 409)
        status, s = await self.get(f'/{self.identity}/manual')
        self.assertEqual(s['state'], 'armed')
        await asyncio.sleep(.25)
        self.assertEqual(self.emulator.core.state, 'armed')
        status, s = await self.post(f'/{self.identity}/manual/land')
        self.assertEqual(status, 200); self.assertEqual(s['state'], 'ended'); self.assertEqual(self.emulator.core.state, 'landing')
        self.assertEqual((await self.post(f'/{self.identity}/manual/input', {'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': .4}))[0], 409)

    async def test_manual_routes_need_the_local_header(self):
        async with self.client.post(self.address + f'/api/aircraft/{self.identity}/manual/start', json={}, headers={'X-Drone137-Control': ''}) as response:
            self.assertEqual(response.status, 403)
        async with self.client.post(self.address + f'/api/aircraft/{self.identity}/manual/input', json={}, headers={'Origin': 'https://untrusted.example'}) as response:
            self.assertEqual(response.status, 403)

    async def test_emergency_stop_works_during_manual_control(self):
        await self.post(f'/{self.identity}/connect')
        await self.post(f'/{self.identity}/manual/start')
        status, result = await self.post(f'/{self.identity}/disarm')
        self.assertEqual(status, 200); self.assertEqual(result['state'], 'disarmed')
        await until(lambda: self.sessions[self.identity].state != 'armed', 2.)
        self.assertEqual(self.emulator.core.state, 'disarmed')


if __name__ == '__main__':
    unittest.main()
