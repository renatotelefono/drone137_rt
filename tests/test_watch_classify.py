"""The kind of object change from pixels: added, taken away or moved; look-alikes elsewhere do not make a move."""
import asyncio
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from app.watch_classify import classify_change, union_box
from app.watch_events import EventStore, PerchedWatch, composite, encode, hint, says_person


def room(seed=0):
    rng = np.random.default_rng(seed)
    image = np.full((150, 200, 3), (120, 118, 112), np.uint8)
    image[100:, :] = (90, 95, 105)                                       # a darker floor
    return np.clip(image.astype(np.int16) + rng.integers(-4, 5, image.shape), 0, 255).astype(np.uint8)


def with_thing(image, x, y, colour=(40, 40, 200), size=(24, 30)):
    out = image.copy(); cv2.rectangle(out, (x, y), (x + size[0], y + size[1]), colour, -1)
    cv2.rectangle(out, (x + 4, y + 8), (x + size[0] - 4, y + 14), (230, 230, 230), -1)   # a label, so it has texture
    return out


class Classifier(unittest.TestCase):
    def test_a_thing_gone_is_removed_and_a_thing_arrived_is_added(self):
        empty, full = room(), with_thing(room(), 60, 50)
        box = (56, 46, 32, 38)
        self.assertEqual(classify_change(full, empty, [box])['category'], 'object_removed')
        self.assertEqual(classify_change(empty, full, [box])['category'], 'object_added')

    def test_the_same_thing_in_another_changed_box_is_moved(self):
        before, after = with_thing(room(), 40, 50), with_thing(room(), 120, 50)
        result = classify_change(before, after, [(36, 46, 32, 38), (116, 46, 32, 38)])
        self.assertEqual(result['category'], 'object_moved')
        self.assertEqual(result['bbox'][0], 40); self.assertGreaterEqual(result['bbox'][2], 100)

    def test_a_short_move_inside_one_box_is_moved(self):
        before, after = with_thing(room(), 60, 50), with_thing(room(), 84, 50)
        self.assertEqual(classify_change(before, after, [(56, 46, 56, 38)])['category'], 'object_moved')

    def test_a_look_alike_in_unchanged_surroundings_does_not_make_a_move(self):
        before = with_thing(with_thing(room(), 60, 50), 130, 50)    # two identical things
        after = with_thing(room(), 130, 50)                           # the first is taken away, the second stays
        result = classify_change(before, after, [(56, 46, 32, 38)])
        self.assertEqual(result['category'], 'object_removed', result['reason'])

    def test_nothing_standing_out_settles_nothing(self):
        before = room(); after = room(1)
        after[50:80, 60:90] = np.clip(after[50:80, 60:90].astype(int) + 2, 0, 255)      # a patch within the noise
        self.assertIsNone(classify_change(before, after, [(60, 50, 30, 30)])['category'])
        self.assertEqual(classify_change(before, after, [(0, 0, 0, 0)])['category'], None)

    def test_union_box(self):
        self.assertEqual(union_box([(10, 10, 5, 5), (20, 0, 5, 30)]), (10, 0, 15, 30))


class Evidence(unittest.TestCase):
    def test_composite_grows_a_small_box_to_a_legible_pair_of_labelled_panels(self):
        before, after = room(), with_thing(room(), 60, 50)
        pair = composite(before, after, (60, 50, 24, 30))
        self.assertEqual(pair.shape[1], 2*448 + 6)
        self.assertGreater(pair[:26].mean(), 0)                     # labels drawn in the band
        self.assertLess(pair.shape[0], pair.shape[1])              # the crop is no narrower than three quarters of its height
        tall = composite(before, after, (90, 0, 6, 150))
        self.assertLessEqual(tall.shape[0], 2*448)

    def test_the_summary_naming_a_person_counts_and_a_denial_does_not(self):
        for text in ('A person has been added to the scene in NOW.', 'Someone walked in from the left.', 'A worker stands by the rack.'):
            self.assertTrue(says_person(text), text)
        for text in ('A cardboard box has been added to the scene.', 'No person is visible now.', 'The cart moved; nobody is there.', None, ''):
            self.assertFalse(says_person(text), text)

    def test_hint_carries_the_pixel_verdict(self):
        candidate = {'kind': 'change', 'bbox': (10, 10, 40, 30), 'area_fraction': .05}
        self.assertIn('the thing was taken away', hint(candidate, (240, 320), {'category': 'object_removed', 'reason': 'it stood out before'}))
        self.assertIn('do not settle', hint(candidate, (240, 320), {'category': None, 'reason': 'x'}))
        self.assertNotIn('pixels', hint(candidate, (240, 320)))


class Clock:
    t = 0.

    def __call__(self):
        return self.t


class MergedEvent(unittest.IsolatedAsyncioTestCase):
    async def test_a_moved_thing_leaving_one_box_and_filling_another_is_one_moved_event_without_the_model(self):
        base = room(); frames = [with_thing(base, 40, 50)]*8 + [with_thing(base, 120, 50)]*12
        clock = Clock(); state = {'i': 0}
        def source():
            if state['i'] >= len(frames):
                return None
            f = frames[state['i']]; state['i'] += 1; clock.t = state['i']/2.5
            return encode(f), state['i'], clock.t
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(Path(d)/'w.sqlite3')
            watch = PerchedWatch('cam', source, store, Path(d)/'events', None, clock=clock)
            watch.state = 'watching'
            for _ in frames:
                await watch.step()
            events = store.list()
            self.assertEqual(len(events), 1)
            e = events[0]
            self.assertEqual((e['kind'], e['category'], e['matters']), ('change', 'object_moved', True))
            self.assertEqual(e['evidence']['detector_category'], 'object_moved'); self.assertIsNone(e['evidence']['model_category'])
            self.assertEqual(len(e['evidence']['boxes']), 2); self.assertIn('moved', e['summary'])
            self.assertTrue((Path(d)/'events'/e['id']/'composite.jpg').is_file())


if __name__ == '__main__':
    unittest.main()
