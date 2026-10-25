import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app import mission_wizard
from app.mission_api import install
from app.mission_runtime import MissionRuntime
from app.place_memory import PlaceMemory
from app.server import local_only


class Model:
    def __init__(self):
        self.ready = True

    def status(self):
        return {'name': 'test model', 'ready': self.ready, 'state': 'ready', 'busy': False}

    async def text(self, *args):
        return json.dumps({'objective': 'inventory', 'focus': 'red fire extinguisher', 'summary': 'Search the room'})


class CatalogueTests(unittest.TestCase):
    def test_catalogue_has_four_clusters_with_gates_and_launch_paths(self):
        data = mission_wizard.load_templates()
        self.assertEqual(mission_wizard.template_ids(data), ['map', 'audit', 'watch', 'find'])
        for c in data['clusters']:
            self.assertTrue(c['gate'])
            self.assertIn(c['launch']['path'], mission_wizard.LAUNCH_PATHS)
        self.assertEqual(mission_wizard.validate_template(data, 'audit'), 'audit')
        self.assertIsNone(mission_wizard.validate_template(data, None))
        with self.assertRaises(ValueError):
            mission_wizard.validate_template(data, 'delivery')

    def test_invalid_catalogues_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder)/'t.json'
            bad.write_text(json.dumps({'clusters': [{'id': 'x', 'name': 'x', 'question': 'q', 'capability': 'seek', 'starts_from': 's',
                                                     'produces': 'p', 'gate': {}, 'fields': [], 'launch': {'path': 'mission', 'status': 'simulation', 'note': ''}}]}))
            with self.assertRaises(ValueError):
                mission_wizard.load_templates(bad)
            bad.write_text(json.dumps({'clusters': [{'id': 'x', 'name': 'x', 'question': 'q', 'capability': 'seek', 'starts_from': 's',
                                                     'produces': 'p', 'gate': {'g': 1}, 'fields': [{'id': 'f', 'type': 'video'}], 'launch': {'path': 'mission', 'status': 'simulation', 'note': ''}}]}))
            with self.assertRaises(ValueError):
                mission_wizard.load_templates(bad)

    def test_suggestions_follow_place_state(self):
        data = mission_wizard.load_templates()
        empty = mission_wizard.suggest(data, [], model_ready=True, mission_busy=False, exploration_active=False)
        self.assertEqual([p['id'] for p in empty['proposals']], ['map', 'audit', 'watch', 'find'])
        self.assertTrue(empty['proposals'][0]['ready'])
        self.assertFalse(empty['proposals'][2]['ready'])
        mapped = [{'id': 'room-a', 'name': 'Room A', 'visits': 2, 'mapped_visits': 1, 'latest_mapped_visit': 'a'*32, 'latest_state': 'complete'}]
        full = mission_wizard.suggest(data, mapped, model_ready=True, mission_busy=False, exploration_active=False)
        self.assertEqual(full['proposals'][0]['id'], 'audit')
        watch = next(p for p in full['proposals'] if p['id'] == 'watch')
        self.assertEqual(watch['prefill']['baseline'], 'a'*32)
        self.assertFalse(watch['ready'], 'planned clusters never report ready')
        busy = mission_wizard.suggest(data, mapped, model_ready=False, mission_busy=True, exploration_active=True)
        self.assertFalse(any(p['ready'] for p in busy['proposals']))
        classified = mission_wizard.suggest(data, mapped, model_ready=True, mission_busy=False, exploration_active=False,
                                            brief='what changed since last time?')
        self.assertEqual(classified['classified'], 'watch')
        self.assertEqual(classified['proposals'][0]['id'], 'watch')

    def test_brief_classification(self):
        self.assertEqual(mission_wizard.classify_brief('Map the new storage room'), 'map')
        self.assertEqual(mission_wizard.classify_brief('Check the extinguishers are in place'), 'audit')
        self.assertEqual(mission_wizard.classify_brief('Find the gas bottle in an unknown room'), 'find')
        self.assertEqual(mission_wizard.classify_brief('Find the red fire extinguisher'), 'audit')
        self.assertIsNone(mission_wizard.classify_brief('hello'))

    def test_compose_audit_and_map(self):
        data = mission_wizard.load_templates()
        out = mission_wizard.compose(data, 'audit', {'targets': 'Red Fire Extinguisher, blue toolbox', 'area': [0, 0, 6, 10]})
        self.assertIn('red fire extinguisher', out['instruction'].casefold())
        self.assertIn('return and land', out['instruction'])
        self.assertEqual(out['flyable_targets'], ['Red Fire Extinguisher'])
        self.assertEqual(len(out['warnings']), 1)
        with self.assertRaises(ValueError):
            mission_wizard.compose(data, 'audit', {'targets': ['blue toolbox']})
        with self.assertRaises(ValueError):
            mission_wizard.compose(data, 'audit', {'targets': []})
        plan = mission_wizard.compose(data, 'map', {'place': 'room-b', 'seed': 42})
        self.assertEqual((plan['place'], plan['seed'], plan['name']), ('room-b', 42, 'Unknown workshop 42'))
        with self.assertRaises(ValueError):
            mission_wizard.compose(data, 'map', {'place': 'Room B', 'seed': 42})
        planned = mission_wizard.compose(data, 'watch', {})
        self.assertEqual(planned['launch']['path'], 'none')
        with self.assertRaises(ValueError):
            mission_wizard.compose(data, 'delivery', {})


class WizardApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.model = Model()
        self.runtime = MissionRuntime(self.model, root/'runs')
        self.places = root/'places.sqlite3'
        memory = PlaceMemory(self.places)
        memory.begin('room-a', 'Room A', 'a'*32)
        memory.save_map('a'*32, {'cells': []})
        memory.finish('a'*32, 'complete', {})
        self.launcher = mission_wizard.ExplorationLauncher(root, output=root/'flights')
        (root/'.local/laya-env/bin').mkdir(parents=True)
        (root/'.local/laya-env/bin/python').touch()
        (root/'scripts').mkdir()
        (root/'scripts/run_blind_test.py').touch()
        app = web.Application(middlewares=[local_only])
        install(app, self.runtime, places=self.places, launcher=self.launcher)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.headers = {'X-Drone137-Control': 'local'}

    async def asyncTearDown(self):
        await self.client.close()
        await self.runtime.close()
        self.temp.cleanup()

    async def test_templates_and_suggestions_reflect_place_memory(self):
        r = await self.client.get('/api/wizard/templates')
        self.assertEqual(r.status, 200)
        self.assertEqual([c['id'] for c in (await r.json())['clusters']], ['map', 'audit', 'watch', 'find'])
        r = await self.client.get('/api/wizard/suggestions?brief=check%20the%20extinguishers')
        data = await r.json()
        self.assertEqual(data['mapped_places'], 1)
        self.assertEqual(data['classified'], 'audit')
        self.assertEqual(data['proposals'][0]['id'], 'audit')
        self.assertTrue(data['proposals'][0]['ready'])
        self.assertEqual(data['places'][0]['id'], 'room-a')
        self.assertIsNone(data['exploration'])

    async def test_compose_feeds_the_existing_plan_with_a_template_tag(self):
        r = await self.client.post('/api/wizard/compose', json={'template': 'audit', 'fields': {'targets': 'red fire extinguisher'}}, headers=self.headers)
        self.assertEqual(r.status, 200)
        out = await r.json()
        draft = await self.runtime.plan({'instruction': out['instruction'], 'case': 'hard-west-dim-present',
                                         'assembly': 'scout-110-power-v2', 'area': out['area'], 'template': out['template']})
        self.assertEqual(draft['template'], 'audit')
        self.assertTrue(draft['dispatchable'])
        with self.assertRaises(ValueError):
            await self.runtime.plan({'instruction': out['instruction'], 'case': 'hard-west-dim-present',
                                     'assembly': 'scout-110-power-v2', 'area': out['area'], 'template': 'delivery'})
        gate = asyncio.Event()
        async def run(plan):
            await gate.wait()
        self.runtime.execute = run
        launched = await self.runtime.launch(draft['id'])
        self.assertEqual(launched['mission']['plan']['template'], 'audit')
        gate.set()
        await self.runtime.task

    async def test_exploration_launch_is_exclusive_and_reports_status(self):
        script = ("import json,sys,time,pathlib;f=pathlib.Path(sys.argv[1]);(f/'explorer').mkdir(parents=True);"
                  "(f/'explorer/summary.json').write_text(json.dumps({'state':'partial','steps':[1,2,3],'wall_time_s':4.5}));"
                  "(f/'score.json').write_text(json.dumps({'accepted':True,'metrics':{'free_space_coverage':.83},'gates':{'coverage':True}}));print('done')")
        folder_holder = {}
        original = self.launcher.start
        async def start(place, seed, name):
            self.launcher.command = [sys.executable, '-c', script, str(self.launcher.output/'pending')]
            return await original(place, seed, name)
        self.launcher.start = start
        r = await self.client.post('/api/wizard/explore', json={'place': 'room-b', 'seed': 42}, headers=self.headers)
        self.assertEqual(r.status, 200, await r.text())
        status = await r.json()
        self.assertTrue(status['active'] or status['exit_code'] is not None)
        await self.launcher.process.wait()
        # The fake runner wrote into a fixed folder; point the launcher at it for status.
        self.launcher.folder = self.launcher.output/'pending'
        r = await self.client.get('/api/wizard/explore/status')
        status = await r.json()
        self.assertFalse(status['active'])
        self.assertEqual(status['exit_code'], 0)
        self.assertEqual((status['state'], status['observations'], status['score']['accepted']), ('partial', 3, True))
        self.assertIn('done', status['last_line'])
        r = await self.client.post('/api/wizard/explore', json={'place': 'Bad Name', 'seed': 42}, headers=self.headers)
        self.assertEqual(r.status, 409)
        self.assertIn('Place name', (await r.json())['error'])

    async def test_exploration_refused_while_a_mission_is_active(self):
        self.runtime.planning = True
        r = await self.client.post('/api/wizard/explore', json={'place': 'room-b', 'seed': 42}, headers=self.headers)
        self.assertNotEqual(r.status, 200)
        self.runtime.planning = False
        r = await self.client.get('/api/wizard/explore/status')
        self.assertEqual(r.status, 404)


if __name__ == '__main__':
    unittest.main()
