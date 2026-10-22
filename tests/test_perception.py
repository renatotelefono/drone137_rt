import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from app.perception import parse, parse_survey, survey, compare, choose_action, aligned_views, VERSION, inspect, PASSAGE_VERSION
from app.recon import Recon
from app.reports import render_report


class PerceptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_passage_task_is_image_only_and_can_abstain(self):
        for blocked,expected in ((True,'solid_surface'),(False,'open_space'),(None,'uncertain')):
            async def image(pixels,prompt,schema):
                self.assertEqual(pixels,b'unchanged full image')
                self.assertNotIn('seed',prompt)
                return json.dumps({'visible_evidence':'Observed doorway','blocked':blocked})
            r=await inspect(image,b'unchanged full image',task='passage')
            self.assertEqual(r['center'],expected);self.assertEqual(r['version'],PASSAGE_VERSION)
        async def invalid(*args): return '{"visible_evidence":"Doorway","blocked":"false"}'
        with self.assertRaises(ValueError): await inspect(invalid,b'image',task='passage')
        with self.assertRaises(ValueError): await inspect(invalid,b'image',task='unknown')

    async def test_object_survey_is_bounded_and_image_only(self):
        calls=[]
        async def image(jpeg,prompt,schema,**kwargs):
            calls.append((jpeg,prompt,schema,kwargs))
            return '{"summary":"Boxes on a shelf","objects":["Brown cartons at center"],"uncertainty":"Labels unreadable"}'
        result=await survey(image,b'camera pixels')
        self.assertEqual(result['objects'],['Brown cartons at center'])
        self.assertEqual(calls[0][0],b'camera pixels')
        self.assertEqual(calls[0][3],{'max_tokens':384})
        self.assertNotIn('workshop',calls[0][1].lower())
        for changes in ({'objects':['x']*5},{'objects':[{}]},{'summary':''},{'uncertainty':'x'*161}):
            with self.assertRaises(ValueError):
                parse_survey(json.dumps({'summary':'View','objects':[],'uncertainty':'',**changes}))

    def test_object_survey_report_escapes_untrusted_descriptions(self):
        html=render_report('a'*32,{'camera':{'width':1280,'height':720,'snapshot_width':960,'snapshot_height':540},
            'observations':[{'image':'b'*32+'.jpg','survey':{'summary':'<script>bad</script>',
                'objects':['Red toolbox on the left','<img src=x onerror=bad>'],'uncertainty':'Small labels unreadable'}}]})
        self.assertNotIn('<script>bad',html)
        self.assertNotIn('<img src=x',html)
        self.assertIn('Red toolbox on the left',html)
        self.assertIn('Small labels unreadable',html)
        self.assertIn('1280 × 720 video',html)

    def test_strict_visual_evidence_contract(self):
        self.assertEqual(parse('{"visible_evidence":"A panel","center":"solid_surface"}')['version'], VERSION)
        for raw in ('{"visible_evidence":"A panel","center":"open_space","center":"solid_surface"}',
                    '{"visible_evidence":"A panel","center":"safe_to_fly"}',
                    '{"visible_evidence":"","center":"uncertain"}',
                    'null', '[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): parse(raw)

    def test_change_comparison_does_not_claim_whole_scene_unchanged(self):
        before={'center':'open_space'}
        self.assertEqual(compare(before, {'center':'solid_surface'})['status'], 'new_obstruction')
        self.assertEqual(compare(before, before)['status'], 'same_center_class')
        self.assertEqual(compare(before, {'center':'uncertain'})['status'], 'uncertain')
        self.assertEqual(compare({'center':'solid_surface'}, before)['status'], 'opening_visible')

    def test_comparison_requires_matching_viewpoints(self):
        self.assertTrue(aligned_views([1,2,1.4,0],[1,2,1.4,0]))
        self.assertFalse(aligned_views([1,2,1.4,0],[1.08,2,1.4,0]))
        self.assertFalse(aligned_views([1,2,1.4,0],[1,2,1.4,.1]))
        self.assertFalse(aligned_views(None,[1,2,1.4,0]))

    async def test_policy_rejects_duplicates_and_unavailable_actions(self):
        for raw in ('{"action":"finish"}', '{"action":"continue","action":"hold"}'):
            async def text(prompt, schema): return raw
            with self.assertRaises(ValueError):
                await choose_action(text, {'center':'open_space'}, ('continue','hold'))

    async def test_operator_pause_cancels_second_stage_policy(self):
        started=asyncio.Event()
        class Manager:
            ready=True
            def status(self): return {'busy':False}
            async def image(self, jpeg, prompt, schema):
                return '{"visible_evidence":"An opening","center":"open_space"}'
            async def text(self, prompt, schema):
                started.set()
                await asyncio.sleep(60)
        with tempfile.TemporaryDirectory() as folder:
            recon=Recon(Manager(),Path(folder))
            recon.configure(137,'warehouse')
            await recon.start('qwen','test','patrol',compare=False)
            recon.begin_observation()
            recon.camera(recon.episode,'test',recon.ticket,(Path('sim/assets/fixture-01.jpg')).read_bytes())
            await asyncio.wait_for(started.wait(),2)
            await recon.pause()
            self.assertTrue(recon.inference.done())
            self.assertEqual(recon.state,'paused')
            self.assertEqual(recon.speed,0)
            self.assertEqual(recon.observations,[])
            await recon.close()

    async def test_operator_pause_cancels_detailed_survey(self):
        started=asyncio.Event()
        class Manager:
            ready=True
            def status(self): return {'busy':False}
            async def image(self,jpeg,prompt,schema,**kwargs):
                if kwargs.get('max_tokens')==384:
                    started.set();await asyncio.sleep(60)
                return '{"visible_evidence":"A panel","center":"solid_surface"}'
            async def text(self,prompt,schema): return '{"action":"continue"}'
        with tempfile.TemporaryDirectory() as folder:
            recon=Recon(Manager(),Path(folder));recon.configure(137,'workshop')
            await recon.start('qwen','test','patrol',compare=False)
            recon.begin_observation()
            recon.camera(recon.episode,'test',recon.ticket,(Path('sim/assets/fixture-01.jpg')).read_bytes())
            await asyncio.wait_for(started.wait(),2)
            await recon.pause()
            self.assertTrue(recon.inference.done())
            self.assertEqual(recon.speed,0)
            self.assertEqual(recon.observations,[])
            await recon.close()

    def test_report_exposes_obstruction_finding_and_uncertainty(self):
        summary={'observations':[{'image':'b'*32+'.jpg','observation':'A panel',
            'perception':{'center':'solid_surface'}, 'change':{'status':'new_obstruction'}}]}
        html=render_report('a'*32,summary)
        self.assertIn('New obstruction in the camera center',html)
        self.assertIn('Camera center: solid surface',html)
        summary['observations'][0]['change']['status']='uncertain'
        self.assertIn('camera center is uncertain',render_report('a'*32,summary))
