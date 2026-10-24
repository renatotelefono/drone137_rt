import unittest
import numpy as np
from app.voxel_rays import traversed_voxels


class VoxelRayTests(unittest.TestCase):
    shape=(200,200,20)
    size=np.array([.15,.15,.15])
    offset=np.array([15.,15.,.15])

    def ray(self,points,origin):
        return traversed_voxels(np.asarray(points,dtype=float),origin,self.shape,self.size,self.offset)

    def reference(self,point,origin):
        # Independent segment/AABB slab intersection over the bounded grid;
        # no traversal recurrence or distance samples from the implementation.
        direction=point-origin;length=np.linalg.norm(direction);direction/=length
        far=min(8.,length-.14)
        a=origin+direction*.08;b=origin+direction*far
        low=np.maximum(0,np.floor((np.minimum(a,b)+self.offset)/self.size).astype(int)-1)
        high=np.minimum(np.array(self.shape)-1,np.floor((np.maximum(a,b)+self.offset)/self.size).astype(int)+1)
        if np.any(low>high):return set()
        cells=np.stack(np.meshgrid(*[np.arange(l,h+1) for l,h in zip(low,high)],indexing='ij'),axis=-1).reshape(-1,3)
        lo=cells*self.size-self.offset;hi=lo+self.size
        ta=np.divide(lo-origin,direction,out=np.full_like(lo,-np.inf),where=np.abs(direction)>1e-12)
        tb=np.divide(hi-origin,direction,out=np.full_like(hi,np.inf),where=np.abs(direction)>1e-12)
        enter=np.maximum(.08,np.minimum(ta,tb).max(axis=1))
        leave=np.minimum(far,np.maximum(ta,tb).min(axis=1))
        parallel_ok=np.all((np.abs(direction)>1e-12)|((origin>=lo)&(origin<hi)),axis=1)
        keep=(leave-enter>1e-9)&parallel_ok
        return set(np.ravel_multi_index(cells[keep].T,self.shape).tolist())

    def test_oblique_axis_and_grid_exit_rays_match_independent_intersections(self):
        rng=np.random.default_rng(608)
        cases=[]
        for _ in range(40):
            origin=rng.uniform([-2,-2,.2],[2,2,2.8])
            direction=rng.normal(size=3);direction/=np.linalg.norm(direction)
            cases.append((origin,origin+direction*rng.uniform(.3,8.5)))
        origin=np.array([.075,.075,1.575])
        cases += [(origin,origin+d*1.5) for d in np.vstack([np.eye(3),-np.eye(3)])]
        for i,(origin,point) in enumerate(cases):
            with self.subTest(ray=i):
                self.assertEqual(set(self.ray([point],origin).tolist()),self.reference(point,origin))

    def test_surface_margin_is_never_cleared_and_duplicate_rays_count_once(self):
        origin=np.array([.075,.075,1.575]);point=origin+np.array([1.5,0,0])
        one=self.ray([point],origin);many=self.ray([point]*8,origin)
        np.testing.assert_array_equal(one,many)
        cells=np.array(np.unravel_index(one,self.shape)).T
        self.assertTrue(np.all(cells[:,0]<int(np.floor((point[0]+15)/.15))))
        self.assertFalse(np.any(cells[:,0]>110))

    def test_invalid_and_too_short_ranges_do_not_clear_space(self):
        origin=np.array([.075,.075,1.575])
        points=np.array([origin,origin+[.2,0,0],[np.nan,0,0],[np.inf,0,0]])
        self.assertEqual(len(self.ray(points,origin)),0)
