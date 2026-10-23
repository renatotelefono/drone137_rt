import ast
import json
from pathlib import Path
import tempfile
import unittest

from app.place_memory import PlaceMemory


class TransitTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_ground_correction_cannot_be_reenabled_after_liftoff(self):
        from app.visual_inertial import VisualInertial,ROOT
        if not (ROOT/'.local/build/openvins/drone137_openvins').is_file():
            self.skipTest('Optional OpenVINS runtime is not built')
        calibration={'mount':{'pitch_degrees':0,'body_offset_flu_m':[.035,0,.015]},
                     'optics':{'fx':226.,'fy':226.,'cx':480.,'cy':270.,'width':960,'height':540,
                               'distortion':[-.025,0,0,0,0]}}
        with tempfile.TemporaryDirectory() as folder:
            vio=VisualInertial()
            try:
                await vio.start(calibration,folder,0,stationary_phase=True)
                for grounded in (True,False,True):
                    vio.process.stdin.write((json.dumps({'imu':[],'stationary_phase':grounded})+'\n').encode())
                    await vio.process.stdin.drain()
                    response=json.loads(await vio.process.stdout.readline())
                    if grounded is False:self.assertNotIn('error',response)
                self.assertIn('Cannot re-enable ground initialization',response['error'])
            finally:await vio.close()

    def test_initialization_requires_fresh_consistent_observations(self):
        from scripts.explore_unknown import initialization_ready
        quality={'time_s':10.,'tracks':50,'position_std_m':.05,
                 'position_disagreement_m':.02,'gravity_disagreement_deg':.1}
        self.assertTrue(initialization_ready(quality,10.1))
        for field,value in [('time_s',9.),('time_s',11.),('tracks',24),
                            ('position_std_m',.2),('position_disagreement_m',.2),
                            ('gravity_disagreement_deg',1.1),('position_std_m',float('nan'))]:
            self.assertFalse(initialization_ready(dict(quality,**{field:value}),10.1),(field,value))
        self.assertFalse(initialization_ready(None,10.1))

    def test_frontier_commitment_is_bounded_and_cannot_restore_a_rejected_route(self):
        from app.frontier_planner import choose_frontier
        far={'score':4.3,'path_distance_m':5.,'viewpoint':[-3.,3.], 'view_heading_rad':1.5}
        near={'score':4.,'path_distance_m':.6,'viewpoint':[.5,.2], 'view_heading_rad':.3}
        self.assertIs(choose_frontier([far,near],[0,0],0),near)
        self.assertIs(choose_frontier([far],[0,0],0),far)
        self.assertEqual(choose_frontier([dict(far,score=6.),near],[0,0],0)['score'],6.)
        self.assertIs(choose_frontier([far,dict(near,viewpoint=[-.5,0])],[0,0],0),far)
        self.assertIsNone(choose_frontier([],[0,0],0))

    async def test_blocked_sensing_step_tries_another_clear_baseline_but_tracking_loss_propagates(self):
        from types import SimpleNamespace
        from scripts.explore_unknown import translate_for_depth,MotionSegmentInvalid,ReplanAfterRecovery
        class Link:
            latest={'position':[0,0,1.5],'time_s':10}
            def __init__(self,error):self.error=error;self.calls=[]
            async def fly(self,goal):
                self.calls.append(goal)
                if len(self.calls)==1:raise self.error('Interrupted')
                self.latest={'position':goal[:3],'time_s':12}
        checked=[]
        def clear(a,b):checked.append(b);return True
        mapping=SimpleNamespace(segment_clear=clear);report={};link=Link(MotionSegmentInvalid)
        await translate_for_depth(link,mapping,0,1.5,report)
        self.assertEqual(len(link.calls),2)
        self.assertGreater(link.calls[0][1],0)
        self.assertLess(link.calls[1][1],0)
        self.assertEqual(len(checked),2)
        self.assertEqual(len(report['sensing_replans']),1)
        link=Link(ReplanAfterRecovery)
        with self.assertRaises(ReplanAfterRecovery):await translate_for_depth(link,mapping,0,1.5,{})
        self.assertEqual(len(link.calls),1)

    def test_panorama_covers_all_bearings_with_overlap_for_different_lenses(self):
        import math
        from scripts.explore_unknown import panorama
        for fov in (60,90,130):
            plan=panorama({'width':960,'optics':{'fx':480/math.tan(math.radians(fov/2))}})
            self.assertLessEqual(plan['step_degrees'],fov*.7)
        self.assertEqual(plan['views'],8)

    def test_temporarily_deferred_frontier_is_not_exhausted_exploration(self):
        from scripts.explore_unknown import eligible_views
        options=[{'viewpoint':[1,0]}];rejected=[{'point':[1,0],'until':15}]
        self.assertEqual(eligible_views(options,rejected,10),([],5))
        self.assertEqual(eligible_views(options,rejected,16),(options,None))
        self.assertEqual(eligible_views([],rejected,10),([],None))
        other={'viewpoint':[0,2]}
        self.assertEqual(eligible_views(options+[other],rejected,10),([other],None))

    async def test_intermediate_waypoint_keeps_motion_but_clearance_veto_still_stops_it(self):
        from scripts.explore_unknown import Link,ReplanAfterRecovery
        link=Link('http://127.0.0.1:8156')
        link.latest={'position':[.85,0,1.5],'velocity':[.5,0,0],'yaw':0,'failsafe':False,'tripped':False}
        link.guard=lambda a,b:True
        await link.fly([1,0,1.5,0],timeout=.2,settle=False)
        with self.assertRaises(TimeoutError):await link.fly([1,0,1.5,0],timeout=.1,settle=True)
        link.guard=lambda a,b:False
        with self.assertRaises(ReplanAfterRecovery):await link.fly([1,0,1.5,0],settle=False)
        self.assertEqual(link.goal,[.85,0,1.5,0])


