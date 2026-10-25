import asyncio
import json
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app import mission_assistant, mission_wizard
from app.server import local_only


class Model:
    """Returns the interpretation a request would get, keyed on the request text."""
    def __init__(self):
        self.answers = {}
        self.prompts = []

    def status(self):
        return {'ready': True, 'state': 'ready'}

    async def text(self, prompt, schema):
        self.prompts.append(prompt)
        request = prompt.rsplit('Operator request: ', 1)[1]
        base = {'action': 'unknown', 'aircraft': '', 'targets': '', 'place': '', 'seed': 0, 'reply': 'I need more detail.'}
        return json.dumps({**base, **self.answers.get(json.loads(request), {})})


class Store:
    def __init__(self, rows):
        self.rows = rows

    def list(self):
        return [dict(r) for r in self.rows]

    def get(self, identity, private=False):
        return next(r for r in self.rows if r['id'] == identity)


class Connection:
    def __init__(self, record):
        self.record, self.state, self.calls = record, 'disconnected', []

    async def connect(self):
        self.state = 'connected'; self.calls.append('connect'); return {'id': self.record['id'], 'connection': 'connected'}

    async def close(self):
        self.state = 'disconnected'; self.calls.append('close')

    async def stop(self, op):
        self.calls.append(op); return {'id': self.record['id'], 'stopped': op}


class Runtime:
    def __init__(self):
        self.busy = False; self.stopped = []

    def available(self):
        return None

    def snapshot(self):
        return {'busy': self.busy, 'model': {'state': 'ready', 'ready': True}, 'mission': None}

    async def stop(self, return_home=False):
        self.stopped.append(return_home); return {'mission': {'state': 'returning' if return_home else 'landing'}}


class Launcher:
    def __init__(self):
        self.active = False; self.started = []

    def status(self):
        return None

    async def start(self, place, seed, name):
        self.started.append((place, seed, name)); return {'active': True, 'folder': 'x'}


def make():
    model = Model()
    rows = [{'id': 'em-1', 'name': 'Scout connection demo', 'kind': 'protocol-emulator', 'assembly': 'scout-110-bench-b@1'},
            {'id': 'ph-1', 'name': 'Workshop Scout', 'kind': 'aircraft', 'assembly': 'scout-110-bench-b@1'}]
    store, connections = Store(rows), {}
    runtime, launcher = Runtime(), Launcher()
    assistant = mission_assistant.Assistant(model, runtime, (store, connections), launcher, mission_wizard.load_templates())
    # Use the test connection class instead of the real link
    import hardware.esp32.connection as real
    real.AircraftConnection = Connection
    return model, store, connections, runtime, launcher, assistant


