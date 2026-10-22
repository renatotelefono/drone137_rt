import unittest
from adapters.vision_reviewer import accepts_caption
from sim.hard_flight import qualification
from scripts.build_flight_review import episode_passes


class ReviewerContracts(unittest.TestCase):
    def test_class_name_without_negation_required(self):
        self.assertTrue(accepts_caption('A red fire extinguisher with a black handle.'))
        for caption in ('A red container with a lid.', 'Not a fire extinguisher.',
                        'Possibly a fire extinguisher.', 'No fire extinguisher is visible.',
                        'The object is uncertain.', 'A fire-extinguisher might be present.'):
            self.assertFalse(accepts_caption(caption),caption)

    def test_good_recognition_cannot_mask_failed_rotor_check(self):
        r={'score':{'correct':True,'false_location_claim':False},'error':None,'landed':True,
           'flight':{'envelope_violations':0},'wall_time_s':90,'physical_checks':{'all_pass':False}}
        report={'runs':[r],'memory':{'qwen':{'budget_exceeded':False,'measurement_error':None}},'errors':[]}
        self.assertEqual(qualification(report,1)['qualified_passes'],0)
        report['qualification']=qualification(report,1)
        self.assertFalse(episode_passes(r,report))
        r['physical_checks']['all_pass']=True
        self.assertTrue(episode_passes(r,report))
        report['qualification']['memory_ok']=False
        self.assertFalse(episode_passes(r,report))

if __name__=='__main__':unittest.main()