class PlaceMemoryTests(unittest.TestCase):
    def test_object_retrieval_keeps_latest_mission_failure_even_without_new_captions(self):
        with tempfile.TemporaryDirectory() as d:
            db=PlaceMemory(Path(d)/'places.sqlite3')
            db.begin('room','Room','a'*32)
            db.observe('a'*32,1,b'image',{'observation':'A red extinguisher beside a door'})
            db.finish('a'*32,'complete',{})
            db.begin('room','Room','b'*32)
            db.finish('b'*32,'failed',{})
            db.record_evaluation('b'*32,{'accepted':False,'gates':{'coverage':False},
                'metrics':{},'protocol_sha256':'f'*64})
            data=db.context('room',question='Where was the extinguisher?')
            self.assertEqual(data['observations'][0]['visit'],'a'*8)
            self.assertEqual(data['latest_visit']['visit'],'b'*8)
            self.assertEqual(data['latest_visit']['independent_test'],'not_passed')
            self.assertEqual(data['latest_visit']['failed_checks'],['coverage'])

    def test_only_a_consistent_finished_evaluation_can_mark_a_visit_complete(self):
        with tempfile.TemporaryDirectory() as d:
            db=PlaceMemory(Path(d)/'places.sqlite3');visit='e'*32
            db.begin('room','Room',visit)
            score={'accepted':False,'gates':{'coverage':False},'metrics':{'coverage':.5},'protocol_sha256':'f'*64}
            with self.assertRaises(ValueError):db.record_evaluation(visit,score)
            db.finish(visit,'partial',{})
            db.record_evaluation(visit,score)
            record=db.recall('room')['visits'][0]
            self.assertEqual(record['state'],'partial')
            self.assertFalse(record['summary']['evaluation']['accepted'])
            score['accepted']=True
            with self.assertRaises(ValueError):db.record_evaluation(visit,score)
            score['gates']['coverage']=True
            db.record_evaluation(visit,score)
            self.assertEqual(db.recall('room')['visits'][0]['state'],'complete')

    def test_evidence_survives_reopen_and_partial_visit_is_not_complete(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'places.sqlite3'
            db=PlaceMemory(path);visit='a'*32
            db.begin('workshop','Workshop',visit)
            db.observe(visit,1,b'camera pixels',{'observation':'A shelf, uncertain contents'})
            db.save_map(visit,{'cells':[[1,2,-1,3]],'status':'partial'})
            db.finish(visit,'failed',{'error':'tracking lost'})
            loaded=PlaceMemory(path).recall('workshop')
            self.assertEqual(loaded['visits'][0]['state'],'failed')
            self.assertEqual(loaded['visits'][0]['map']['status'],'partial')
            self.assertEqual(len(loaded['visits'][0]['observations']),1)
            self.assertIn('relocalization',loaded['reuse_policy'])
            context=PlaceMemory(path).context('workshop')
            self.assertEqual(context['visits'][0]['mission_state'],'failed')
            self.assertEqual(context['observations'][0]['visual_observation'],'A shelf, uncertain contents')
            self.assertNotIn('map',context)
            with self.assertRaises(Exception):
                db.observe(visit,1,b'replacement',{})
            with self.assertRaises(KeyError):
                db.recall('another-place')

    def test_visits_keep_separate_maps_and_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            db=PlaceMemory(Path(d)/'places.sqlite3')
            for i in ('a','b'):
                db.begin('warehouse','Warehouse',i*32)
                db.observe(i*32,1,i.encode(),{'observation':i})
                db.save_map(i*32,{'cells':[i]})
            visits=db.recall('warehouse')['visits']
            self.assertEqual([v['map']['cells'] for v in visits],[['a'],['b']])

    def test_recall_finds_earlier_sighting_without_other_places_or_duplicate_captions(self):
        with tempfile.TemporaryDirectory() as d:
            db=PlaceMemory(Path(d)/'places.sqlite3')
            db.begin('workshop','Workshop','a'*32)
            db.begin('warehouse','Warehouse','b'*32)
            db.observe('a'*32,1,b'one',{'observation':'A red fire extinguisher beside a doorway'})
            for i in range(2,80):
                db.observe('a'*32,i,b'shelf',{'observation':'A grey shelf against a white wall'})
            db.observe('b'*32,1,b'other',{'observation':'A yellow fire extinguisher'})
            context=db.context('workshop',limit=1800,question='Where was the fire extinguisher?')
            self.assertEqual(context['observations'][0]['sequence'],1)
            self.assertEqual(len(context['observations']),2)
            self.assertNotIn('yellow',json.dumps(context))

    def test_controller_cannot_import_simulator_or_known_map_navigation(self):
        root=Path(__file__).resolve().parents[1]
        forbidden=('sim','adapters.rapier_drone','app.mission_navigation','app.mission_views')
        for name in ('scripts/explore_unknown.py','app/blind_mapping.py','app/place_memory.py',
                     'app/metric_mapping.py','app/visual_inertial.py','app/frontier_planner.py',
                     'app/voxel_mapping.py','app/temporal_geometry.py','app/planar_surfaces.py','app/breadcrumbs.py'):
            tree=ast.parse((root/name).read_text())
            for node in ast.walk(tree):
                modules=[node.module or ''] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names] if isinstance(node,ast.Import) else []
                self.assertFalse(any(m==f or m.startswith(f+'.') for m in modules for f in forbidden),name)


