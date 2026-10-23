"""Image-derived metric surfaces. Estimated depth never equals a range sensor."""
import io
import math
import cv2
import numpy as np
from app.blind_mapping import ObservedMap, camera_transform


class MetricDepth:
    def __init__(self, weights):
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        torch.set_num_threads(2)
        self.torch=torch
        self.device='mps' if torch.backends.mps.is_available() else 'cpu'
        self.processor=AutoImageProcessor.from_pretrained(weights,local_files_only=True,use_fast=False)
        self.model=AutoModelForDepthEstimation.from_pretrained(weights,local_files_only=True).to(self.device).eval()
        self.scale=None

    def observe(self,jpeg,pose,calibration,landmarks):
        from PIL import Image
        tw,k=camera_transform(pose,calibration)
        if pose['position'][2]<.9:
            # The close-up launch image is outside this room-depth model's
            # useful scale range. It remains useful for native feature tracking.
            return None,tw,k,{'usable':False,'reason':'Low launch/landing view; waiting for survey height'}
        rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
        lens=np.array(calibration['optics']['distortion'],np.float64)
        rgb=cv2.undistort(rgb,k,lens)
        with self.torch.inference_mode():
            inputs=self.processor(images=Image.fromarray(rgb),return_tensors='pt').to(self.device)
            raw=self.model(**inputs).predicted_depth
            raw=self.torch.nn.functional.interpolate(raw[:,None],size=rgb.shape[:2],mode='bicubic',align_corners=False)[0,0].cpu().numpy()
        quality={'scale_source':'previous visual triangulation','supports':0}
        if landmarks:
            uvd=np.array([p['uvd'] for p in landmarks])
            uv=cv2.undistortPoints(uvd[:,:2,None].transpose(0,2,1),k,lens,P=k).reshape(-1,2)
            x,y=np.rint(uv).astype(int).T
            good=(x>8)&(x<rgb.shape[1]-8)&(y>8)&(y<rgb.shape[0]-8)&(uvd[:,2]>.25)&(uvd[:,2]<8)
            x,y,metric=x[good],y[good],uvd[good,2]
            ratio=metric/np.maximum(.01,raw[y,x])
            if len(ratio)>=20:
                center=float(np.median(ratio))
                keep=np.abs(ratio/center-1)<.15
                # A low-scatter cluster can still be degenerate during pure
                # rotation. Never let it abruptly rescale a metric map.
                consistent=self.scale is None or abs(center/self.scale-1)<.2
                if sum(keep)>=20 and .1<center<4 and consistent:
                    scale=float(np.median(ratio[keep]))
                    self.scale=scale if self.scale is None else .8*self.scale+.2*scale
                    quality={'scale_source':'camera/IMU-triangulated landmarks','supports':int(sum(keep)),
                             'scale':self.scale,'relative_scatter':float(np.median(np.abs(ratio[keep]/scale-1)))}
        if self.scale is None:
            return None,tw,k,{'usable':False,'reason':'Waiting for metric visual landmarks'}
        quality.update(usable=True,scale=self.scale,range_source='learned RGB depth; approximate, independently scored')
        return np.clip(raw*self.scale,.05,12),tw,k,quality


class SurfaceMap(ObservedMap):
    """Project estimated 3D surfaces, never an assumed floor for raised objects.

    Ground observations can mark previously unknown cells free, but cannot
    erase a raised surface. Clearing a surface requires a ray at flight height.
    """
    def integrate_surfaces(self,depth,tw,k,position,landmarks):
        self.frames+=1
        origin=tw[:3,3]
        current=self.cell(position)
        if self.inside(current):self.visits[current]+=1
        if depth is None:return
        ys,xs=np.mgrid[6:depth.shape[0]-6:6,6:depth.shape[1]-6:6]
        d=depth[ys,xs].ravel()
        rays=np.c_[xs.ravel(),ys.ravel(),np.ones(xs.size)]@np.linalg.inv(k).T@tw[:3,:3].T
        points=origin+rays*d[:,None]
        # Image-depth edges are uncertain; do not interpolate across silhouettes.
        gradient=np.maximum(np.abs(cv2.Sobel(depth,cv2.CV_32F,1,0,ksize=3)),np.abs(cv2.Sobel(depth,cv2.CV_32F,0,1,ksize=3)))/np.maximum(depth,.1)
        good=(d>.15)&(d<5)&(gradient[ys,xs].ravel()<.25)&np.isfinite(points).all(axis=1)
        points=points[good]
        if landmarks:
            points=np.concatenate((points,np.array([item['point'] for item in landmarks])))
        self.integrate_cloud(points,origin,position,advance=False)

    def integrate_cloud(self,points,origin,position,advance=True):
        if advance:self.frames+=1
        current=self.cell(position)
        if self.inside(current):self.visits[current]+=1
        hits={self.cell(p) for p in points if .35<p[2]<1.65}
        ground={self.cell(p) for p in points if -.10<p[2]<.12}
        free=set()
        for p in points:
            if .9<p[2]<1.3 and np.linalg.norm(p[:2]-origin[:2])>.3:
                cells=self.line(self.cell(origin),self.cell(p))
                free.update(cells[:-2])
        for c in ground-hits:
            if self.inside(c) and self.logodds[c]<=0:
                self.logodds[c]=max(-5,self.logodds[c]-.5)
                self.seen[c]=min(65535,int(self.seen[c])+1)
        for c in free-hits:
            if self.inside(c):
                self.logodds[c]=max(-5,self.logodds[c]-.35)
                self.seen[c]=min(65535,int(self.seen[c])+1)
        for c in hits:
            if self.inside(c):
                self.logodds[c]=min(5,self.logodds[c]+1.2)
                self.seen[c]=min(65535,int(self.seen[c])+1)
        # The occupied aircraft itself establishes only its present footprint.
        if self.inside(current):self.logodds[current]=-5;self.seen[current]=max(1,int(self.seen[current]))
        for p in points[::12]:
            if -.15<p[2]<3.5:self.points[tuple(np.rint(p/.15).astype(int))]=[round(float(x),3) for x in p]
        if len(self.points)>20000:self.points=dict(list(self.points.items())[-20000:])

    def snapshot(self):
        result=super().snapshot()
        result['source']='Bidirectional RGB optical-flow triangulation using visual-inertial camera poses; no scene geometry or model depth'
        result['scale']='Camera/IMU visual-inertial metric scale; provisional calibration, unqualified on hardware'
        return result
