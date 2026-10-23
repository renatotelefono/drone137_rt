"""Camera-only learned geometry and sparse visual odometry. No sim imports.

Metric depth is an uncertain learned prior, never a depth sensor. A map remains
partial until an independent evaluator or real survey establishes coverage.
"""
import heapq
import math
import numpy as np
import cv2


def camera_transform(pose, calibration):
    x, y, z, w = pose['quaternion']
    r = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                  [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                  [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    pitch = math.radians(calibration['mount']['pitch_degrees'])
    # Camera right/down/forward expressed in aircraft FLU coordinates.
    body = np.array([[0, math.sin(pitch), math.cos(pitch)], [-1, 0, 0], [0, -math.cos(pitch), math.sin(pitch)]])
    t = np.eye(4)
    t[:3, :3] = r @ body
    t[:3, 3] = np.asarray(pose['position']) + r @ np.asarray(calibration['mount']['body_offset_flu_m'])
    fy = calibration['height']/(2*math.tan(math.radians(calibration['vertical_fov_deg'])/2))
    k = np.array([[fy, 0, calibration['width']/2], [0, fy, calibration['height']/2], [0, 0, 1.]])
    if calibration.get('optics'):
        o=calibration['optics']
        k=np.array([[o['fx'],0,o['cx']],[0,o['fy'],o['cy']],[0,0,1.]])
    return t, k


class LaunchFloorAppearance:
    """Fit a floor-appearance hypothesis from the low launch image, not a palette.

    Requires a clear, level launch patch. This is not a geometric proof that a
    matching surface is traversable; the physical test separately scores errors.
    A new material stays unknown unless subsequent observations identify it.
    """
    def __init__(self):
        self.mean=self.precision=self.minimum_texture=None

    @staticmethod
    def features(rgb):
        rgb=np.float32(rgb)/255
        mean=cv2.GaussianBlur(rgb,(9,9),0)
        chroma=mean/(np.sum(mean,axis=2,keepdims=True)+.01)
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        texture=[]
        for k in (7,15,31):
            avg=cv2.blur(gray,(k,k))
            std=np.sqrt(np.maximum(0,cv2.blur(gray*gray,(k,k))-avg*avg))
            texture.append(std/(avg+.05))
        return chroma[:,:,:2],np.maximum.reduce(texture)

    def infer(self, rgb, height):
        chroma,texture=self.features(rgb)
        if self.mean is None:
            if not .1<height<.4:
                raise ValueError('Floor appearance must start from a low launch-camera observation')
            h,w=texture.shape
            roi=(slice(int(h*.4),int(h*.9)),slice(int(w*.15),int(w*.85)))
            samples=chroma[roi].reshape(-1,2)
            self.mean=np.median(samples,axis=0)
            self.precision=np.linalg.inv(np.cov(samples.T)+np.eye(2)*.00001)
            self.minimum_texture=float(np.quantile(texture[roi],.05))*.4
            if self.minimum_texture<.008:
                raise ValueError('Launch patch lacks usable visual texture')
        delta=chroma-self.mean
        distance=np.einsum('...i,ij,...j->...',delta,self.precision,delta)
        mask=np.uint8((distance<9)&(texture>self.minimum_texture))
        return cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((15,15),np.uint8)).astype(np.float32)


class ImageGeometry:
    def __init__(self, weights):
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        torch.set_num_threads(2)
        self.torch = torch
        self.device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        self.processor = AutoImageProcessor.from_pretrained(weights, local_files_only=True, use_fast=False)
        self.model = AutoModelForDepthEstimation.from_pretrained(weights, local_files_only=True).to(self.device).eval()
        self.floor_appearance=LaunchFloorAppearance()
        self.orb = cv2.ORB_create(nfeatures=1800, fastThreshold=12)
        self.previous = None

    def observe(self, jpeg, pose, calibration):
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(jpeg)).convert('RGB')
        torch = self.torch
        with torch.inference_mode():
            inputs = self.processor(images=im, return_tensors='pt').to(self.device)
            out = self.model(**inputs).predicted_depth
            depth = torch.nn.functional.interpolate(out.unsqueeze(1), size=im.size[::-1], mode='bicubic', align_corners=False).squeeze().cpu().numpy()
        floor_prob=self.floor_appearance.infer(np.asarray(im),pose['position'][2])
        floor_mask = cv2.erode(np.uint8(floor_prob > .85), np.ones((7,7),np.uint8))
        depth = np.clip(depth, .15, 12)
        gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
        keys, desc = self.orb.detectAndCompute(gray, floor_mask*255)
        tw, k = camera_transform(pose, calibration)
        vo = {'valid': False, 'inliers': 0, 'reason': 'Insufficient floor feature correspondences'}
        if self.previous and desc is not None and self.previous['desc'] is not None:
            prev = self.previous
            matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(prev['desc'], desc, k=2)
            pairs = [a for pair in matches if len(pair) == 2 for a, b in [pair] if a.distance < .7*b.distance]
            if len(pairs) >= 30:
                src = np.array([prev['keys'][m.queryIdx].pt for m in pairs])
                dst = np.array([keys[m.trainIdx].pt for m in pairs])
                rays=np.column_stack((src,np.ones(len(src))))@np.linalg.inv(k).T
                world_rays=rays@prev['tw'][:3,:3].T
                # The launch floor is the sole geometric prior. Its scale is
                # initialized by the short IMU takeoff, not by scene coordinates.
                dep=-prev['tw'][2,3]/world_rays[:,2]
                xyz=rays*dep[:,None]
                ok, rv, tv, inside = cv2.solvePnPRansac(xyz, dst, k, None, iterationsCount=100, reprojectionError=2.5, confidence=.999)
                if ok and inside is not None and len(inside) >= 25:
                    # Gyro supplies orientation. Re-fitting rotation in planar
                    # PnP and then discarding it couples rotation error into scale.
                    # Solve camera translation with the measured rotation fixed.
                    ids=inside[:,0]
                    world_points=xyz[ids]@prev['tw'][:3,:3].T+prev['tw'][:3,3]
                    current_rays=np.column_stack((dst[ids],np.ones(len(ids))))@np.linalg.inv(k).T@tw[:3,:3].T
                    current_rays/=np.linalg.norm(current_rays,axis=1)[:,None]
                    projectors=np.eye(3)[None,:,:]-current_rays[:,:,None]*current_rays[:,None,:]
                    center=np.linalg.solve(projectors.sum(0),np.einsum('nij,nj->i',projectors,world_points))
                    recovered=tw.copy()
                    recovered[:3,3]=center
                    delta = recovered[:3, 3]-tw[:3, 3]
                    position = (np.asarray(pose['position'])+delta).tolist()
                    interval=pose['time_s']-prev['time_s']
                    velocity=(np.asarray(position)-prev['body_position'])/max(.01,interval)
                    vo = {'valid': bool(float(np.linalg.norm(delta)) < .6 and np.linalg.norm(velocity)<1.5), 'inliers': len(inside), 'position': position,
                          'velocity':velocity.tolist(),
                          'correction_m': float(np.linalg.norm(delta)), 'reason': 'RANSAC floor-feature PnP; launch-plane scale from initial IMU ascent'}
                    if vo['valid']:
                        tw[:3,3]=recovered[:3,3]
        # Floor appearance is fitted from the onboard launch image, never renderer IDs.
        # Ground-plane intersection provides scale; learned depth is context only.
        ys,xs=np.mgrid[0:depth.shape[0]:6,0:depth.shape[1]:6]
        floor_rays=np.column_stack((xs.ravel(),ys.ravel(),np.ones(xs.size)))@np.linalg.inv(k).T@tw[:3,:3].T
        valid=(floor_mask[ys,xs].ravel()>0)&(floor_rays[:,2]<-.2)
        heights=(-floor_rays[:,2]*depth[ys,xs].ravel())[valid]
        heights=heights[heights>.05]
        if len(heights)>50:
            h=float(np.median(heights));scatter=float(np.median(np.abs(heights-h))/h)
            scale=float(tw[2,3]/h)
            if scatter<.2 and .1<scale<5:
                depth=depth*scale
                vo['depth_scale']=scale
                vo['floor_scatter']=scatter
        vo['floor_fraction']=float(np.mean(floor_mask))
        self.previous = {'keys': keys, 'desc': desc, 'depth': depth, 'tw': tw.copy(), 'time_s':pose['time_s'], 'body_position':np.asarray(pose['position'])+tw[:3,3]-camera_transform(pose,calibration)[0][:3,3]}
        return depth, tw, k, vo, floor_prob


