"""Small 3D ray occupancy map, projected for the indoor mission planner."""
import numpy as np
from app.blind_mapping import ObservedMap


class RaycastMap(ObservedMap):
    def __init__(self):
        super().__init__(resolution=.15)
        self.z_resolution=.15
        self.voxels=np.zeros((*self.logodds.shape,20),np.float32)
        self.ground=np.zeros_like(self.logodds,np.uint16)
        self.previous_origin=None
        self.flight_clear=np.zeros_like(self.logodds,dtype=bool)
        self.semantic_views=[]
        self.visibility_obstacles=np.zeros_like(self.logodds,dtype=bool)
        self.view_attempts=np.zeros_like(self.logodds,dtype=np.uint8)

    def clear(self,p,radius=.2):
        # 0.20 m plus half a grid cell: provisional clearance around the
        # approximately 0.10 m guarded aircraft envelope, independently scored.
        # Sparse image rays can miss a small object above a tabletop. Retain
        # the lower obstacle footprint as well as the flight-height check.
        if not super().clear(p,radius=radius):return False
        c=self.cell(p);n=int(np.ceil(radius/self.resolution))
        return all(self.inside((c[0]+dx,c[1]+dy)) and self.flight_clear[c[0]+dx,c[1]+dy]
                   for dx in range(-n,n+1) for dy in range(-n,n+1)
                   if np.linalg.norm(np.array(self.xy((c[0]+dx,c[1]+dy)))-np.array(p[:2]))<=radius+self.resolution/2)

    def recorded_segment_unobstructed(self,start,end):
        """Veto fresh obstacles on a previously traversed trajectory only.

        This is not a clearance test for a new route through unknown space.
        """
        for f in np.linspace(0,1,max(3,int(np.linalg.norm(np.array(end[:2])-start[:2])/.06)+1)):
            p=np.array(start[:2])+f*(np.array(end[:2])-start[:2]);c=self.cell(p)
            for dx in range(-2,3):
                for dy in range(-2,3):
                    cell=(c[0]+dx,c[1]+dy)
                    if np.linalg.norm(np.array(self.xy(cell))-p)>.16+self.resolution/2:continue
                    if not self.inside(cell) or np.any(self.voxels[cell][10:12]>.8):return False
        return True

    def integrate_cloud(self,points,origin,position):
        self.integrate_prepared(self.prepare_cloud(points,origin),origin,position)

    def prepare_cloud(self,points,origin):
        """Compute ray evidence off the command/IMU event loop; no mutation."""
        if self.previous_origin is not None and np.linalg.norm(origin-self.previous_origin)<.08:return
        points=np.asarray(points)
        # A measured ceiling above the occupancy grid still supplies a valid
        # free ray through the flight volume below it. Do not discard the ray
        # just because its surface endpoint lies above the grid.
        valid=np.isfinite(points).all(axis=1)&(points[:,2]>-.15)&(points[:,2]<6)
        points=points[valid]
        if not len(points):return
        def indices(p):
            a=np.floor((p+np.array([self.extent,self.extent,.15]))/
                       np.array([self.resolution,self.resolution,self.z_resolution])).astype(int)
            valid=np.all((a>=0)&(a<self.voxels.shape),axis=-1)
            a=a[valid]
            return np.ravel_multi_index(a.T,self.voxels.shape)
        surface=indices(points)
        hits,count=np.unique(surface,return_counts=True)
        hits=hits[count>=2]
        delta=points-origin
        length=np.linalg.norm(delta,axis=1)
        # Free evidence is a ray through 3D space, not a 2D floor projection.
        steps=np.arange(.08,8,.1)
        distances=np.broadcast_to(steps[None,:],(len(points),len(steps)))
        safe=distances<(length[:,None]-.14)
        samples=origin+delta[:,None,:]/length[:,None,None]*distances[:,:,None]
        free=np.unique(indices(samples[safe]))
        free=np.setdiff1d(free,hits,assume_unique=True)
        ground=points[(points[:,2]>-.1)&(points[:,2]<.12)]
        cells=np.floor((ground[:,:2]+self.extent)/self.resolution).astype(int)
        cells=cells[np.all((cells>=0)&(cells<len(self.logodds)),axis=1)]
        if len(cells):
            cells,count=np.unique(cells,axis=0,return_counts=True)
            cells=cells[count>=3]
        return free,hits,cells,points[::30]

    def integrate_prepared(self,evidence,origin,position):
        current=self.cell(position)
        if self.inside(current):self.visits[current]=min(65535,int(self.visits[current])+1)
        if evidence is None:return
        self.previous_origin=np.asarray(origin).copy();self.frames+=1
        free,hits,cells,points=evidence
        flat=self.voxels.ravel()
        flat[free]=np.maximum(-5,flat[free]-.4)
        # Smaller cells need fewer image points per surface, but a surface now
        # needs corroboration from at least two translated camera observations.
        flat[hits]=np.minimum(5,flat[hits]+.7)
        if len(cells):
            self.ground[cells[:,0],cells[:,1]]=np.minimum(65535,self.ground[cells[:,0],cells[:,1]].astype(int)+1)
        # Raised surfaces are retained until a later 3D visibility ray actually
        # passes through their voxels. Seeing floor elsewhere cannot erase them.
        raised=np.max(self.voxels[:,:,3:12],axis=2)
        clear_band=np.all(self.voxels[:,:,6:10]<-.6,axis=2)
        self.flight_clear[:]=np.all(self.voxels[:,:,10:12]<-.6,axis=2)
        occupied=raised>.8
        # Rank forward views with occluders at camera/flight height. Projecting
        # every low shelf and overhead surface into this 2D mask incorrectly
        # hid views through openings. Actual navigation still independently
        # requires the full conservative footprint and clearance band below.
        self.visibility_obstacles[:]=np.any(self.voxels[:,:,10:12]>.8,axis=2)
        # Visible ground beneath a table does not prove the flight volume is
        # empty. Every vertical slice of the clearance band must be observed.
        free=clear_band
        self.logodds[:]=0
        self.logodds[free]=-2
        self.logodds[occupied]=raised[occupied]
        observed=free|occupied|(self.ground>0)
        self.seen[observed]=np.minimum(65535,self.seen[observed].astype(int)+1)
        for p in points:
            self.points[tuple(np.rint(p/.15).astype(int))]=[round(float(x),3) for x in p]
        if len(self.points)>20000:self.points=dict(list(self.points.items())[-20000:])

    def snapshot(self):
        result=super().snapshot()
        result.update(source='RGB multiview triangulation with 3D free-space rays; no scene map or depth buffer',
                      scale='Visual-inertial metric scale; provisional camera/IMU calibration',
                      voxel_height_m=self.z_resolution)
        result['navigation_clearance_height_m']=[1.35,1.65]
        result['navigation_free_cells']=np.argwhere(self.flight_clear & (self.logodds<-.3)).tolist()
        result['semantic_views']=list(self.semantic_views)
        return result