class GeometryTests(unittest.TestCase):
    def test_common_position_drift_does_not_look_like_lost_relative_tracking(self):
        import numpy as np
        from app.visual_inertial import displacement_std,tracking_faults
        common=np.eye(3)*.04;independent=np.eye(3)*.0001
        joint=np.block([[common+independent,common],[common,common+independent]])
        relative=displacement_std(joint)
        self.assertAlmostEqual(relative,np.sqrt(.0002))
        q={'stable_image_tracks':100,'position_std_m':[.201]*3,'velocity':[.5,0,0],
           'relative_position_std_m':relative,'relative_position_span_s':.9}
        self.assertEqual(tracking_faults(q,.2,True),[])
        self.assertTrue(tracking_faults(q,.2,False))
        q['relative_position_std_m']=displacement_std(np.eye(6)*.04)
        self.assertTrue(tracking_faults(q,.2,True))
        q['relative_position_std_m']=relative;q['stable_image_tracks']=3
        self.assertTrue(tracking_faults(q,.2,True))
        q['stable_image_tracks']=100
        self.assertTrue(tracking_faults(q,1.2,True))
        q['relative_position_std_m']=float('nan')
        self.assertTrue(tracking_faults(q,.2,True))
        with self.assertRaises(ValueError):displacement_std(-np.eye(6))

    def test_narrow_glimpse_of_floor_stays_worth_inspecting_without_granting_clearance(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        from app.frontier_planner import exploration_interest, candidates
        m=RaycastMap();x,y=(np.indices(m.logodds.shape)+.5)*m.resolution-m.extent
        launch=(x>-.8)&(x<1.1)&(np.abs(y)<.8)
        glimpse=(x>=1.1)&(x<2.5)&(np.abs(y)<.2)
        m.seen[launch|glimpse]=1;m.ground[launch|glimpse]=1
        m.logodds[launch]=-2;m.flight_clear[launch]=True
        before=m.voxels.copy();m.explored_views=[[.375,.075,0]]
        interest=exploration_interest(m)
        self.assertGreater(interest[m.cell([1.5,0])],0)
        options=candidates(m,[.375,.075],0)
        self.assertTrue(options)
        self.assertGreater(options[0]['viewpoint'][0],.6)
        self.assertTrue(m.segment_clear([.375,.075],options[0]['viewpoint']))
        self.assertFalse(m.clear([1.5,0]))
        np.testing.assert_array_equal(before,m.voxels)

    def test_overhead_surface_does_not_hide_a_view_at_camera_height(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        m=RaycastMap();c=m.cell([1,0]);m.voxels[c][16]=2
        empty=(np.array([],int),np.array([],int),np.empty((0,2),int),np.empty((0,3)))
        m.integrate_prepared(empty,np.array([0,0,1.5]),[0,0,1.5])
        self.assertFalse(m.visibility_obstacles[c])
        self.assertFalse(m.clear([1,0])) # visibility priority never certifies flight
        m.voxels[c][11]=2
        m.integrate_prepared(empty,np.array([.1,0,1.5]),[.1,0,1.5])
        self.assertTrue(m.visibility_obstacles[c])

    def test_measured_ceiling_outside_grid_still_supplies_free_rays_inside_grid(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        x,y=np.mgrid[2:5:.02,-1:1:.02]
        ceiling=np.c_[x.ravel(),y.ravel(),np.full(x.size,3.2)]
        m=RaycastMap()
        for offset in (0,.1,.2,.3):m.integrate_cloud(ceiling,[offset,0,1.5],[offset,0,1.5])
        self.assertLess(m.voxels[m.cell([.4,0])][11],-.6)
        self.assertFalse(m.clear([.4,0])) # upper rays alone do not clear the lower band
        self.assertFalse(np.any(m.logodds>.5)) # ceiling is not a floor-plan obstacle

    def test_distant_wall_requires_a_longer_camera_baseline(self):
        import cv2
        import numpy as np
        from app.temporal_geometry import TemporalGeometry
        from app.blind_mapping import camera_transform
        focal=540/(2*np.tan(np.radians(50)))
        cal={'width':960,'height':540,'vertical_fov_deg':100,
             'mount':{'pitch_degrees':0,'body_offset_flu_m':[0,0,0]},
             'optics':{'fx':focal,'fy':focal,'cx':480,'cy':270,'distortion':[0,0,0,0,0]}}
        rng=np.random.default_rng(891)
        texture=cv2.GaussianBlur(rng.integers(0,256,(2048,4096),dtype=np.uint8),(3,3),0)
        def frame(offset,time):
            pose={'position':[0,offset,1.5],'quaternion':[0,0,0,1],'time_s':time}
            tw,k=camera_transform(pose,cal)
            y,x=np.mgrid[:540,:960]
            rays=np.stack(((x-480)/focal,(y-270)/focal,np.ones_like(x)),axis=-1)@tw[:3,:3].T
            points=np.asarray(pose['position'])+rays*(6/rays[:,:,0])[:,:,None]
            im=cv2.remap(texture,np.float32(points[:,:,1]*100+2048),np.float32(points[:,:,2]*100+512),cv2.INTER_LINEAR)
            return cv2.imencode('.jpg',im)[1].tobytes(),pose
        g=TemporalGeometry()
        for offset,time in ((0,1),(.25,1.5)):
            im,pose=frame(offset,time);short=g.observe(im,pose,cal)[3]
        self.assertLess(len(short),20)
        im,pose=frame(.65,2)
        long=g.observe(im,pose,cal)[3]
        self.assertGreater(len(long),1000)
        self.assertLess(float(np.median(np.abs(long[:,0]-6))),.1)

    def test_repeated_view_does_not_award_clearance_or_discount_occluded_cells(self):
        from app.voxel_mapping import RaycastMap
        from app.frontier_planner import record_view_attempt
        m=RaycastMap();wall=m.cell([1,0])[0];m.visibility_obstacles[wall,:]=True
        record_view_attempt(m,[0,0,1.5],0)
        self.assertGreater(m.view_attempts[m.cell([.5,0])],0)
        self.assertEqual(m.view_attempts[m.cell([2,0])],0)
        self.assertFalse(m.clear([.5,0]))

    def test_frontier_planner_advances_for_a_closer_view_of_unresolved_passage(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        from app.frontier_planner import candidates
        m=RaycastMap();x,y=(np.indices(m.logodds.shape)+.5)*m.resolution-m.extent
        free=(x>-.8)&(x<1.1)&(np.abs(y)<.8)
        m.seen[free]=1;m.logodds[free]=-2;m.flight_clear[free]=True
        # Ground extends into a passage whose flight volume is still unknown.
        m.ground[(x>-.8)&(x<2.5)&(np.abs(y)<.8)]=1
        m.explored_views=[[.375,.075,0]]
        before=m.logodds.copy()
        options=candidates(m,[.375,.075],0)
        self.assertTrue(options)
        self.assertGreater(options[0]['viewpoint'][0],.6)
        self.assertTrue(m.segment_clear([.375,.075],options[0]['viewpoint']))
        np.testing.assert_array_equal(m.logodds,before)
        self.assertFalse(m.clear([1.5,0]))

    def test_view_priority_follows_observed_ground_but_does_not_certify_clearance(self):
        from app.voxel_mapping import RaycastMap
        from app.frontier_planner import exploration_interest
        m=RaycastMap();cell=m.cell([1,1]);x,y=cell
        m.ground[x-3:x+4,y-3:y+4]=2;m.seen[x-3:x+4,y-3:y+4]=2
        interest=exploration_interest(m)
        self.assertEqual(interest[cell],1)
        self.assertEqual(interest[m.cell([8,8])],0)
        self.assertFalse(m.clear([1,1]))
        m.logodds[cell]=-2;m.flight_clear[cell]=True
        self.assertEqual(exploration_interest(m)[cell],0)

    def test_visibility_ray_does_not_skip_a_nearby_wall(self):
        import numpy as np
        from app.frontier_planner import visibility_rewards
        occupied=np.zeros((80,80),bool);occupied[42,:]=True
        seen=np.zeros((80,80),int);seen[:42,:]=1
        logodds=np.zeros((80,80));logodds[:42,:]=-2
        _,rewards=visibility_rewards(occupied,seen,logodds,np.array([[40,40]]),.15)
        self.assertEqual(rewards[0,0],0)
        occupied[:]=False
        _,rewards=visibility_rewards(occupied,seen,logodds,np.array([[40,40]]),.15)
        self.assertGreater(rewards[0,0],10)

    def test_recorded_return_preserves_corners_and_rejects_new_obstacles(self):
        import numpy as np
        from app.breadcrumbs import Breadcrumbs
        from app.voxel_mapping import RaycastMap
        trail=Breadcrumbs()
        for x in np.arange(0,2,.1):trail.observe([x,0,1.5],0)
        for y in np.arange(0,2,.1):trail.observe([1.9,y,1.5],1.57)
        path=trail.route([1.9,1.9,1.5],1.57)
        self.assertGreater(len(path),3)
        for a,b in zip(path,path[1:]):
            self.assertTrue(abs(a[0]-b[0])<.06 or abs(a[1]-b[1])<.06)
        m=RaycastMap()
        self.assertTrue(m.recorded_segment_unobstructed([0,0],[1,0]))
        m.voxels[m.cell([.5,0])][10]=2
        self.assertFalse(m.recorded_segment_unobstructed([0,0],[1,0]))
        # Unknown space remains forbidden for an ordinary new route.
        self.assertFalse(m.segment_clear([0,1],[1,1]))

    def test_fine_grid_preserves_a_passable_doorway_without_opening_a_narrow_gap(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        for gap,expected in ((.9,True),(.3,False)):
            m=RaycastMap();m.seen[:]=1;m.logodds[:]=-2;m.flight_clear[:]=True
            for x in range(len(m.logodds)):
                for y in range(len(m.logodds)):
                    p=m.xy((x,y))
                    if abs(p[0])<.15 and abs(p[1])>gap/2:
                        m.logodds[x,y]=5;m.flight_clear[x,y]=False
            self.assertEqual(m.path([-1,0],[1,0]) is not None,expected)

    def test_plane_completion_stays_inside_support_and_respects_foreground(self):
        import numpy as np
        from app.planar_surfaces import complete_patches
        from app.blind_mapping import camera_transform
        cal={'width':320,'height':240,'vertical_fov_deg':60,
             'mount':{'pitch_degrees':0,'body_offset_flu_m':[0,0,0]}}
        tw,k=camera_transform({'position':[0,0,1.1],'quaternion':[0,0,0,1]},cal)
        old=tw.copy();old[1,3]=.3
        y,z=np.mgrid[-1:1:.07,.3:2:.07]
        support=np.c_[np.full(y.size,3),y.ravel(),z.ravel()]
        image=np.full((240,320),100,np.uint8)
        sparse=np.full(image.shape,np.nan,np.float32)
        filled=complete_patches(support,image,image,tw,old,k,sparse)
        self.assertGreater(len(filled),300)
        np.testing.assert_allclose(filled[:,0],3,atol=.001)
        self.assertTrue(np.all((filled[:,1]>-1)&(filled[:,1]<1)&(filled[:,2]>.3)&(filled[:,2]<2)))
        sparse[:]=1.5
        self.assertEqual(len(complete_patches(support,image,image,tw,old,k,sparse)),0)
        self.assertEqual(len(complete_patches(support,image,image+30,tw,old,k,np.full(image.shape,np.nan,np.float32))),0)

    def test_wall_completion_preserves_measured_background_through_opening(self):
        import numpy as np
        from app.planar_surfaces import complete_patches
        from app.blind_mapping import camera_transform
        cal={'width':320,'height':240,'vertical_fov_deg':60,
             'mount':{'pitch_degrees':0,'body_offset_flu_m':[0,0,0]}}
        tw,k=camera_transform({'position':[0,0,1.1],'quaternion':[0,0,0,1]},cal)
        old=tw.copy();old[1,3]=.3
        y,z=np.mgrid[-1:1:.07,.3:2:.07]
        support=np.c_[np.full(y.size,3),y.ravel(),z.ravel()]
        support=support[np.abs(support[:,1])>.35]
        # Same colour on near and far walls: photometry cannot veto bridging
        # the doorway. Sparse farther measurements must do so themselves.
        image=np.full((240,320),100,np.uint8)
        sparse=np.full(image.shape,np.nan,np.float32)
        sparse[65:160:3,143:178:3]=5
        filled=complete_patches(support,image,image,tw,old,k,sparse)
        self.assertGreater(len(filled),100)
        camera=(filled-tw[:3,3])@tw[:3,:3]
        uv=camera@k.T;uv=uv[:,:2]/uv[:,2,None]
        opening=(uv[:,0]>143)&(uv[:,0]<175)&(uv[:,1]>65)&(uv[:,1]<157)
        self.assertFalse(opening.any())

    def test_coplanar_wall_segments_do_not_fill_unmeasured_doorway_between_them(self):
        import numpy as np
        from app.planar_surfaces import near_measured_support
        y,z=np.mgrid[-2:2:.05,.2:2.6:.05]
        wall=np.c_[np.full(y.size,3),y.ravel(),z.ravel()]
        wall=wall[np.abs(wall[:,1])>.8]
        test=np.array([[3,0,1.5],[3,.2,1.5],[3,1,1.5],[3,-1.5,1.]])
        self.assertEqual(near_measured_support(test,np.array([1.,0,0]),wall).tolist(),[False,False,True,True])

    def test_floor_plan_clearance_is_not_flight_height_clearance(self):
        from app.voxel_mapping import RaycastMap
        m=RaycastMap();m.seen[:]=1;m.logodds[:]=-2
        self.assertFalse(m.clear([0,0]))
        m.flight_clear[:]=True
        self.assertTrue(m.clear([0,0]))
        m.flight_clear[m.cell([.1,.1])]=False
        self.assertFalse(m.clear([0,0]))

    def test_sparse_flight_height_rays_cannot_override_lower_obstacle_footprint(self):
        from app.voxel_mapping import RaycastMap
        m=RaycastMap();m.seen[:]=1;m.logodds[:]=2
        self.assertFalse(m.clear([0,0]))
        m.flight_clear[:]=True
        self.assertFalse(m.segment_clear([0,0],[1,0]))
        self.assertGreater(m.logodds[m.cell([0,0])],.5)
        m.flight_clear[m.cell([.5,0])]=False
        self.assertFalse(m.segment_clear([0,0],[1,0]))

    def test_visible_floor_alone_does_not_clear_a_flight_volume(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        x,y=np.mgrid[.3:3:.03,-1:1:.03]
        floor=np.c_[x.ravel(),y.ravel(),np.zeros(x.size)]
        mapping=RaycastMap()
        for offset in (0,.1,.2,.3):
            mapping.integrate_cloud(floor,np.array([offset,0,.3]),[offset,0,.3])
        self.assertGreater(np.count_nonzero(mapping.ground),0)
        self.assertFalse(np.any(mapping.logodds<-.3))

    def test_visible_floor_under_table_does_not_erase_the_table(self):
        import numpy as np
        from app.voxel_mapping import RaycastMap
        x,y=np.mgrid[1:1.5:.02,-.4:.4:.02]
        top=np.c_[x.ravel(),y.ravel(),np.ones(x.size)]
        ground=top.copy();ground[:,2]=0
        mapping=RaycastMap()
        for offset in (0,.1,.2,.3):
            origin=np.array([offset,0,1.5])
            mapping.integrate_cloud(np.concatenate((top,ground)),origin,origin)
        cell=mapping.cell([1.25,0])
        self.assertGreater(mapping.logodds[cell],.5)
        self.assertFalse(mapping.clear([1.25,0]))

    def test_image_parallax_recovers_plane_and_rotation_only_stays_unknown(self):
        import cv2
        import numpy as np
        from app.temporal_geometry import TemporalGeometry
        from app.blind_mapping import camera_transform
        focal=540/(2*np.tan(np.pi/6))
        cal={'width':960,'height':540,'vertical_fov_deg':60,
             'mount':{'pitch_degrees':-55,'body_offset_flu_m':[0,0,0]},
             'optics':{'fx':focal,'fy':focal,'cx':480,'cy':270,'distortion':[0,0,0,0,0]}}
        rng=np.random.default_rng(514)
        texture=cv2.GaussianBlur(rng.integers(0,256,(1024,1024),dtype=np.uint8),(3,3),0)
        def frame(position,time):
            pose={'position':position,'quaternion':[0,0,0,1],'time_s':time}
            tw,k=camera_transform(pose,cal)
            y,x=np.mgrid[:540,:960]
            r=np.stack(((x-480)/focal,(y-270)/focal,np.ones_like(x)),axis=-1)@tw[:3,:3].T
            p=np.asarray(position)+r*(-position[2]/r[:,:,2])[:,:,None]
            image=cv2.remap(texture,np.float32(p[:,:,0]*150+256),np.float32(p[:,:,1]*150+512),cv2.INTER_LINEAR)
            return cv2.imencode('.jpg',image)[1].tobytes(),pose
        geometry=TemporalGeometry();image,pose=frame([0,0,1.1],1)
        self.assertEqual(len(geometry.observe(image,pose,cal)[3]),0)
        pose['time_s']=1.2
        self.assertEqual(len(geometry.observe(image,pose,cal)[3]),0)
        image,pose=frame([0,.2,1.1],1.5)
        points=geometry.observe(image,pose,cal)[3]
        self.assertGreater(len(points),1000)
        self.assertLess(float(np.median(np.abs(points[:,2]))),.03)

    def test_raised_surface_is_not_projected_onto_floor_and_floor_cannot_erase_it(self):
        import numpy as np
        from app.blind_mapping import camera_transform
        from app.metric_mapping import SurfaceMap
        calibration={'height':120,'width':160,'vertical_fov_deg':60,
                     'mount':{'pitch_degrees':-55,'body_offset_flu_m':[0,0,0]}}
        pose={'position':[0,0,1.1],'quaternion':[0,0,0,1]}
        tw,k=camera_transform(pose,calibration)
        y,x=np.mgrid[:120,:160]
        rays=np.stack(((x-k[0,2])/k[0,0],(y-k[1,2])/k[1,1],np.ones_like(x)),axis=-1)@tw[:3,:3].T
        elevated=np.float32((.6-tw[2,3])/rays[:,:,2])
        mapping=SurfaceMap();mapping.integrate_surfaces(elevated,tw,k,pose['position'],[])
        raised=mapping.logodds>.5
        self.assertGreater(int(raised.sum()),4)
        floor=np.float32(-tw[2,3]/rays[:,:,2])
        for _ in range(10):mapping.integrate_surfaces(floor,tw,k,pose['position'],[])
        self.assertTrue(np.all(mapping.logodds[raised]>.5))

    def test_imu_camera_rotation_conversion_preserves_axes(self):
        import numpy as np
        from app.visual_inertial import quaternion
        from app.blind_mapping import camera_transform
        r=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
        q=quaternion(r)
        tw,_=camera_transform({'position':[0,0,0],'quaternion':q},
            {'height':120,'width':160,'vertical_fov_deg':60,'mount':{'pitch_degrees':0,'body_offset_flu_m':[.1,0,0]}})
        np.testing.assert_allclose(tw[:3,3],[0,.1,0],atol=1e-10)
        np.testing.assert_allclose(tw[:3,2],[0,1,0],atol=1e-10)

    def test_visual_gravity_gate_ignores_yaw_but_rejects_wrong_tilt(self):
        import math
        from app.visual_inertial import gravity_disagreement_degrees
        self.assertAlmostEqual(gravity_disagreement_degrees([0,0,0,1],[0,0,1,0]),0)
        tilt=math.radians(3)
        self.assertAlmostEqual(gravity_disagreement_degrees([0,0,0,1],
            [math.sin(tilt/2),0,0,math.cos(tilt/2)]),3)

    def test_camera_transform_is_rigid_and_unknown_is_not_free(self):
        try:
            import numpy as np
            from app.blind_mapping import camera_transform,ObservedMap
        except ImportError:
            self.skipTest('Optional mapping environment required')
        t,k=camera_transform({'position':[0,0,1],'quaternion':[0,0,0,1]},
          {'height':540,'width':960,'vertical_fov_deg':55,'mount':{'pitch_degrees':-10,'body_offset_flu_m':[.12,0,.02]}})
        np.testing.assert_allclose(t[:3,:3].T@t[:3,:3],np.eye(3),atol=1e-8)
        self.assertAlmostEqual(np.linalg.det(t[:3,:3]),1)
        m=ObservedMap()
        self.assertFalse(m.clear([0,0]))
        self.assertEqual(m.snapshot()['cells'],[])
        self.assertIsNone(m.choose([0,0,1],0))

    def test_depth_hallucination_cannot_clear_unobserved_floor(self):
        import numpy as np
        from app.blind_mapping import camera_transform,ObservedMap
        calibration={'height':120,'width':160,'vertical_fov_deg':60,
                     'mount':{'pitch_degrees':-55,'body_offset_flu_m':[0,0,0]}}
        tw,k=camera_transform({'position':[0,0,1],'quaternion':[0,0,0,1]},calibration)
        depth=np.ones((120,160),np.float32)
        mapping=ObservedMap()
        mapping.integrate(depth,tw,k,[0,0,1],np.zeros_like(depth))
        self.assertFalse(np.any(mapping.logodds < -.3))
        self.assertFalse(mapping.clear([0,0]))
        mask=np.ones_like(depth)
        mapping=ObservedMap()
        mapping.integrate(depth,tw,k,[0,0,1],mask)
        before=mapping.logodds.copy()
        # Changing the depth-model guess cannot move the observed floor footprint.
        other=ObservedMap()
        other.integrate(depth*9,tw,k,[0,0,1],mask)
        np.testing.assert_array_equal(before,other.logodds)

    def test_updated_margin_allows_only_observed_egress_away_from_obstacle(self):
        from app.blind_mapping import ObservedMap
        m=ObservedMap();m.seen[:]=1;m.logodds[:]=-2
        m.logodds[:,59]=5
        start=[0,.25]
        self.assertFalse(m.clear(start))
        self.assertTrue(m.segment_clear(start,[0,1]))
        self.assertFalse(m.segment_clear(start,[0,-.25]))
        path=m.path(start,[2,1])
        self.assertIsNotNone(path)
        self.assertEqual(path[0],start)
        self.assertTrue(all(p[1]>=start[1] for p in path))


class PlaceApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_place_scoping_and_model_receives_saved_evidence_only(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        from app.place_api import install
        from app.server import local_only
        class Model:
            async def text(self,prompt,schema,timeout):
                self.prompt=prompt
                return json.dumps({'answer':'A shelf was recorded in observation 1.','evidence':['E1']})
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'places.sqlite3';db=PlaceMemory(path)
            db.begin('workshop','Workshop','a'*32)
            db.observe('a'*32,1,b'pixels',{'sequence':1,'observation':'A shelf','image':'frame-0001.jpg','evidence_directory':'/outside/allowed/root'})
            model=Model();app=web.Application(middlewares=[local_only]);install(app,path,model)
            async with TestClient(TestServer(app)) as client:
                self.assertEqual((await client.get('/api/places/missing')).status,404)
                self.assertEqual((await client.get('/api/places/workshop/visits/'+'a'*32+'/images/1')).status,404)
                self.assertEqual((await client.post('/api/places/workshop/ask',json={'question':'What was seen?'})).status,403)
                r=await client.post('/api/places/workshop/ask',json={'question':'What was seen?'},headers={'X-Drone137-Control':'local'})
                self.assertEqual(r.status,200)
                self.assertEqual((await r.json())['evidence'][0]['visit'],'a'*32)
                self.assertIn('A shelf',model.prompt)
                self.assertNotIn('evidence_directory',model.prompt)
                self.assertNotIn('"cells"',model.prompt)


if __name__=='__main__':unittest.main()
