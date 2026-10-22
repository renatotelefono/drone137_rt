import copy
import unittest
from sim.hard_flight import build, cases, qualification
from sim.flight_world import HOME, VIEWS, route, segment_clear


class HardFlight(unittest.TestCase):
    def test_present_absent_pairs_share_all_non_target_geometry(self):
        specifications=cases()
        self.assertEqual(len(specifications),8)
        self.assertEqual(len({c['id'] for c in specifications}),8)
        for positive,negative in zip(specifications[::2],specifications[1::2]):
            a,b=build(positive),build(negative)
            target=next(p for p in a['obstacles'] if p['kind']=='extinguisher')
            self.assertEqual([target['x'],target['y']],positive['target_xy'])
            target_id=target['id']
            self.assertFalse(any(p['kind']=='extinguisher' for p in b['obstacles']))
            self.assertEqual([p for p in a['obstacles'] if p['id']!=target_id],
                             [p for p in b['obstacles'] if p['id']!=target_id])
            # Search poses are independent of target location and presence.
            self.assertNotIn('views',positive)
            self.assertNotIn('views',negative)

    def test_every_planned_route_is_feasible_in_shared_collision_geometry(self):
        for case in cases()[::2]:
            world=build(case);previous=HOME
            for destination in VIEWS+[HOME]:
                for point in route(world,previous,destination):
                    self.assertTrue(segment_clear(world,previous,point),case['id'])
                    previous=point

    def test_qualification_keeps_unexecuted_runs_and_rejects_resource_failures(self):
        run={'score':{'correct':True,'false_location_claim':False},'error':None,
             'landed':True,'flight':{'envelope_violations':0},'wall_time_s':100}
        report={'runs':[run],'memory':{'qwen+laya':{'budget_exceeded':False,'measurement_error':None}},'errors':[]}
        self.assertEqual(qualification(report,8)['pass_rate'],.125)
        self.assertFalse(qualification(report,8)['all_pass'])
        report['runs']=[copy.deepcopy(run) for _ in range(8)]
        self.assertTrue(qualification(report,8)['all_pass'])
        report['runs'][0]['flight']['envelope_violations']=1
        self.assertEqual(qualification(report,8)['qualified_passes'],7)
        report['memory']['qwen+laya']['budget_exceeded']=True
        self.assertEqual(qualification(report,8)['qualified_passes'],0)
        self.assertEqual(qualification(report,8)['task_correct'],8)
