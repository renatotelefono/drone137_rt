import unittest

from scripts.evaluate import score_default_gates


class NativeEvaluationTests(unittest.TestCase):
    def events(self, second='closed'):
        return [
            {'event': 'observation', 'request_id': 'a', 'target': 'gate_a', 'image_file': 'a.jpg'},
            {'event': 'decision_accepted', 'request_id': 'a', 'observation': 'open', 'reason': 'Opening'},
            {'event': 'observation', 'request_id': 'b', 'target': 'gate_b', 'image_file': 'b.jpg'},
            {'event': 'decision_accepted', 'request_id': 'b', 'observation': second, 'reason': 'Panel'},
        ]

    def test_native_accuracy_is_required_separately_from_route_completion(self):
        self.assertTrue(score_default_gates(self.events())['passed'])
        for label in ('open', 'uncertain'):
            self.assertFalse(score_default_gates(self.events(label))['passed'])

    def test_missing_and_unmatched_observations_cannot_pass(self):
        self.assertFalse(score_default_gates([])['passed'])
        self.assertFalse(score_default_gates(self.events()[:2])['passed'])
        events = self.events()
        events[-1]['request_id'] = 'unknown'
        self.assertFalse(score_default_gates(events)['passed'])
