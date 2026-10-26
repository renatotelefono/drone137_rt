import asyncio
import json
import math
from pathlib import Path
import tempfile
import unittest

from app import mission_assistant
from app.mission_wizard import load_templates
from app.mission_runtime import MissionRuntime

POSE = {'x': 1.25, 'y': 1.25, 'z': 0., 'yaw': math.pi}


class Model:
    async def text(self, *args):
        return json.dumps({'objective': 'inventory', 'focus': 'red fire extinguisher', 'summary': 'Search the room'})


class Vehicle:
    map = None
    latest = {'position': [1.3, 1.2, 0.], 'yaw': .5}
    interrupt = None


class RuntimeDocking(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = MissionRuntime(Model(), Path(self.temp.name)/'runs')
        self.body = {'instruction': 'Find the red fire extinguisher', 'case': 'hard-west-dim-present', 'assembly': 'scout-110-power-v2', 'area': [0, 0, 12, 10]}

    async def asyncTearDown(self):
        await self.runtime.close(); self.temp.cleanup()

    async def test_plan_refuses_unknown_dock_and_keeps_a_registered_one(self):
        with self.assertRaises(ValueError):
            await self.runtime.plan({**self.body, 'dock': 'nowhere'})
        with self.assertRaises(ValueError):
            await self.runtime.plan({**self.body, 'dock': 3})
        self.runtime.docks.register('hall-dock', 'Hall', POSE)
        draft = await self.runtime.plan({**self.body, 'dock': 'hall-dock'})
        self.assertEqual(draft['dock'], 'hall-dock')
        self.assertIsNone((await self.runtime.plan(self.body))['dock'])

    async def test_current_pose_and_dock_intervention(self):
        self.assertIsNone(self.runtime.current_pose())
        self.runtime.vehicle = Vehicle()
        self.assertEqual(self.runtime.current_pose(), {'x': 1.3, 'y': 1.2, 'z': 0., 'yaw': .5})
        self.runtime.docks.register('hall-dock', 'Hall', POSE)
        draft = await self.runtime.plan({**self.body, 'dock': 'hall-dock'})
        gate = asyncio.Event()
        async def run(plan):
            await gate.wait()
        self.runtime.execute = run
        await self.runtime.launch(draft['id'])
        snapshot = await self.runtime.stop(dock=True)
        self.assertEqual(snapshot['mission']['state'], 'docking'); self.assertEqual(self.runtime.intervention, 'dock')
        self.assertEqual(self.runtime.vehicle.interrupt, 'Operator requested dock')
        gate.set(); await self.runtime.task

    async def test_dock_intervention_needs_a_dock_on_the_plan(self):
        draft = await self.runtime.plan(self.body)
        gate = asyncio.Event()
        async def run(plan):
            await gate.wait()
        self.runtime.execute = run
        await self.runtime.launch(draft['id'])
        with self.assertRaises(ValueError):
            await self.runtime.stop(dock=True)
        gate.set(); await self.runtime.task

    async def test_source_hashes_cover_the_docking_modules(self):
        for path in ('app/docking.py', 'app/dock_tags.py', 'app/docks.py', 'sim/dock_world.py', 'config/dock-a.json'):
            self.assertIn(path, self.runtime.source_hashes)


class FakeDocks:
    def __init__(self, rows):
        self.rows = rows

    def list(self):
        return self.rows


class FakeClient:
    async def status(self):
        return {'mode': 'charge', 'supply_v': 5., 'pin_current_ma': 450, 'pad_temp_c': 24, 'contact': True, 'fault': None, 'uptime_s': 10}


class FakeRuntime:
    def __init__(self):
        self.busy = True; self.stopped = []
        self.run = {'id': 'm1', 'state': 'running', 'plan': {'dock': 'hall-dock'}}
        self.docks = FakeDocks([{'dock': {'id': 'hall-dock', 'name': 'Hall', 'place_id': 'hall'}}])
        self.dock_clients = {'hall-dock': FakeClient()}

    def available(self):
        return None

    def snapshot(self):
        return {'busy': self.busy, 'model': {'state': 'ready', 'ready': True}, 'mission': self.run}

    async def stop(self, return_home=False, dock=False):
        self.stopped.append('dock' if dock else 'return' if return_home else 'land'); return {'mission': {'state': 'docking'}}


class AssistantModel:
    def __init__(self, action):
        self.action = action

    def status(self):
        return {'ready': True, 'state': 'ready'}

    async def text(self, prompt, schema):
        return json.dumps({'action': self.action, 'aircraft': '', 'targets': '', 'place': '', 'seed': 0, 'reply': 'ok'})


class Store:
    def list(self):
        return []


class AssistantDocking(unittest.IsolatedAsyncioTestCase):
    async def test_dock_status_is_immediate(self):
        runtime = FakeRuntime()
        assistant = mission_assistant.Assistant(AssistantModel('dock_status'), runtime, (Store(), {}), None, load_templates())
        out = await assistant.handle('is the aircraft charging')
        self.assertTrue(out['executed']); self.assertEqual(out['result']['docks'][0]['status']['contact'], True)
        self.assertIn('docked, mode charge', out['reply'])

    async def test_return_to_dock_needs_confirmation_then_stops_with_dock(self):
        runtime = FakeRuntime()
        assistant = mission_assistant.Assistant(AssistantModel('return_to_dock'), runtime, (Store(), {}), None, load_templates())
        out = await assistant.handle('go back to the dock')
        self.assertTrue(out['needs_confirmation']); self.assertFalse(out['executed']); self.assertEqual(runtime.stopped, [])
        self.assertEqual(out['proposal'], {'kind': 'return_to_dock', 'dock': 'hall-dock', 'mission': 'm1'})
        result = await assistant.confirm(out['proposal'])
        self.assertEqual(result['mission']['state'], 'docking'); self.assertEqual(runtime.stopped, ['dock'])
        runtime.busy = False
        with self.assertRaises(RuntimeError):
            await assistant.confirm(out['proposal'])

    async def test_return_to_dock_without_dock_or_mission_is_refused(self):
        runtime = FakeRuntime(); runtime.run['plan'] = {}
        assistant = mission_assistant.Assistant(AssistantModel('return_to_dock'), runtime, (Store(), {}), None, load_templates())
        out = await assistant.handle('dock now')
        self.assertEqual(out['action'], 'unknown'); self.assertIn('without a dock', out['reply'])
        runtime.busy = False; runtime.run = None
        out = await assistant.handle('dock now')
        self.assertEqual(out['action'], 'unknown'); self.assertIn('No mission is flying', out['reply'])


if __name__ == '__main__':
    unittest.main()
