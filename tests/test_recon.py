import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from app.recon import Recon, decision, world

JPEG = (Path(__file__).resolve().parents[1]/'sim/assets/fixture-01.jpg').read_bytes()

class Manager:
    ready = True
    def status(self): return {'busy': False}
    async def image(self, *args):
        await asyncio.sleep(60)


class ReconTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.recon = Recon(Manager(), Path(self.temp.name))

    async def asyncTearDown(self):
        await self.recon.close()
        self.temp.cleanup()

    async def test_seeded_room_reproducible_and_not_constant(self):
        self.assertEqual(world(137), world(137))
        self.assertNotEqual(world(137), world(138))

    async def test_model_unavailable_does_not_fall_back(self):
        self.recon.manager.ready = False
        with self.assertRaisesRegex(RuntimeError, 'local model'): await self.recon.start('qwen', 'test')
        self.assertIsNone(self.recon.recorder)

    async def test_camera_and_sensor_failure_stop_inference_independently(self):
        r = self.recon
        await r.start('qwen', 'test')
        await asyncio.sleep(.15)
        r.camera(r.episode, 'test', r.ticket, JPEG)
        await asyncio.sleep(.15)
        self.assertIsNotNone(r.inference)
        r.sensor_frozen = True
        await asyncio.sleep(.5)
        self.assertEqual(r.state, 'failed')
        self.assertIn('stale', r.reason)
        self.assertTrue(r.inference.done())
        self.assertEqual(r.speed, 0)

    async def test_wrong_camera_token_is_not_used_for_decision(self):
        r = self.recon
        await r.start('scripted', 'test')
        await asyncio.sleep(.15)
        r.camera(r.episode, 'test', 'old-ticket', JPEG)
        self.assertIsNone(r.frame)
        with self.assertRaises(ValueError): r.camera('wrong-episode', 'test', r.ticket, JPEG)
        r.camera(r.episode, 'test', r.ticket, JPEG)
        await asyncio.sleep(.25)
        self.assertEqual(len(r.observations), 1)
        await r.pause()
        pose = list(r.pose)
        await asyncio.sleep(.2)
        self.assertEqual(r.pose, pose)

    async def test_browser_loss_deadline(self):
        r = self.recon
        await r.start('scripted','test')
        r.last_browser -= 3
        await asyncio.sleep(.15)
        self.assertEqual(r.state, 'failed')
        self.assertIn('connection lost', r.reason)
        self.assertTrue((r.recorder.directory/'summary.json').is_file())

    async def test_video_sequence_and_final_report(self):
        r = self.recon
        await r.start('scripted','test')
        await r.video(r.episode,'test',0,'video/webm',b'chunk0')
        with self.assertRaises(ValueError): await r.video(r.episode,'test',2,'video/webm',b'wrong')
        await r.land()
        await r.video(r.episode,'test',1,'video/webm',b'chunk1')
        await r.finalize_video(r.episode,'test')
        summary = json.loads((r.recorder.directory/'summary.json').read_text())
        self.assertTrue(summary['video']['complete'])
        self.assertEqual((r.recorder.directory/'onboard.webm').read_bytes(),b'chunk0chunk1')

    async def test_planner_only_uses_observed_map(self):
        r = self.recon
        r.sense(time.monotonic())
        route = r.plan()
        self.assertTrue(route)
        # No call to world collision/obstacle geometry in the planner.
        with patch('app.recon.clearance', side_effect=AssertionError('ground truth accessed')):
            self.assertEqual(r.plan(), route)
        self.assertTrue(all(r.safe_cell(c) for c in route))

    async def test_route_randomized_obstacle_safety(self):
        # Fast controller-level simulation; real-time browser/video tested separately.
        r = self.recon
        for seed in (1, 42, 137, 999):
            r.configure(seed)
            r.visited = set(); r.stops = 0; r.sensor_frozen = False
            r.distance, r.minimum_clearance = 0., 100.
            now = time.monotonic()
            for step in range(180):
                now += .1
                r.sense(now)
                r.move(.1, now)
            self.assertGreater(r.distance, 1)
            self.assertGreaterEqual(r.minimum_clearance, .12)

    async def test_decision_rejects_unbounded_actions(self):
        with self.assertRaises(ValueError): decision('{"action":"move_xyz","observation":"test"}')
        with self.assertRaises(ValueError): decision('{"action":"hold","action":"continue","observation":"test"}')
        with self.assertRaises(ValueError): decision('{"action":"continue","observation":"test","coordinates":[0,0,0]}')

    async def test_local_http_vision_changes_view_and_finishes(self):
        # Contract test with a local HTTP stub; deliberately not real-model evidence.
        from aiohttp import web
        from aiohttp.test_utils import TestServer
        from adapters.llama import LlamaBackend
        requests = []
        actions = []
        async def completion(request):
            body = await request.json()
            requests.append(body)
            if 'center' in body['response_format']['json_schema']['schema']['properties']:
                value={'visible_evidence':'Stub response for transport testing','center':'uncertain'}
            else:
                action='look_left' if not actions else 'finish'
                actions.append(action)
                value={'action':action}
            return web.json_response({'choices':[{'message':{'content':json.dumps(value)}}]})
        app = web.Application(); app.router.add_post('/v1/chat/completions', completion)
        async with TestServer(app) as server:
            backend = LlamaBackend(str(server.make_url('')).rstrip('/'))
            async def image(jpeg, prompt, schema):
                return await backend.image(jpeg, prompt, schema, time.monotonic()+6)
            async def text(prompt, schema):
                return await backend.text(prompt, schema, time.monotonic()+6)
            self.recon.manager.image = image
            self.recon.manager.text = text
            r = self.recon
            try:
                await r.start('qwen','test')
                deadline = time.monotonic()+3
                while r.state in ('observing','exploring','returning') and time.monotonic()<deadline:
                    r.camera(r.episode,'test',r.ticket,JPEG)
                    await asyncio.sleep(.12)
                self.assertEqual(r.state, 'complete')
                self.assertEqual(len(requests), 4)
                self.assertEqual(r.observations[0]['action'], 'look_left')
                self.assertNotEqual(r.observations[0]['pose'][3],r.observations[1]['pose'][3])
                self.assertTrue(requests[0]['messages'][0]['content'][0]['image_url']['url'].startswith('data:image/jpeg;base64,'))
                self.assertEqual(requests[0]['max_tokens'],128)
            finally:
                await backend.close()

    async def test_forward_obstacle_stops_before_motion(self):
        r = self.recon
        r.scene['obstacles'] = [dict(x=1.85, y=1.25, sx=.4, sy=1., height=2)]
        now = time.monotonic()
        r.sense(now)
        r.route = [r.cell(2.25,1.25)]
        r.speed = .6
        before = list(r.pose)
        r.move(.1, now)
        self.assertEqual(r.pose, before)
        self.assertEqual(r.speed, 0.)
        self.assertEqual(r.stops, 1)
