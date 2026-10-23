import unittest
from app.mission_identity import supported, parse


class CrossModelIdentity(unittest.TestCase):
    def test_both_independent_classifiers_required(self):
        good = {'category': 'fire_extinguisher', 'evidence': 'Cylinder, hose and handle'}
        self.assertTrue(supported(good, {'accepted': True}))
        self.assertFalse(supported(good, {'accepted': False}))
        self.assertFalse(supported({'category': 'gas_cylinder'}, {'accepted': True}))
        self.assertFalse(supported(None, {'accepted': True}))
        self.assertFalse(supported(good, None))

    def test_unknown_or_extra_fields_rejected(self):
        for raw in ('{"category":"extinguisher","evidence":"red"}',
                    '{"category":"fire_extinguisher","evidence":"red","ground_truth":true}'):
            with self.assertRaises(ValueError):
                parse(raw)
