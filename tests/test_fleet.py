import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from app.fleet import Fleet, DRONES, parse_plan, rectangle
from app.recon import Recon, ACTIVE
from app.reports import render_fleet_report

JPEG = (Path(__file__).resolve().parents[1]/'sim/assets/fixture-01.jpg').read_bytes()


class Manager:
    ready = True
    objective = 'inventory'
    def status(self): return {'busy': False, 'ready': self.ready}
    async def text(self, prompt, schema):
        self.prompt = prompt
        return json.dumps({'objective': self.objective, 'focus': 'visible bottles and boxes', 'summary': 'Inspect visible objects.'})


class FleetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = Manager()
        self.lab = Recon(self.manager, Path(self.temp.name)/'runs')
        self.fleet = Fleet(self.lab)
        self.body = {'area': [0, 0, 12, 10], 'instruction': 'Inventory visible objects', 'drones': list(DRONES)}

    async def asyncTearDown(self):
        await self.fleet.close()
        await self.lab.close()
        self.temp.cleanup()

    def cameras(self):
        for key in DRONES:
            self.fleet.heartbeat(key, {'client': key+'-camera', 'session': 'dashboard', 'ready': True, 'generation': self.fleet.generation})

    async def launch(self):
        draft = await self.fleet.plan(self.body)
        self.cameras()
        await self.fleet.launch(draft['id'], 'dashboard')

    async def test_area_bounded_partition_and_real_intent(self):
        plan = await self.fleet.plan({**self.body, 'area': [0, 0, 5.5, 10]})
        self.assertEqual([p for a in plan['assignments'] for p in a['points']], ['entry','stock-rack','passage'])
        self.assertTrue(plan['real_inference'])
        self.assertEqual(len(plan['assignments']), 2)
        self.assertIn(self.body['instruction'], self.manager.prompt)
        self.manager.objective = 'passage'
        plan = await self.fleet.plan(self.body)
        self.assertEqual(plan['assignments'], [{'drone_id': 'drone-01', 'points': ['passage']}])
        self.manager.objective = 'unsupported'
        plan = await self.fleet.plan(self.body)
        self.assertFalse(plan['dispatchable'])
        with self.assertRaises(ValueError): await self.fleet.launch(plan['id'], 'dashboard')

    async def test_mixed_hardware_plan_survives_profile_revision_and_freezes_evidence(self):
        first = self.fleet.airframes.assign('drone-01', 'reference-quad@1')
        second = self.fleet.airframes.assign('drone-02', 'light-quad@1')
        plan = await self.fleet.plan(self.body)
        changed = json.loads(json.dumps(first['profile']))
        changed['camera']['latency_ms'] = 210
        self.fleet.airframes.save(changed, expected_revision=1)
        self.cameras()
        await self.fleet.launch(plan['id'], 'dashboard')
        expected = {'drone-01': first, 'drone-02': second}
        self.assertEqual(self.fleet.mission['plan']['hardware'], expected)
        with self.fleet.airframes.connection() as db:
            frozen = db.execute('SELECT snapshots FROM experiments WHERE id=?',
                                (self.fleet.mission['id'],)).fetchone()[0]
        self.assertEqual(json.loads(frozen), list(expected.values()))
        evidence = json.loads((self.fleet.recorder.directory/'summary.json').read_text())
        self.assertEqual(evidence['plan']['hardware'], expected)
        with patch.object(Recon, 'run', return_value=None):
            await self.fleet.tick()
            self.assertEqual(self.fleet.drones['drone-01'].task_context['hardware'], first)

    async def test_hardware_http_revisions_and_assignment_invalidate_draft(self):
        from aiohttp.test_utils import TestClient, TestServer
        from app.recon_server import make_recon_app
        headers = {'X-Drone137-Control': 'local'}
        async with TestClient(TestServer(make_recon_app(self.lab))) as client:
            initial = await (await client.get('/api/airframes')).json()
            original = initial['assignments']['drone-01']['profile']
            body = {'profile': original, 'expected_revision': 1}
            self.assertEqual((await client.post('/api/airframes/save', json=body)).status, 403)
            original['camera']['latency_ms'] = 180
            saved = await client.post('/api/airframes/save', json=body, headers=headers)
            self.assertEqual(saved.status, 200)
            self.assertEqual((await saved.json())['revision'], 2)
            self.assertEqual((await client.post('/api/airframes/save', json=body, headers=headers)).status, 409)
            self.assertEqual((await client.post('/api/fleet/plan', json=self.body, headers=headers)).status, 200)
            response = await client.post('/api/airframes/assign', json={
                'vehicle_id': 'drone-02', 'reference': 'light-quad@1'}, headers=headers)
            self.assertEqual(response.status, 200)
            self.assertIsNone((await (await client.get('/api/fleet/status')).json())['draft'])
            final = await (await client.get('/api/airframes')).json()
            self.assertEqual(final['assignments']['drone-02']['profile']['id'], 'light-quad')

    async def test_invalid_area_inputs_and_model_output(self):
        for area in ([0,0,13,10], [0,0,float('nan'),10], [0,0,.1,1], [False,0,1,1], [0,0,1]):
            with self.assertRaises(ValueError): rectangle(area)
        for body in ({**self.body,'area':[10,8,12,10]}, {**self.body,'drones':['unknown']}, {**self.body,'drones':['drone-01']*2}):
            with self.assertRaises(ValueError): await self.fleet.plan(body)
        for raw in ('{"objective":"inventory","focus":"","summary":"ok","coordinates":[1,2]}',
                    '{"objective":"inventory","objective":"passage","focus":"","summary":"ok"}',
                    '{"objective":"fly","focus":"","summary":"ok"}'):
            with self.assertRaises(ValueError): parse_plan(raw)

    async def test_draft_identity_camera_owner_expiry_and_replay(self):
        plan = await self.fleet.plan(self.body)
        with self.assertRaisesRegex(RuntimeError,'camera'): await self.fleet.launch(plan['id'], 'dashboard')
        self.cameras()
        with self.assertRaisesRegex(RuntimeError,'camera'): await self.fleet.launch(plan['id'], 'another-tab')
        with self.assertRaises(ValueError): await self.fleet.launch('stale-id', 'dashboard')
        self.fleet.draft['created_at'] -= 601
        with self.assertRaises(ValueError): await self.fleet.launch(plan['id'], 'dashboard')
        await self.launch()
        with self.assertRaises(RuntimeError): await self.fleet.launch(plan['id'], 'dashboard')
        self.assertIsNone(self.fleet.draft)

    async def test_only_one_aircraft_then_handoff_after_evidence_finalization(self):
        await self.launch()
        with patch.object(Recon, 'run', return_value=None) as run:
            await self.fleet.tick()
            first, second = self.fleet.drones.values()
            self.assertIn(first.state, ACTIVE)
            self.assertEqual(second.state, 'idle')
            self.assertEqual([c['id'] for c in first.checkpoints], ['entry','stock-rack','passage'])
            self.assertEqual(len(first.scene['checkpoints']), 6)  # Renderer world stays unchanged.
            with self.assertRaises(ValueError): second.camera(first.episode, first.client, first.ticket, JPEG)
            with self.assertRaises(ValueError): await second.video(first.episode, first.client, 0, 'video/webm', b'wrong')
            with self.assertRaises(RuntimeError): self.fleet.heartbeat('drone-01', {'client':'intruder','session':'dashboard','ready':True})
            first.checkpoint_index = len(first.checkpoints)
            await first.finish('complete', 'Returned home')
            await self.fleet.tick()
            self.assertEqual(second.state, 'idle')
            await first.video(first.episode, first.client, 0, 'video/webm', b'first')
            await first.finalize_video(first.episode, first.client)
            self.cameras()
            await self.fleet.tick()
            self.assertIn(second.state, ACTIVE)
            self.assertNotEqual(first.episode, second.episode)
            self.assertEqual([c['id'] for c in second.checkpoints], ['equipment','far-room','seating'])
            self.assertEqual(second.task_context['drone_id'], 'drone-02')
            second.checkpoint_index = len(second.checkpoints)
            await second.finish('complete', 'Returned home')
            await second.video(second.episode, second.client, 0, 'video/webm', b'second')
            await second.finalize_video(second.episode, second.client)
            await self.fleet.tick()
            self.assertEqual(self.fleet.mission['state'], 'complete')
            summary=json.loads((self.fleet.recorder.directory/'summary.json').read_text())
            self.assertEqual(len({j['episode'] for j in summary['jobs']}),2)
            self.assertTrue(all(j['video_complete'] for j in summary['jobs']))

    async def test_stop_cancels_queue_before_any_next_dispatch(self):
        await self.launch()
        with patch.object(Recon, 'run', return_value=None):
            await self.fleet.tick()
            first, second = self.fleet.drones.values()
            first.pose[0] = 2.25
            await self.fleet.stop()
            self.assertEqual(first.state, 'ended')
            self.assertEqual(self.fleet.mission['jobs'][1]['state'], 'cancelled')
            self.assertTrue(self.fleet.reset_required)
            await self.fleet.tick()
            self.fleet.mission['jobs'][0]['finalizing_since'] -= 11
            await self.fleet.tick()
            self.assertEqual(second.state, 'idle')
            with self.assertRaises(RuntimeError): await self.fleet.plan(self.body)
            self.fleet.configure(619)
            self.assertFalse(self.fleet.reset_required)
            self.assertTrue(all(d.episode is None and d.state == 'idle' for d in self.fleet.drones.values()))

    async def test_disconnect_partial_and_missing_evidence_block_handoff(self):
        await self.launch()
        self.fleet.leases['drone-01']['time'] -= 3
        await self.fleet.tick()
        self.assertEqual(self.fleet.mission['state'], 'failed')
        self.assertTrue(all(j['state']=='cancelled' for j in self.fleet.mission['jobs']))
        await self.launch()
        with patch.object(Recon, 'run', return_value=None):
            await self.fleet.tick()
            first, second = self.fleet.drones.values()
            await first.finish('partial','Unreached views')
            await self.fleet.tick()
            self.assertEqual(self.fleet.mission['jobs'][1]['state'], 'cancelled')
            self.assertEqual(second.state, 'idle')

    async def test_lab_and_planner_cannot_overlap_model_requests(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed(prompt,schema):
            started.set();await release.wait()
            return '{"objective":"inventory","focus":"","summary":"Inspect objects"}'
        self.manager.text = delayed
        task=asyncio.create_task(self.fleet.plan(self.body));await started.wait()
        with self.assertRaises(RuntimeError): await self.fleet.plan(self.body)
        with self.assertRaises(RuntimeError): self.fleet.configure(1)
        release.set();await task
        self.lab.state='observing'
        with self.assertRaises(RuntimeError): await self.fleet.plan(self.body)
        self.lab.state='idle'

    async def test_subset_baseline_isolation_and_observation_focus(self):
        from app.perception import survey
        r=self.fleet.drones['drone-01']
        with patch.object(Recon,'run',return_value=None):
            await r.start('qwen','test','patrol',checkpoint_ids=['entry'],task_context={'focus':'bottles'})
            self.assertEqual(r.recorder.provenance['inspection_points'], ['entry'])
            await r.finish('complete','test')
            r.configure(619,'realism')
            self.assertIsNone(r.find_baseline())
        async def image(jpeg,prompt,schema,**kwargs):
            self.assertIn('bottles',prompt)
            self.assertIn('Do not infer',prompt)
            return '{"summary":"Visible objects","objects":[],"uncertainty":"No bottle is visible"}'
        await survey(image,JPEG,focus='bottles')

    async def test_return_keeps_current_inference_and_cancels_queue(self):
        await self.launch()
        with patch.object(Recon,'run',return_value=None):
            await self.fleet.tick()
            first=self.fleet.drones['drone-01']
            first.begin_observation()
            await self.fleet.stop(return_home=True)
            self.assertTrue(first.return_requested)
            self.assertEqual(first.state,'observing')
            self.assertEqual(self.fleet.mission['jobs'][1]['state'],'cancelled')

    def test_report_escapes_brief_and_rejects_injected_links(self):
        report=render_fleet_report('a'*32,{'state':'complete','plan':{'instruction':'<script>bad</script>'},
            'jobs':[{'drone_id':'drone-01','episode':'../../bad','points':[]}]})
        self.assertNotIn('<script>bad',report)
        self.assertNotIn('../../bad',report)
        self.assertIn('&lt;script&gt;',report)

    async def test_local_http_fleet_routes_keep_camera_namespaces_and_controls(self):
        from aiohttp.test_utils import TestClient, TestServer
        from app.recon_server import make_recon_app
        headers={'X-Drone137-Control':'local'}
        async with TestClient(TestServer(make_recon_app(self.lab))) as client:
            response=await client.get('/control')
            self.assertEqual(response.status,200)
            self.assertIn('Mission control',await response.text())
            self.assertEqual((await client.post('/api/fleet/plan',json=self.body)).status,403)
            self.assertEqual((await client.get('/api/fleet/drones/not-a-drone/status')).status,404)
            response=await client.post('/api/fleet/plan',json=self.body,headers=headers)
            self.assertEqual(response.status,200)
            plan=await response.json()
            self.assertEqual(len(plan['assignments']),2)
            response=await client.post('/api/fleet/launch',json={'draft_id':plan['id'],'session':'test'},headers=headers)
            self.assertEqual(response.status,409)  # No live cameras, so no dispatch.
            for key in DRONES:
                response=await client.post(f'/api/fleet/drones/{key}/camera?episode=wrong&client=wrong',data=JPEG,headers=headers)
                self.assertEqual(response.status,409)
            response=await client.post('/api/fleet/plan',json=[],headers=headers)
            self.assertEqual(response.status,409)

    async def test_lab_start_transition_excludes_fleet_inference(self):
        from aiohttp.test_utils import TestClient, TestServer
        from app.recon_server import make_recon_app
        entered, planning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original_start, original_plan = self.lab.start, self.fleet.plan
        async def slow_start(*args):
            entered.set();await release.wait();await original_start(*args)
        async def observed_plan(body):
            planning.set();return await original_plan(body)
        self.lab.start, self.fleet.plan = slow_start, observed_plan
        headers={'X-Drone137-Control':'local'}
        with patch('app.recon_server.Fleet',return_value=self.fleet):
            async with TestClient(TestServer(make_recon_app(self.lab))) as client:
                first=asyncio.create_task(client.post('/api/start',json={'policy':'scripted','client':'lab'},headers=headers))
                await entered.wait()
                second=asyncio.create_task(client.post('/api/fleet/plan',json=self.body,headers=headers))
                await planning.wait()
                self.assertFalse(second.done())
                self.assertFalse(hasattr(self.manager,'prompt'))
                release.set()
                self.assertEqual((await first).status,200)
                self.assertEqual((await second).status,409)
                self.assertFalse(hasattr(self.manager,'prompt'))
