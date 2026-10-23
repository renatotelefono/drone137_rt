import copy
import json
from pathlib import Path
import tempfile
import unittest

from app.components import Components,validate_component


class ComponentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'parts.sqlite3';self.db=Components(self.path)
    def tearDown(self):self.temp.cleanup()

    def test_swaps_persist_and_existing_assemblies_pin_revisions(self):
        original=self.db.assemble('scout-110')
        c=copy.deepcopy(self.db.get('component','battery-500')['content']);c['mass_kg']=.1
        with self.assertRaises(ValueError):self.db.save('component',c,1)
        c.pop('mass_kg');c['parameters']['mass_kg']=.025
        self.db.save('component',c,1)
        self.assertEqual(self.db.assemble('scout-110'),original)
        cfg=copy.deepcopy(original['configuration']['content']);cfg['id']='heavy-scout';cfg['components']['battery']='battery-500@2'
        self.db.save('configuration',cfg,0)
        rebuilt=Components(self.path).assemble('heavy-scout')
        self.assertAlmostEqual(rebuilt['mass_kg']-original['mass_kg'],.011)
        self.assertFalse(rebuilt['physical_enabled'])
        with self.assertRaises(ValueError):self.db.save('component',c,1)

    def test_bad_chemistry_geometry_slots_and_unpinned_refs_rejected(self):
        cfg=self.db.get('configuration','micro-90')['content']
        for slot,ref in [('propulsion','motor-8520-65-hypothesis@1'),('battery','mpu6050@1'),('battery','battery-500')]:
            c=copy.deepcopy(cfg);c['components'][slot]=ref
            with self.assertRaises(ValueError):self.db.save('configuration',c,1)
        p=self.db.get('component','battery-500')['content'];p['parameters']['full_v']=4.35
        self.db.save('component',p,1);cfg['components']['battery']='battery-500@2'
        with self.assertRaises(ValueError):self.db.save('configuration',cfg,1)

    def test_every_parameter_has_evidence_and_invalid_curve_cannot_be_used(self):
        for c in self.db.list('component'):validate_component(c['content'])
        p=self.db.get('component','cf2-published-propulsion')['content']
        self.assertAlmostEqual(p['parameters']['curve'][-1][1],57.9*.00981/4,7)
        for edit in ('nonfinite','nonmonotonic','unsourced'):
            c=copy.deepcopy(p)
            if edit=='nonfinite':c['parameters']['mass_kg']=float('nan')
            elif edit=='nonmonotonic':c['parameters']['curve'][3][0]=0
            else:c['evidence']['curve']['source']=''
            with self.assertRaises(ValueError):validate_component(c)

    def test_frozen_experiment_integrity_and_nonoverwrite(self):
        trial=self.db.freeze('scout-110','nominal')
        c=self.db.get('configuration','scout-110')['content'];c['components']['battery']='pluto-600@1'
        self.db.save('configuration',c,1)
        self.assertEqual(trial['snapshot']['assembly']['configuration']['revision'],1)
        self.assertEqual(self.db.freeze('scout-110','nominal',2027)['snapshot']['seed'],2027)
        self.assertEqual(self.db.freeze('scout-110','nominal',dt_s=.002)['snapshot']['dt_s'],.002)
        with self.assertRaises(ValueError):self.db.freeze('scout-110','nominal',dt_s=.1)
        for invalid in (-1,4294967296,True,1.5):
            with self.assertRaises(ValueError):self.db.freeze('scout-110','nominal',invalid)
        with self.assertRaises(ValueError):self.db.record(trial['id'],{'trial_sha256':'bad'})
        gates={k:False for k in ('liftoff','hover','transit','landed','controlled_attitude','no_obstacle_contact','battery_valid','landing_speed','thrust_reserve')}
        result={'trial_sha256':trial['sha256'],'physical_enabled':True,'recognition_tested':True,'configuration':'scout-110',
                'scenario':'nominal','seed':137,'configuration_revision':1,'engine':'rapier-0.21.0','assembly_sha256':trial['snapshot']['assembly']['sha256'],
                'gates':gates,'flight_passed':False,'engineering_passed':False}
        with self.assertRaises(ValueError):self.db.record(trial['id'],{**result,'flight_passed':True})
        with self.assertRaises(ValueError):self.db.record(trial['id'],{**result,'seed':2027})
        with self.assertRaises(ValueError):self.db.record(trial['id'],{**result,'configuration_revision':2})
        self.db.record(trial['id'],result)
        with self.assertRaises(ValueError):self.db.record(trial['id'],{'trial_sha256':trial['sha256']})
        result=next(h['result'] for h in self.db.history() if h['id']==trial['id']);self.assertFalse(result['physical_enabled']);self.assertFalse(result['recognition_tested'])
        with self.db.connection() as conn:conn.execute("UPDATE revisions SET content='{}' WHERE type='component' AND id='battery-500' AND revision=1")
        with self.assertRaises(ValueError):self.db.assemble('scout-110@1')


class ComponentApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_write_guard_and_saved_configuration(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        from app.server import local_only
        from app.component_api import install
        with tempfile.TemporaryDirectory() as temp:
            app=web.Application(middlewares=[local_only]);db=Components(Path(temp)/'test.sqlite3');install(app,db)
            async with TestClient(TestServer(app)) as client:
                value=await (await client.get('/api/components')).json()
                self.assertEqual(len(value['assemblies']),len(db.list('configuration')))
                self.assertEqual(value['assemblies'][0]['propulsion_evidence'],'derived')
                body={'reference':'scout-110','scenario':'nominal'}
                self.assertEqual((await client.post('/api/components/freeze',json=body)).status,403)
                headers={'X-Drone137-Control':'local'}
                frozen=await (await client.post('/api/components/freeze',json=body,headers=headers)).json()
                self.assertIn('sha256',frozen)
                bad=await client.post('/api/components/freeze',json={**body,'scenario':'invalid'},headers=headers)
                self.assertEqual(bad.status,409)


if __name__=='__main__':unittest.main()
