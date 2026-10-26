import asyncio
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.server import local_only
from app.watch_detector import ChangeDetector, iou
from app.watch_events import CATEGORIES, EventStore, PerchedWatch, composite, parse
from app.watch_api import install
from sim.watch_scenes import CATEGORIES as SCENES, jpeg, quiet, scenario


class Detector(unittest.TestCase):
    def test_each_staged_event_is_detected_with_the_right_kind_and_no_false_candidate_before(self):
        for category in SCENES:
            frames, truth = scenario(category, 11)
            detector = ChangeDetector(); found = None; early = 0
            for t, frame in frames:
                for c in detector.update(frame):
                    if t < truth['at'] - .5:
                        early += 1
                    elif found is None and c['kind'] == truth['kind']:
                        found = (t - truth['at'], c)
                        if c['kind'] == 'change':
                            detector.absorb()
            self.assertIsNotNone(found, category); self.assertEqual(early, 0, category)
            self.assertLessEqual(found[0], 2.5, category)
            if truth['kind'] == 'change':
                self.assertGreater(iou(found[1]['bbox'], truth['bbox']), .15, category)

    def test_quiet_frames_raise_nothing_and_absorb_resets_tracks(self):
        detector = ChangeDetector(); candidates = 0
        for i, (t, frame) in enumerate(quiet(3, hours=.02)):
            candidates += len(detector.update(frame))
        self.assertEqual(candidates, 0)
        detector.absorb(); self.assertEqual(detector.tracks, [])
        self.assertEqual(detector.reference_image().shape[:2], (240, 320))


class FakeModel:
    name = 'fake'

    def __init__(self, category='object_removed', matters=True, fail=False):
        self.category, self.matters, self.fail, self.calls = category, matters, fail, 0

    async def image(self, jpeg, prompt, schema, timeout=12, max_tokens=120):
        self.calls += 1
        if self.fail:
            raise RuntimeError('model down')
        self.assertion = jpeg[:2] == b'\xff\xd8'
        return json.dumps({'category': self.category, 'matters': self.matters, 'summary': 'A box was taken from the shelf.'})


class Clock:
    def __init__(self):
        self.t = 1000.

    def __call__(self):
        return self.t


def feeder(frames, clock):
    """Frames handed to the watch one per call, with the simulated clock advancing."""
    state = {'i': 0}
    def frames_source():
        if state['i'] >= len(frames):
            return None
        t, frame = frames[state['i']]; state['i'] += 1; clock.t = 1000. + t
        return jpeg(frame), state['i'], 1000. + t
    return frames_source


class Pipeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.store = EventStore(Path(self.temp.name)/'watch.sqlite3')

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def run_scenario(self, category, model, seed=5, **options):
        frames, truth = scenario(category, seed)
        clock = Clock()
        watch = PerchedWatch('em-1', feeder(frames, clock), self.store, Path(self.temp.name)/'watch/em-1', model, clock=clock, **options)
        watch.state = 'watching'
        for _ in frames:
            await watch.step()
        return watch, truth

    async def test_removed_object_becomes_one_event_with_evidence_and_the_model_answer(self):
        model = FakeModel('object_removed', True)
        watch, truth = await self.run_scenario('object_removed', model)
        events = self.store.list()
        self.assertEqual(len(events), 1); e = events[0]
        self.assertEqual(e['kind'], 'change'); self.assertEqual(e['category'], 'object_removed'); self.assertTrue(e['matters'])
        self.assertAlmostEqual(e['at'], 1000. + truth['at'], delta=2.5)
        folder = Path(self.temp.name)/'watch/em-1'/e['id']
        for name in ('before.jpg', 'after.jpg', 'composite.jpg'):
            self.assertTrue((folder/name).is_file())
        pair = cv2.imread(str(folder/'composite.jpg')); self.assertLessEqual(pair.shape[1], 960)
        self.assertEqual(model.calls, 1); self.assertEqual(watch.status()['events'], 1)
        self.assertEqual(self.store.alerts()[0]['id'], e['id'])
        acknowledged = self.store.acknowledge(e['id']); self.assertIsNotNone(acknowledged['acknowledged_at']); self.assertEqual(self.store.alerts(), [])
        with self.assertRaises(ValueError):
            self.store.acknowledge(e['id'])

    async def test_person_walk_is_one_motion_event_under_cooldown(self):
        model = FakeModel('person', True)
        watch, truth = await self.run_scenario('person', model)
        events = self.store.list()
        self.assertEqual([e['kind'] for e in events], ['motion']); self.assertEqual(events[0]['category'], 'person')
        self.assertGreaterEqual(watch.suppressed + watch.events, 1)

    async def test_lighting_is_recorded_without_the_model_and_does_not_alert(self):
        model = FakeModel('nothing', False)
        watch, truth = await self.run_scenario('lighting', model)
        events = self.store.list()
        self.assertEqual(len(events), 1); self.assertEqual(events[0]['kind'], 'lighting'); self.assertFalse(events[0]['matters'])
        self.assertEqual(model.calls, 0); self.assertEqual(self.store.alerts(), [])

    async def test_model_failure_still_records_an_unreviewed_alert(self):
        model = FakeModel(fail=True)
        watch, truth = await self.run_scenario('object_added', model)
        e = self.store.list()[0]
        self.assertIsNone(e['category']); self.assertTrue(e['matters']); self.assertIn('unreviewed', e['summary']); self.assertIn('model', watch.error)

    async def test_parse_and_composite(self):
        self.assertEqual(parse(json.dumps({'category': 'person', 'matters': True, 'summary': 'x'}))['category'], 'person')
        for bad in ({'category': 'alien', 'matters': True, 'summary': 'x'}, {'category': 'person', 'matters': 'yes', 'summary': 'x'}, {'category': 'person'}):
            with self.assertRaises(ValueError):
                parse(json.dumps(bad))
        a = np.zeros((480, 640, 3), np.uint8); b = a.copy()
        pair = composite(a, b, (300, 200, 40, 30))
        self.assertLessEqual(pair.shape[1], 960); self.assertGreaterEqual(pair.shape[1], 2*int(640*.4))
        self.assertGreater(pair[:22].mean(), 0)   # the BEFORE and NOW labels are drawn into the top band
        from app.watch_events import hint
        self.assertIn('moved across the frame', hint({'kind': 'motion', 'bbox': (0, 0, 40, 120), 'area_fraction': .02}, (480, 640)))
        self.assertIn('taller than wide', hint({'kind': 'motion', 'bbox': (0, 0, 40, 120), 'area_fraction': .02}, (480, 640)))
        self.assertIn('stayed still', hint({'kind': 'change', 'bbox': (0, 0, 120, 40), 'area_fraction': .05}, (480, 640)))


