import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from app.components import Components
from sim.asset_world import build
from sim.hard_flight import cases
from adapters.rapier_drone import RapierDrone


class TransportIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_radio_command_recovers_with_observed_watchdog_landing(self):
        with tempfile.TemporaryDirectory() as folder:
            registry=Components(Path(folder)/'parts.sqlite3')
            drone=RapierDrone(registry.assemble('scout-110-bench-b'),build(cases()[0]),Path(folder))
            try:
                await drone.start()
                await drone.takeoff()
                self.assertGreater(drone.latest['position'][2],1.3)
                # Fault injection bypasses settle's validation to reproduce the
                # failed qualification flight's radio-pump rejection.
                drone.goal=[1.25,1.25,1.8000061511993408,0]
                async with asyncio.timeout(3):
                    while not drone.error:
                        await asyncio.sleep(.05)
                original=drone.error
                await drone.watchdog_land()
                self.assertEqual(drone.error,original)
                self.assertTrue(drone.landed)
                self.assertTrue(drone.latest['failsafe'])
                self.assertLess(drone.latest['position'][2],.05)
                self.assertEqual(drone.latest['contacts'],0)
                self.assertIn('supervisor-requested-failsafe',(Path(folder)/'transport-events.jsonl').read_text())
            finally:
                await drone.close()

    async def test_radio_survives_short_supervisor_gap_but_expires_its_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'input.json'
            registry = Components(Path(folder)/'components.sqlite3')
            path.write_text(json.dumps({'assembly': registry.assemble('scout-110-power-v2'),
                                        'scene': build(cases()[0]), 'seed': 137}))
            p = await asyncio.create_subprocess_exec('node', 'scripts/mission-transport.cjs', str(path),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            async def command(op='command'):
                p.stdin.write((json.dumps({'op': op, 'target': [1.25, 1.25, .6, 0]})+'\n').encode())
                await p.stdin.drain()
                return json.loads(await asyncio.wait_for(p.stdout.readline(), 4))
            try:
                await command()
                # Longer than the aircraft's 0.5 s watchdog: the dedicated
                # ground transport continues radio heartbeats independently.
                await asyncio.sleep(1.6)
                packet = await command()
                self.assertFalse(packet['failsafe'])
                self.assertGreater(packet['position'][2], .1)
                self.assertLess(packet['transport']['sample_age_s'], .2)
                # Exceed the 2 s supervisor lease plus 0.5 s aircraft watchdog.
                await asyncio.sleep(2.8)
                packet = await command('status')
                self.assertTrue(packet['failsafe'])
                self.assertTrue(packet['transport']['supervisor_lease_expired'])
                await asyncio.sleep(.3)
                self.assertTrue((await command())['failsafe'])  # No auto-resume.
            finally:
                await command('close')
                await asyncio.wait_for(p.wait(), 5)
            self.assertEqual(p.returncode, 0, (await p.stderr.read()).decode())
