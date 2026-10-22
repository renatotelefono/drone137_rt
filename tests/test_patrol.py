import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

from app.navigation import ObservedMap, supervised_velocity
from app.recon import Recon
from app.reports import list_runs, render_report, evidence_image
from sim.recon_world import world, ray_distance

JPEG = (Path(__file__).resolve().parents[1]/'sim/assets/fixture-01.jpg').read_bytes()


class PatrolTests(unittest.IsolatedAsyncioTestCase):
    async def test_realism_camera_survives_start_and_isolates_baselines(self):
        class Manager:
            def status(self): return {'busy': False}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); r=Recon(Manager(),root)
            r.configure(417,'realism','baseline','dim')
            camera=dict(r.scene['camera'])
            await r.start('scripted','camera-test','patrol')
            self.assertEqual(r.scene['camera'],camera)
            self.assertEqual(r.scene['condition'],'dim')
            await r.close()
            directory=root/('f'*32);directory.mkdir()
            summary={'mode':'browser-kinematic-recon','mission':'patrol','state':'complete','policy':'qwen',
                     'seed':417,'scenario':'realism','visual_revision':'realism-v1','camera':camera}
            (directory/'summary.json').write_text(json.dumps(summary))
            r.configure(417,'realism','changed','nominal')
            self.assertIsNone(r.find_baseline())
            r.configure(417,'realism','changed','dim')
            self.assertEqual(r.find_baseline()['episode'],'f'*32)
            with self.assertRaises(ValueError): r.configure(417,'workshop','baseline','dim')
            with self.assertRaises(ValueError): r.configure(417,'realism','baseline','unknown')

    async def test_model_cannot_finish_patrol_from_one_empty_view(self):
        class Manager:
            ready = True
            def status(self): return {'busy': False}
            async def image(self, jpeg, prompt, schema):
                return json.dumps({'visible_evidence': 'An empty wall', 'center': 'solid_surface'})
            async def text(self, prompt, schema):
                self.schema = schema
                return json.dumps({'action': 'finish'})
        manager = Manager()
        with tempfile.TemporaryDirectory() as folder:
            r = Recon(manager, Path(folder))
            r.configure(137, 'warehouse')
            await r.start('qwen', 'test', 'patrol')
            r.begin_observation()
            r.camera(r.episode, 'test', r.ticket, JPEG)
            await asyncio.sleep(.35)
            self.assertEqual(r.state, 'failed')
            self.assertIn('unavailable action', r.reason)
            self.assertNotIn('finish', manager.schema['properties']['action']['enum'])
            await r.close()

    async def test_baseline_is_completed_matching_local_vision_patrol(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for i, changes in enumerate(({}, {'seed': 99}, {'state': 'partial'}, {'policy': 'scripted'})):
                directory = root/f'{i:032x}'; directory.mkdir()
                summary = {'mode': 'browser-kinematic-recon', 'mission': 'patrol', 'state': 'complete',
                           'policy': 'qwen', 'seed': 137, 'scenario': 'warehouse', **changes}
                (directory/'summary.json').write_text(json.dumps(summary))
            r = Recon(None, root); r.configure(137, 'warehouse', 'changed')
            self.assertEqual(r.find_baseline()['episode'], '0'*32)
            r.configure(137, 'rooms')
            self.assertIsNone(r.find_baseline())

    async def test_camera_timestamp_rejects_future_nan_and_wrong_episode(self):
        class Manager:
            def status(self): return {'busy': False}
        with tempfile.TemporaryDirectory() as folder:
            r = Recon(Manager(), Path(folder))
            await r.start('scripted', 'test')
            r.begin_observation()
            for stamp in (float('nan'), float('inf'), -1, 100):
                with self.assertRaises(ValueError): r.camera(r.episode, 'test', r.ticket, JPEG, stamp)
            r.camera(r.episode, 'test', r.ticket, JPEG, 0.)
            self.assertEqual(r.frame_video_time, 0.)
            await r.close()

    async def test_baseline_requires_same_visual_revision_and_camera(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); directory=root/('a'*32);directory.mkdir()
            summary={'mode':'browser-kinematic-recon','mission':'patrol','state':'complete','policy':'qwen',
                     'seed':137,'scenario':'workshop','visual_revision':'workshop-v1','camera':{'id':'module3-720p'}}
            recon=Recon(None,root);recon.configure(137,'workshop','changed')
            for field,bad in (('visual_revision','old-assets'),('camera',{'id':'lean'})):
                (directory/'summary.json').write_text(json.dumps({**summary,field:bad}))
                self.assertIsNone(recon.find_baseline())
            (directory/'summary.json').write_text(json.dumps(summary))
            self.assertIsNotNone(recon.find_baseline())


class MappingAndReports(unittest.TestCase):
    def test_recorded_return_recovery_still_stops_on_fresh_obstacle(self):
        r=Recon(None,Path('.local/data/runs'));r.scene['obstacles']=[]
        r.pose=[2.25,1.25,1.4,0];r.breadcrumbs=[[1.25,1.25],[1.75,1.25],[2.25,1.25]]
        r.return_requested=True;r.plan=lambda returning:[];r.sense(0.)
        self.assertTrue(r.move(.1,0.));self.assertIsNotNone(r.return_trace)
        before=list(r.pose)
        for ray in r.ranges:ray.update(distance=.1,hit=True)
        with self.assertRaisesRegex(RuntimeError,'Recorded return path blocked'):r.move(.1,0.)
        self.assertEqual(r.pose,before)

    def test_return_recovers_when_coarse_map_disconnects_flown_route(self):
        from scripts.evaluate_recon import episode
        result=episode(7)
        self.assertTrue(result['returned'],result)
        self.assertGreaterEqual(result['minimum_clearance_m'],.12)

    def test_return_plan_finishes_approach_inside_home_cell(self):
        m=ObservedMap();m.grid=[1]*len(m.grid)
        self.assertEqual(m.plan([1.45,1.25,1.4,0],set(),returning=True),[m.cell(1.25,1.25)])
        self.assertEqual(m.plan([1.25,1.25,1.4,0],set(),returning=True),[])

    def test_later_free_ranges_correct_an_isolated_occupied_cell(self):
        m=ObservedMap();pose=[1.25,1.25,1.4,0]
        hit={'angle':0.,'distance':1.28,'hit':True,'valid':True,'time':1.,'max_range':3.}
        m.integrate(pose,[hit],1.)
        cell=m.cell(2.53,1.25);self.assertEqual(m.grid[cell],2)
        clear={**hit,'distance':3.,'hit':False}
        for _ in range(8): m.integrate(pose,[clear],1.)
        self.assertEqual(m.grid[cell],1)
        for _ in range(8): m.integrate(pose,[hit],1.)
        self.assertEqual(m.grid[cell],2)

    def test_inflation_blocks_adjacent_cells_but_not_distant_diagonal(self):
        mapping=ObservedMap();mapping.grid=[1]*len(mapping.grid)
        cell=mapping.cell(5.25,4.25)
        mapping.grid[cell+mapping.nx+1]=2
        self.assertTrue(mapping.safe_cell(cell))
        mapping.grid[cell+1]=2
        self.assertFalse(mapping.safe_cell(cell))
        mapping.grid[cell+1]=0
        self.assertFalse(mapping.safe_cell(cell))

    def test_range_geometry_and_observed_map_are_separate(self):
        scene = world(1)
        scene['obstacles'] = [dict(x=3., y=1.25, sx=1., sy=1., height=2.)]
        distance, hit = ray_distance(scene, 1.25, 1.25, 0)
        self.assertTrue(hit)
        self.assertAlmostEqual(distance, 1.28)
        mapping = ObservedMap()
        rays = [{'angle': 0., 'distance': distance, 'hit': hit, 'valid': True, 'time': 10., 'max_range': 3.}]
        mapping.integrate([1.25,1.25,1.4,0], rays, 10.)
        self.assertEqual(mapping.grid[mapping.cell(2.53,1.25)], 2)
        self.assertEqual(mapping.grid[mapping.cell(4.,1.25)], 0)
        with self.assertRaisesRegex(RuntimeError, 'range unavailable'):
            supervised_velocity([1.25,1.25,1.4,0], .1, [2.25,1.25], rays, .1, 11.)

    def test_report_escapes_model_text_and_links_only_valid_evidence(self):
        report = render_report('a'*32, {'state': 'complete', 'policy': 'qwen',
            'video': {'chunks': 1, 'complete': True, 'mime': 'video/webm'},
            'observations': [{'image': 'b'*32+'.jpg', 'observation': '<script>alert(1)</script>',
                              'video_time_s': 3.2, 'action': 'continue'}]})
        self.assertNotIn('<script>alert', report)
        self.assertIn('&lt;script&gt;', report)
        self.assertIn('data-time="3.200"', report)
        self.assertIn('Camera-visible coverage is unmeasured', report)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): evidence_image(Path(folder), '../elsewhere', 'b'*32+'.jpg')