class AssistantTests(unittest.IsolatedAsyncioTestCase):
    def test_name_resolution(self):
        rows = Store(make()[1].rows).list()
        self.assertEqual(mission_assistant.resolve_aircraft('workshop scout', rows)[0]['id'], 'ph-1')
        self.assertEqual(mission_assistant.resolve_aircraft('the demo', rows)[0]['id'], 'em-1')
        self.assertEqual(mission_assistant.resolve_aircraft('the scout', rows)[0], None)
        self.assertIn('Paired:', mission_assistant.resolve_aircraft('the scout', rows)[1])
        self.assertEqual(mission_assistant.resolve_aircraft('', rows)[0], None)
        self.assertEqual(mission_assistant.resolve_aircraft('', rows[:1])[0]['id'], 'em-1')
        self.assertIn('No aircraft', mission_assistant.resolve_aircraft('x', [])[1])

    def test_parse_rejects_bad_interpretations(self):
        with self.assertRaises(ValueError):
            mission_assistant.parse(json.dumps({'action': 'launch', 'aircraft': '', 'targets': '', 'place': '', 'seed': 0, 'reply': ''}))
        with self.assertRaises(ValueError):
            mission_assistant.parse(json.dumps({'action': 'connect'}))

    async def test_connect_by_spoken_name_executes_through_the_registry(self):
        model, store, connections, runtime, launcher, assistant = make()
        model.answers['connect to the demo drone'] = {'action': 'connect', 'aircraft': 'demo drone'}
        out = await assistant.handle('connect to the demo drone')
        self.assertTrue(out['executed'])
        self.assertEqual(out['aircraft']['id'], 'em-1')
        self.assertEqual(connections['em-1'].calls, ['connect'])
        self.assertIn('protocol emulator', out['reply'])
        self.assertNotIn('credential', model.prompts[-1])
        model.answers['connect to the scout'] = {'action': 'connect', 'aircraft': 'the scout'}
        out = await assistant.handle('connect to the scout')
        self.assertEqual(out['action'], 'unknown')
        self.assertFalse(out['executed'])
        self.assertIn('Paired:', out['reply'])

    async def test_camera_disconnect_and_emergency(self):
        model, store, connections, runtime, launcher, assistant = make()
        model.answers['show the demo camera'] = {'action': 'show_camera', 'aircraft': 'demo'}
        out = await assistant.handle('show the demo camera')
        self.assertFalse(out['executed']); self.assertIn('not connected', out['reply'])
        connections['em-1'] = Connection(store.get('em-1')); await connections['em-1'].connect()
        out = await assistant.handle('show the demo camera')
        self.assertTrue(out['executed']); self.assertEqual(out['result']['camera'], 'em-1')
        model.answers['cut the motors on the workshop scout'] = {'action': 'cut_motors', 'aircraft': 'workshop scout'}
        out = await assistant.handle('cut the motors on the workshop scout')
        self.assertTrue(out['executed']); self.assertEqual(out['result']['stopped'], 'disarm')
        self.assertNotIn('ph-1', connections, 'emergency uses a transient connection, never queued')
        model.answers['disconnect the demo'] = {'action': 'disconnect', 'aircraft': 'demo'}
        out = await assistant.handle('disconnect the demo')
        self.assertTrue(out['executed']); self.assertEqual(connections['em-1'].calls[-1], 'close')

    async def test_exploration_needs_a_click_and_launch_is_never_offered(self):
        model, store, connections, runtime, launcher, assistant = make()
        model.answers['map a new room with seed 777'] = {'action': 'start_exploration', 'place': 'room-c', 'seed': 777}
        out = await assistant.handle('map a new room with seed 777')
        self.assertTrue(out['needs_confirmation']); self.assertFalse(out['executed']); self.assertEqual(launcher.started, [])
        self.assertEqual(out['proposal'], {'place': 'room-c', 'seed': 777, 'name': 'Unknown workshop 777'})
        await assistant.confirm({'kind': 'start_exploration', **out['proposal']})
        self.assertEqual(launcher.started, [('room-c', 777, 'Unknown workshop 777')])
        runtime.busy = True
        with self.assertRaises(RuntimeError):
            await assistant.confirm({'kind': 'start_exploration', **out['proposal']})
        with self.assertRaises(ValueError):
            await assistant.confirm({'kind': 'launch_mission'})
        self.assertNotIn('launch', mission_assistant.ACTIONS)

    async def test_audit_brief_status_and_listing(self):
        model, store, connections, runtime, launcher, assistant = make()
        model.answers['check the extinguisher and the blue toolbox'] = {'action': 'compose_audit', 'targets': 'red fire extinguisher, blue toolbox'}
        out = await assistant.handle('check the extinguisher and the blue toolbox')
        self.assertTrue(out['executed']); self.assertIn('red fire extinguisher', out['result']['instruction'])
        self.assertEqual(len(out['result']['warnings']), 1)
        model.answers['what drones do we have?'] = {'action': 'list_aircraft'}
        out = await assistant.handle('what drones do we have?')
        self.assertIn('protocol emulator', out['reply']); self.assertIn('physical aircraft', out['reply']); self.assertIn('scout-110-bench-b@1', out['reply'])
        model.answers['stop everything'] = {'action': 'stop_mission'}
        out = await assistant.handle('stop everything')
        self.assertTrue(out['executed']); self.assertEqual(runtime.stopped, [False])
        model.answers['hello'] = {}
        out = await assistant.handle('hello')
        self.assertEqual(out['action'], 'unknown'); self.assertFalse(out['executed'])

    async def test_api_routes(self):
        model, store, connections, runtime, launcher, assistant = make()
        model.answers['list drones'] = {'action': 'list_aircraft'}
        app = web.Application(middlewares=[local_only])
        mission_assistant.install(app, assistant)
        async with TestClient(TestServer(app)) as client:
            r = await client.post('/api/assistant/ask', json={'text': 'list drones'}, headers={'X-Drone137-Control': 'local'})
            self.assertEqual(r.status, 200); self.assertTrue((await r.json())['executed'])
            r = await client.post('/api/assistant/ask', json={'text': ''}, headers={'X-Drone137-Control': 'local'})
            self.assertEqual(r.status, 409)
            r = await client.post('/api/assistant/confirm', json={'proposal': {'kind': 'nothing'}}, headers={'X-Drone137-Control': 'local'})
            self.assertEqual(r.status, 409)


if __name__ == '__main__':
    unittest.main()