class ObservedMap:
    def __init__(self, resolution=.25, extent=15):
        self.resolution, self.extent = resolution, extent
        n = round(extent*2/resolution)
        self.logodds = np.zeros((n, n), np.float32)
        self.seen = np.zeros((n, n), np.uint16)
        self.visits = np.zeros((n, n), np.uint16)
        self.points = {}
        self.frames = 0

    def cell(self, p):
        return (int(math.floor((p[0]+self.extent)/self.resolution)), int(math.floor((p[1]+self.extent)/self.resolution)))

    def xy(self, c):
        return [(c[0]+.5)*self.resolution-self.extent, (c[1]+.5)*self.resolution-self.extent]

    def inside(self, c):
        return all(0 <= x < len(self.logodds) for x in c)

    def line(self, a, b):
        steps = max(abs(b[0]-a[0]), abs(b[1]-a[1]), 1)
        return list(dict.fromkeys((round(a[0]+(b[0]-a[0])*i/steps), round(a[1]+(b[1]-a[1])*i/steps)) for i in range(steps+1)))

    def integrate(self, depth, tw, k, position, floor_probability):
        self.frames += 1
        origin = tw[:3, 3]
        current=self.cell(position)
        if self.inside(current): self.visits[current] += 1
        floor=np.uint8(floor_probability>.85)
        # Erosion provides a pixel uncertainty margin at object edges.
        safe=cv2.erode(floor,np.ones((9,9),np.uint8))
        ys,xs=np.mgrid[0:depth.shape[0]:4,0:depth.shape[1]:4]
        rays=np.column_stack((xs.ravel(),ys.ravel(),np.ones(xs.size)))@np.linalg.inv(k).T@tw[:3,:3].T
        down=rays[:,2]<-.15
        lengths=np.divide(-origin[2],rays[:,2],out=np.zeros(len(rays)),where=down)
        points=origin+rays*lengths[:,None]
        valid=down&(lengths>.05)&(lengths<5)&(safe[ys,xs].ravel()>0)
        free_cells={self.cell(p) for p in points[valid]}
        for c in free_cells:
            if self.inside(c):
                self.logodds[c]=max(-5,self.logodds[c]-.6)
                self.seen[c]=min(65535,int(self.seen[c])+1)
        # An observed floor/non-floor edge is a possible obstruction footpoint.
        # Image borders and low-confidence segmentation transitions stay unknown.
        inner=floor-cv2.erode(floor,np.ones((3,3),np.uint8))
        # Texture speckles are uncertain pixels, not obstacle boundaries.
        # Keep connected non-floor regions large enough to be structural edges.
        count,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(floor_probability<.15))
        keep=np.zeros(count,np.uint8)
        gy,gx=np.mgrid[:depth.shape[0],:depth.shape[1]]
        world_z=origin[2]+depth*((gx-k[0,2])/k[0,0]*tw[2,0]+(gy-k[1,2])/k[1,1]*tw[2,1]+tw[2,2])
        for label in range(1,count):
            if stats[label,cv2.CC_STAT_AREA]>max(250,depth.size*.002):
                # Flat changes in floor appearance (paint/shadows) must not
                # become walls. Depth only vetoes a proposed obstacle here.
                keep[label]=np.percentile(world_z[labels==label],90)>.25
        other=keep[labels]
        # Only a lower silhouette edge adjoining observed floor is a possible
        # contact boundary. Side/top occlusion edges are not ground contacts.
        boundary=floor*np.roll(other,2,axis=0)
        boundary[:2]=0
        boundary[:12]=0;boundary[-12:]=0;boundary[:,:12]=0;boundary[:,-12:]=0
        by,bx=np.where(boundary)
        br=np.column_stack((bx[::4],by[::4],np.ones(len(bx[::4]))))@np.linalg.inv(k).T@tw[:3,:3].T
        if len(br):
            dist=np.divide(-origin[2],br[:,2],out=np.zeros(len(br)),where=br[:,2]<-.15)
            bp=origin+br*dist[:,None]
            occupied={self.cell(p) for p in bp[(dist>.1)&(dist<5)]}
            for c in occupied:
                if self.inside(c):
                    self.logodds[c]=min(5,self.logodds[c]+.8)
                    self.seen[c]=min(65535,int(self.seen[c])+1)
        # Predicted 3D geometry is retained for review, never used to clear space.
        d=depth[ys,xs].ravel()
        geometry=origin+rays*d[:,None]
        for p in geometry[::30]:
            if np.isfinite(p).all() and -.1<p[2]<3.5 and np.linalg.norm(p-origin)<7:
                self.points[tuple(np.rint(p/.2).astype(int))]=[round(float(x),3) for x in p]
        if len(self.points)>20000:self.points=dict(list(self.points.items())[-20000:])

    def clear(self, p, radius=.38):
        c = self.cell(p)
        n = math.ceil(radius/self.resolution)
        for dx in range(-n, n+1):
            for dy in range(-n, n+1):
                if math.dist(self.xy((c[0]+dx,c[1]+dy)),p[:2]) > radius+self.resolution/2:
                    continue
                t = c[0]+dx, c[1]+dy
                if not self.inside(t) or self.seen[t] == 0 or self.logodds[t] >= -.3:
                    return False
        return True

    def clearance(self, p):
        # Distance to a blocking cell center, matching clear()'s grid margin.
        c=self.cell(p);n=math.ceil(1.25/self.resolution)
        blockers=[math.dist(p[:2],self.xy((x,y))) for x in range(c[0]-n,c[0]+n+1) for y in range(c[1]-n,c[1]+n+1)
                  if not self.inside((x,y)) or not self.seen[x,y] or self.logodds[x,y]>=-.3]
        return min(blockers,default=1.25)

    def segment_clear(self, start, end):
        # New observations can expand an obstacle's uncertainty margin around a
        # stationary aircraft. Permit egress only through observed free cells,
        # with physical clearance and monotonically increasing separation.
        previous=self.clearance(start)
        escaping=not self.clear(start)
        for f in np.linspace(0,1,max(3,math.ceil(math.dist(start[:2],end[:2])/.1)+1)):
            p=[start[0]+f*(end[0]-start[0]),start[1]+f*(end[1]-start[1])]
            distance=self.clearance(p)
            if self.clear(p):escaping=False
            elif not escaping or not self.clear(p,radius=.12) or distance+1e-6<previous:
                return False
            previous=distance
        return self.clear(end)

    def choose(self, pose, heading):
        p = pose[:2]
        candidates = []
        for angle in np.arange(0, 2*math.pi, math.pi/8):
            for distance in (.5, .8, 1.1):
                q = [p[0]+distance*math.cos(angle), p[1]+distance*math.sin(angle)]
                cells = self.line(self.cell(p), self.cell(q))
                if not self.segment_clear(p,q):
                    continue
                c = self.cell(q)
                n = 5
                section = self.seen[max(0,c[0]-n):c[0]+n+1, max(0,c[1]-n):c[1]+n+1]
                revisit = sum(int(self.visits[t]) for t in cells)
                novelty = float(np.mean(section == 0))
                turn = abs(math.atan2(math.sin(angle-heading), math.cos(angle-heading)))
                score = 4*novelty+distance-1.4*revisit-.8*turn
                candidates.append((score, [*q, 1.1, float(angle)]))
        return max(candidates, key=lambda x:x[0])[1] if candidates else None

    def path(self, start, end):
        a, b = self.cell(start), self.cell(end)
        queue, costs, parent = [(0, a)], {a: 0}, {}
        while queue:
            _, c = heapq.heappop(queue)
            if c == b:
                route = [c]
                while c != a:
                    c = parent[c]
                    route.append(c)
                route=list(reversed(route))
                return [list(start[:2])]+[self.xy(c) for c in route[1:-1]]+[list(end[:2])]
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                t = c[0]+dx, c[1]+dy
                cost = costs[c]+1
                point=self.xy(t) if t!=b else end[:2]
                previous=start[:2] if c==a else self.xy(c)
                safe=self.clear(point) or (not self.clear(previous) and self.clear(point,radius=.12) and self.clearance(point)>=self.clearance(previous))
                if not self.inside(t) or not safe or cost >= costs.get(t, math.inf):
                    continue
                costs[t], parent[t] = cost, c
                heapq.heappush(queue, (cost+math.dist(t,b), t))
        return None

    def snapshot(self):
        return {'frame': 'launch-local ENU', 'scale': 'learned monocular metric prior + synthetic IMU, uncalibrated on hardware',
                'resolution_m': self.resolution, 'extent_m': self.extent, 'frames': self.frames,
                'cells': [[int(x),int(y),round(float(self.logodds[x,y]),2),int(self.seen[x,y])] for x,y in np.argwhere(self.seen > 0)],
                'points': list(self.points.values()), 'status': 'partial; unknown is not free',
                'source': 'Launch-image appearance hypothesis + observed ground-plane projection; depth is visualization only; no simulator geometry or range sensor'}
