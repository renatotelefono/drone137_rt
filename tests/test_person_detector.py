"""A person is the person detector's call: a real person is seen, a cart or a drawn silhouette is not, and the model is not asked."""
import asyncio
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from app.person_detector import PersonDetector, available_backend, overlap, person_in
from app.watch_events import EventStore, PerchedWatch
from sim.watch_scenes import PERSON_PHOTO, jpeg, room, scenario

ROOT = Path(__file__).resolve().parents[1]
HAVE_BACKEND = available_backend() == 'apple-vision'


class Boxes(unittest.TestCase):
    def test_overlap_is_over_the_smaller_box_and_person_in_picks_the_best(self):
        self.assertAlmostEqual(overlap((0, 0, 10, 10), (5, 0, 10, 10)), .5)
        self.assertEqual(overlap((0, 0, 10, 10), (20, 20, 5, 5)), 0.)
        found = [{'confidence': .9, 'bbox': (100, 100, 50, 80)}, {'confidence': .6, 'bbox': (0, 0, 20, 20)}]
        self.assertEqual(person_in(found, (120, 120, 60, 60))['confidence'], .9)
        self.assertIsNone(person_in(found, (300, 300, 10, 10)))
        self.assertEqual(PersonDetector(backend=None).detect(np.zeros((10, 10, 3), np.uint8)), [])


@unittest.skipUnless(HAVE_BACKEND, 'Apple Vision is not available here; the watch falls back to the model')
class AppleVision(unittest.TestCase):
    def test_a_real_person_is_seen_in_the_room_and_a_drawn_figure_or_a_box_is_not(self):
        detector = PersonDetector()
        self.assertEqual(detector.backend, 'apple-vision')
        frames, truth = scenario('person_photo', 100)
        mid = next(f for t, f in frames if abs(t - 14.) < .3)
        seen = person_in(detector.detect(mid), truth['bbox'])
        self.assertIsNotNone(seen); self.assertGreaterEqual(seen['confidence'], .5)
        self.assertEqual(detector.detect(room()), [])
        frames, truth = scenario('object_added', 100)
        self.assertEqual(detector.detect(frames[-1][1]), [])
        frames, truth = scenario('person', 100)   # the drawn silhouette is not a person to it: that path stays with the model
        mid = next(f for t, f in frames if abs(t - 14.) < .3)
        self.assertIsNone(person_in(detector.detect(mid), truth['bbox']))


class Clock:
    t = 0.

    def __call__(self):
        return self.t


class CountingModel:
    name = 'counting'

    def __init__(self):
        self.calls = 0

    async def image(self, jpeg, prompt, schema, timeout=12, max_tokens=120):
        self.calls += 1
        return '{"summary": "A box appeared.", "category": "object_added", "matters": true}'


class Pipeline(unittest.IsolatedAsyncioTestCase):
    async def play(self, category, model):
        frames, truth = scenario(category, 100)
        clock = Clock(); state = {'i': 0}
        def source():
            if state['i'] >= len(frames):
                return None
            t, f = frames[state['i']]; state['i'] += 1; clock.t = t
            return jpeg(f), state['i'], t
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(Path(d)/'w.sqlite3')
            watch = PerchedWatch(category, source, store, Path(d)/'events', model, clock=clock)
            watch.state = 'watching'
            for _ in frames:
                await watch.step()
            return store.list(), truth, watch

    @unittest.skipUnless(HAVE_BACKEND, 'Apple Vision is not available here')
    async def test_a_real_person_walking_through_is_a_person_event_without_asking_the_model(self):
        model = CountingModel()
        events, truth, watch = await self.play('person_photo', model)
        hits = [e for e in events if e['kind'] == 'motion' and e['at'] >= truth['at'] - .5]
        self.assertEqual(len(hits), 1)
        e = hits[0]
        self.assertEqual((e['category'], e['matters'], e['summary']), ('person', True, 'A person is in view'))
        self.assertTrue(e['evidence']['person_detector']['seen']); self.assertIsNone(e['evidence']['model_category'])
        self.assertEqual(model.calls, 0)
        self.assertEqual(watch.status()['person_detector'], 'apple-vision')

    async def test_without_a_backend_the_model_is_asked_as_before(self):
        model = CountingModel()
        frames, truth = scenario('person_photo', 100)
        clock = Clock(); state = {'i': 0}
        def source():
            if state['i'] >= len(frames):
                return None
            t, f = frames[state['i']]; state['i'] += 1; clock.t = t
            return jpeg(f), state['i'], t
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(Path(d)/'w.sqlite3')
            watch = PerchedWatch('x', source, store, Path(d)/'events', model, clock=clock, people=PersonDetector(backend=None))
            watch.state = 'watching'
            for _ in frames:
                await watch.step()
            e = next(e for e in store.list() if e['kind'] == 'motion')
            self.assertGreaterEqual(model.calls, 1)
            self.assertEqual(e['evidence']['person_detector'], {'backend': None, 'seen': False})
            self.assertEqual(watch.status()['person_detector'], None)


if __name__ == '__main__':
    unittest.main()
