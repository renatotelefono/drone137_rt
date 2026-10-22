import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from app.reliability import (load_manifest, read_json, score_case, summarize, domain_gates,
                             zero_failure_upper, render_html)
from scripts.evaluate_reliability import exposure_conflicts


def case(name='one', center='solid_surface'):
    return {'id': name, 'site_id': 'site-a', 'encounter_id': 'encounter-a',
            'camera_id': 'candidate-camera', 'perception_profile': 'detail',
            'domain': 'workshop', 'source_kind': 'target_camera', 'split': 'held_out',
            'conditions': ['nominal'], 'provenance': 'Locally captured test fixture',
            'annotation': {'center': center, 'reviewer':'fixture-author', 'reviewer_kind':'human',
                           'required_objects':[['monitor','screen']], 'notes':'Labelled test fixture'}}


def output(name='one', center='solid_surface', action='continue', summary='A monitor'):
    return {'id':name,'perception':{'center':center},'action':action,
            'survey':{'summary':summary,'objects':[]},'latency_s':2.0}


class ReliabilityTests(unittest.TestCase):
    def dataset(self, folder, cases):
        for i,c in enumerate(cases):
            data=b'\xff\xd8fixture'+bytes([i])+b'\xff\xd9'
            c.update(path=f'{i}.jpg',image_sha256=hashlib.sha256(data).hexdigest())
            (folder/c['path']).write_bytes(data)
        p=folder/'manifest.json'
        p.write_text(json.dumps({'version':1,'dataset_id':'test','cases':cases}))
        return p

    def test_site_overlap_and_image_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);a,b=case(),case('two');b['split']='development'
            p=self.dataset(folder,[a,b])
            with self.assertRaisesRegex(ValueError,'Site appears'):load_manifest(p)
            b['split']='held_out';b['path']=a['path'];b['image_sha256']=a['image_sha256']
            p.write_text(json.dumps({'version':1,'dataset_id':'test','cases':[a,b]}))
            with self.assertRaisesRegex(ValueError,'Duplicate image'):load_manifest(p)

    def test_mutated_input_and_unsafe_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);c=case();p=self.dataset(folder,[c]);load_manifest(p)
            (folder/c['path']).write_bytes(b'\xff\xd8changed\xff\xd9')
            with self.assertRaisesRegex(ValueError,'checksum'):load_manifest(p)
            c=case('../escape');p=self.dataset(folder,[c])
            with self.assertRaisesRegex(ValueError,'filename'):load_manifest(p)

    def test_missing_annotations_and_unknown_domains_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            for change in ({'annotation':{}},{'domain':'anywhere'},{'perception_profile':'automatic'}):
                c=case();c.update(change);p=self.dataset(Path(temp),[c])
                with self.assertRaises(ValueError):load_manifest(p)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input.json';p.write_text('{"version":1,"version":2}')
            with self.assertRaises(ValueError):read_json(p)

    def test_required_objects_are_whole_phrases_not_substrings(self):
        self.assertFalse(score_case(case(),output(summary='A monitoring system'))['passed'])
        self.assertTrue(score_case(case(),output(summary='A black MONITOR.'))['passed'])

    def test_uncertain_reference_requires_uncertain_perception_and_relook_or_hold(self):
        c=case(center='uncertain')
        self.assertFalse(score_case(c,output(center='uncertain'))['passed'])
        self.assertTrue(score_case(c,output(center='uncertain',action='look_left'))['passed'])
        self.assertFalse(score_case(c,output(center='open_space',action='hold'))['passed'])

    def test_missing_or_error_cannot_improve_false_clear_bound(self):
        stats=summarize([case()],[])
        self.assertEqual(stats['case_checks_passed'],0)
        self.assertIsNone(stats['false_clear_upper_95_if_independent'])
        stats=summarize([case()],[{**output(),'error':'timeout'}])
        self.assertIsNone(stats['false_clear_upper_95_if_independent'])
        self.assertEqual(stats['errors_or_missing'],1)

    def test_adjacent_frames_count_as_one_encounter(self):
        cases=[case(str(i)) for i in range(300)]
        results=[output(str(i)) for i in range(300)]
        stats=summarize(cases,results)
        self.assertEqual(stats['blocked_encounters'],1)
        self.assertAlmostEqual(stats['false_clear_upper_95_if_independent'],.95)
        results[-1]['perception']['center']='open_space'
        stats=summarize(cases,results)
        self.assertEqual(stats['false_clear_encounters'],1)
        self.assertEqual(stats['center_encounter_accuracy'],0)

    def test_exact_zero_failure_bound_and_no_empty_pass(self):
        self.assertIsNone(zero_failure_upper(0,0))
        self.assertIsNone(zero_failure_upper(1,300))
        self.assertLess(zero_failure_upper(0,300),.01)
        self.assertGreater(zero_failure_upper(0,32),.08)

    def test_proxy_synthetic_development_and_agent_labels_cannot_qualify(self):
        for change in ({'source_kind':'public_real'},{'source_kind':'synthetic'},
                       {'split':'development'},{'annotation':{**case()['annotation'],'reviewer_kind':'agent'}}):
            c=case();c.update(change)
            domains=domain_gates({'cases':[c]},[output()])
            self.assertEqual(domains['workshop']['metrics']['cases'],0)
            self.assertTrue(all(not d['real_world_qualified'] for d in domains.values()))

    def test_new_frame_from_used_site_is_not_a_new_holdout(self):
        c={**case(),'image_sha256':'fresh'}
        self.assertEqual(exposure_conflicts([c],[{'image_sha256':'old','site_id':'site-a'}]),['one'])
        self.assertEqual(exposure_conflicts([c],[{'image_sha256':'fresh','site_id':'elsewhere'}]),['one'])

    def test_report_escapes_model_content_and_never_invents_caption_precision(self):
        c=case();r=output(summary='<script>bad</script>')
        report={'scope':'Diagnostic only','cases':[c],'results':[r],
                'summary':summarize([c],[r]),'domains':domain_gates({'cases':[c]},[r])}
        content=render_html(report)
        self.assertNotIn('<script>bad',content)
        self.assertIn('&lt;script&gt;',content)
        self.assertIsNone(report['summary']['caption_precision'])
        self.assertIn('Not qualified',content)


if __name__=='__main__':unittest.main()