class Connection:
    def __init__(self, frames):
        self.frames, self.state, self.i = frames, 'connected', 0

    def latest_frame(self):
        self.i = min(self.i + 1, len(self.frames))
        t, frame = self.frames[self.i - 1]
        return {'jpeg': jpeg(frame), 'sequence': self.i, 'capture_time_us': int((1000 + t)*1e6)}


class Api(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        frames, self.truth = scenario('object_added', 7)
        self.connections = {'em-1': Connection(frames)}
        app = web.Application(middlewares=[local_only])
        self.watches, self.store = install(app, self.connections, model=FakeModel('object_added', True), store=EventStore(Path(self.temp.name)/'w.sqlite3'), folder=Path(self.temp.name)/'watch')
        self.client = TestClient(TestServer(app)); await self.client.start_server()
        self.headers = {'X-Drone137-Control': 'local'}

    async def asyncTearDown(self):
        await self.client.close(); self.temp.cleanup()

    async def test_start_watch_event_feed_ack_and_evidence(self):
        r = await self.client.post('/api/watch/em-2/start', json={}, headers=self.headers)
        self.assertEqual(r.status, 409)
        r = await self.client.post('/api/watch/em-1/start', json={}, headers=self.headers)
        self.assertEqual(r.status, 200); self.assertEqual((await r.json())['state'], 'watching')
        self.assertEqual((await self.client.post('/api/watch/em-1/start', json={}, headers=self.headers)).status, 409)
        watch = self.watches['em-1']; watch.period_s = 0.
        async with asyncio.timeout(20):
            while watch.events < 1:
                await asyncio.sleep(.05)
        r = await self.client.get('/api/watch'); body = await r.json()
        self.assertEqual(body['watches'][0]['events'], 1); self.assertEqual(len(body['alerts']), 1)
        event = body['alerts'][0]
        r = await self.client.get(f"/api/watch/events/{event['id']}/composite.jpg")
        self.assertEqual(r.status, 200); self.assertTrue((await r.read()).startswith(b'\xff\xd8'))
        r = await self.client.get('/api/watch/events?limit=5'); self.assertEqual(len(await r.json()), 1)
        r = await self.client.post(f"/api/watch/events/{event['id']}/ack", json={}, headers=self.headers)
        self.assertEqual(r.status, 200); self.assertEqual(len((await (await self.client.get('/api/watch')).json())['alerts']), 0)
        r = await self.client.post('/api/watch/em-1/stop', json={}, headers=self.headers)
        self.assertEqual((await r.json())['state'], 'stopped')
        r = await self.client.get('/api/watch/events/zzz/composite.jpg'); self.assertEqual(r.status, 404)


if __name__ == '__main__':
    unittest.main()
