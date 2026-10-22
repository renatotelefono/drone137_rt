import math
import unittest
from app.inspection_planner import observed_viewpoints


class ObservedInspectionContracts(unittest.TestCase):
    def snapshot(self, occluder=False):
        cell=.2;nx=60;ny=50;grid=[1]*(nx*ny);safe=[]
        for i in range(len(grid)):
            x,y=(i%nx+.5)*cell,(i//nx+.5)*cell
            dx=max(4.3-x,0,x-5.5);dy=max(6.7-y,0,y-7.8)
            if occluder and dx==dy==0:grid[i]=2
            if .6<x<11.4 and .6<y<9.4 and (not occluder or math.hypot(dx,dy)>.6):safe.append(i)
        return {'grid':grid,'safe':safe,'width_cells':nx,'height_cells':ny,'cell_m':cell}

    def test_looks_around_observed_box_without_using_scene_labels(self):
        position=[4,5.5,1.5];target=[4.8,8.5,.6]
        views=observed_viewpoints(self.snapshot(True),position,{'xyz_m':target})
        self.assertTrue(views)
        for view in views:
            p=view['pose'];self.assertLessEqual(math.dist(p[:2],position[:2]),3.5)
            self.assertGreaterEqual(math.dist(p[:2],target[:2]),1.5)
            self.assertLessEqual(abs(p[2]-position[2]),.300001)
            origin=[p[0]+.12*math.cos(p[3]),p[1]+.12*math.sin(p[3])]
            # Independent geometric check at three slices through the blocker.
            for y in (6.8,7.2,7.7):
                t=(y-origin[1])/(target[1]-origin[1]) if target[1]!=origin[1] else -1
                if 0<t<1:
                    x=origin[0]+t*(target[0]-origin[0])
                    self.assertFalse(4.3<x<5.5,(p,x,y))

    def test_can_look_into_unknown_space_but_cannot_route_through_it(self):
        snapshot=self.snapshot();nx=snapshot['width_cells']
        barrier={y*nx+30 for y in range(snapshot['height_cells'])}
        snapshot['safe']=[i for i in snapshot['safe'] if i not in barrier]
        for i in barrier:snapshot['grid'][i]=0
        views=observed_viewpoints(snapshot,[4,5.5,1.5],{'xyz_m':[7.5,8.5,.6]})
        self.assertTrue(views)
        self.assertTrue(all(v['pose'][0]<6 for v in views))
        self.assertTrue(any(v['unknown_sightline_fraction']>0 for v in views))

    def test_no_reachable_station_and_invalid_geometry_fail_closed(self):
        snapshot=self.snapshot();snapshot['safe']=[]
        self.assertEqual(observed_viewpoints(snapshot,[4,5.5,1.5],{'xyz_m':[4.8,8.5,.6]}),[])
        with self.assertRaises(ValueError):
            observed_viewpoints(snapshot,[4,5.5,1.5],{'xyz_m':[float('nan'),8.5,.6]})


if __name__=='__main__':unittest.main()
