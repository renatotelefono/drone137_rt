import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app import memory_budget
from app.memory_budget import GIB, ROOT
from app.preflight_api import install
from app.server import local_only


class Estimates(unittest.TestCase):
    def setUp(self):
        self.data = memory_budget.load_baselines()

    def test_gguf_header_is_read_without_touching_tensors(self):
        weights = ROOT/self.data['model']['weights']
        if not weights.is_file():
            self.skipTest('model file not installed')
        meta = memory_budget.gguf_metadata(weights)
        self.assertEqual(meta['architecture'], 'qwen3vl'); self.assertEqual(meta['layers'], 28); self.assertEqual(meta['kv_heads'], 8)
        self.assertEqual(meta['key_length'], 128); self.assertGreater(meta['bytes'], GIB)
        with self.assertRaises(ValueError):
            memory_budget.gguf_metadata(ROOT/'config/memory-baselines.json')

    def test_model_formula_counts_files_cache_and_overhead(self):
        meta = {'layers': 28, 'kv_heads': 8, 'key_length': 128, 'value_length': 128, 'embedding': 2048, 'heads': 16, 'bytes': 1000*GIB//1000}
        weights = ROOT/self.data['model']['weights']
        if not weights.is_file():
            self.skipTest('model file not installed')
        e = memory_budget.model_estimate(self.data['model'], meta)
        cache = 2*28*2048*8*128*2
        self.assertAlmostEqual(e['detail']['context_cache_gib'], cache/GIB, places=6)
        self.assertEqual(e['bytes'], int(GIB + (ROOT/self.data['model']['mmproj']).stat().st_size + cache + self.data['model']['server_overhead_gib']*GIB))
        missing = memory_budget.model_estimate({**self.data['model'], 'weights': 'nowhere.gguf'})
        self.assertIsNone(missing['bytes'])

    def test_flight_estimate_includes_the_allocated_grids(self):
        mapping, frames, jpegs, sizes = memory_budget.flight_structures()
        self.assertGreater(sizes['grids_bytes'], 2*2**20); self.assertIn('voxels', sizes['grid_shapes'])
        e = memory_budget.flight_estimate(self.data)
        self.assertGreater(e['bytes'], self.data['components']['flight']['gib']*GIB + sizes['grids_bytes'])

    def test_profiles_sum_their_components_and_unknown_profiles_are_refused(self):
        e = memory_budget.estimate('mission-simulation', self.data)
        self.assertEqual(set(e['components']), set(self.data['profiles']['mission-simulation']))
        known = sum(c['bytes'] for c in e['components'].values() if c['bytes'] is not None)
        self.assertAlmostEqual(e['total_gib'], known/GIB)
        self.assertGreater(e['total_gib'], 4)
        with self.assertRaises(ValueError):
            memory_budget.estimate('rocket', self.data)

    def test_verdict_static_and_dynamic(self):
        small = {'total_gib': 8., 'available_gib': 2., 'swap_used_gib': 0.}
        v = memory_budget.verdict(5.3, small, self.data)
        self.assertFalse(v['fits_machine']); self.assertFalse(v['fits_now']); self.assertEqual(v['budget_gib'], 3.5)
        v = memory_budget.verdict(2.4, small, self.data)
        self.assertTrue(v['fits_machine']); self.assertFalse(v['fits_now']); self.assertTrue(v['within_budget'])
        big = {'total_gib': 16., 'available_gib': 9., 'swap_used_gib': 0.}
        v = memory_budget.verdict(5.3, big, self.data)
        self.assertTrue(v['fits_machine']); self.assertTrue(v['fits_now']); self.assertEqual(v['budget_gib'], 5.)
        self.assertEqual(memory_budget.budget_gib(8, self.data), 3.5); self.assertEqual(memory_budget.budget_gib(16, self.data), 5.)

    def test_learned_baselines_only_grow(self):
        temp = tempfile.TemporaryDirectory(); learned = Path(temp.name)/'learned.json'
        original = memory_budget.LEARNED
        try:
            memory_budget.LEARNED = learned
            learned.write_text(json.dumps({'components': {'vio': {'gib': .01, 'basis': 'small'}, 'console': {'gib': .5, 'basis': 'large'}}}))
            data = memory_budget.load_baselines()
            self.assertEqual(data['components']['vio']['gib'], .15)          # smaller local figure ignored
            self.assertEqual(data['components']['console']['gib'], .5)       # larger local figure kept
            self.assertTrue(data['components']['console']['learned'])
        finally:
            memory_budget.LEARNED = original; temp.cleanup()


class MeasuredPreflight(unittest.IsolatedAsyncioTestCase):
    async def test_measures_the_flight_structures_and_keeps_estimates_as_floors(self):
        temp = tempfile.TemporaryDirectory(); original = memory_budget.LEARNED
        try:
            memory_budget.LEARNED = Path(temp.name)/'learned.json'
            report = await memory_budget.measure('mapping-flight', 1, verifier=False)
            self.assertIn('flight', report['measured']); self.assertGreater(report['measured_gib']['flight'], .02)
            flight = report['components']['flight']
            self.assertGreaterEqual(flight['bytes'], memory_budget.estimate('mapping-flight')['components']['flight']['bytes'])
            self.assertIn('vio', report['components']); self.assertEqual(report['components']['vio']['basis'][:12], 'not measured')
            self.assertIn('verdict', report); self.assertIn('fits_machine', report['verdict'])
            self.assertTrue(memory_budget.LEARNED.is_file())
        finally:
            memory_budget.LEARNED = original; temp.cleanup()


class Api(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = web.Application(middlewares=[local_only]); install(app)
        self.client = TestClient(TestServer(app)); await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_estimate_and_measure_routes(self):
        r = await self.client.get('/api/preflight/memory?profile=mapping-flight')
        self.assertEqual(r.status, 200); body = await r.json()
        self.assertEqual(body['profile'], 'mapping-flight'); self.assertIn('model-server', body['components']); self.assertIn('fits_machine', body)
        r = await self.client.get('/api/preflight/memory?profile=rocket')
        self.assertEqual(r.status, 409)
        r = await self.client.post('/api/preflight/memory', json={'profile': 'mapping-flight', 'seconds': 1, 'verifier': False}, headers={'X-Drone137-Control': 'local'})
        self.assertEqual(r.status, 200); body = await r.json()
        self.assertIn('flight', body['measured']); self.assertIn('host_after', body)
        r = await self.client.post('/api/preflight/memory', json={'seconds': 99}, headers={'X-Drone137-Control': 'local'})
        self.assertEqual(r.status, 409)


if __name__ == '__main__':
    unittest.main()
