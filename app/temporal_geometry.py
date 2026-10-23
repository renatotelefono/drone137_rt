"""Metric multiview geometry from RGB correspondences and estimated VIO poses."""
from collections import deque
import math
import cv2
import numpy as np
from app.blind_mapping import camera_transform
from app.planar_surfaces import complete_patches


class TemporalGeometry:
    def __init__(self):
        cv2.setNumThreads(2)
        self.frames=deque(maxlen=45)
        self.flow=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.flow.setUseSpatialPropagation(True)

    def observe(self,jpeg,pose,calibration,landmarks=()):
        tw,k=camera_transform(pose,calibration)
        image=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_GRAYSCALE)
        image=cv2.undistort(image,k,np.array(calibration['optics']['distortion'],np.float64))
        # Keep the recorded sensor resolution. Halving it discarded the
        # disparity precision needed to triangulate the room's upper walls.
        height,width=image.shape
        current={'image':image,'tw':tw,'time':pose['time_s']}
        choices=[]
        for old in self.frames:
            baseline=float(np.linalg.norm(tw[:3,3]-old['tw'][:3,3]))
            angle=math.acos(float(np.clip((np.trace(tw[:3,:3].T@old['tw'][:3,:3])-1)/2,-1,1)))
            if .12<baseline<.9 and angle<.4 and pose['time_s']-old['time']<5:
                choices.append((baseline/(1+angle*2),old))
        if not self.frames or pose['time_s']-self.frames[-1]['time']>.10:
            self.frames.append(current)
        depth=np.full(image.shape,np.nan,np.float32)
        if not choices:return depth,tw,k,np.empty((0,3)),{'points':0,'reason':'Waiting for camera translation'}
        _,old=max(choices,key=lambda item:item[0])
        homography=k@tw[:3,:3].T@old['tw'][:3,:3]@np.linalg.inv(k)
        warped=cv2.warpPerspective(old['image'],homography,(width,height))
        mask=cv2.warpPerspective(np.full(image.shape,255,np.uint8),homography,(width,height))
        forward=self.flow.calc(image,warped,None)
        backward=self.flow.calc(warped,image,None)
        stride=3
        ys,xs=np.mgrid[16:height-16:stride,16:width-16:stride]
        uv=np.c_[xs.ravel(),ys.ravel()].astype(np.float32)
        shift=forward[ys,xs].reshape(-1,2);other=uv+shift
        mx,my=other[:,0].reshape(xs.shape),other[:,1].reshape(xs.shape)
        back=cv2.remap(backward,mx,my,cv2.INTER_LINEAR).reshape(-1,2)
        valid_mask=cv2.remap(mask,mx,my,cv2.INTER_NEAREST).ravel()>254
        other_gray=cv2.remap(warped,mx,my,cv2.INTER_LINEAR).ravel()
        good=(np.linalg.norm(shift+back,axis=1)<.55)&valid_mask
        good&=(np.abs(other_gray.astype(float)-image[ys,xs].ravel())<20)
        # Optical flow interpolates across blank walls. A reversible flow on a
        # uniform patch is still unobservable, so require local 2D texture.
        texture=cv2.cornerMinEigenVal(image,blockSize=7,ksize=3)
        good&=texture[ys,xs].ravel()>1e-4
        def rays(p):
            r=np.c_[p,np.ones(len(p))]@np.linalg.inv(k).T@tw[:3,:3].T
            return r/np.linalg.norm(r,axis=1)[:,None]
        a,b=rays(uv),rays(other)
        base=old['tw'][:3,3]-tw[:3,3]
        cosine=np.einsum('ij,ij->i',a,b)
        den=1-cosine*cosine
        d1,d2=a@base,b@base
        t=np.divide(d1-cosine*d2,den,out=np.zeros_like(den),where=den>1e-8)
        u=np.divide(cosine*d1-d2,den,out=np.zeros_like(den),where=den>1e-8)
        p=tw[:3,3]+a*t[:,None];q=old['tw'][:3,3]+b*u[:,None]
        uncertainty=t/(k[0,0]*np.sqrt(np.maximum(den,1e-12)))*.5
        good&=(t>.2)&(t<8)&(u>.2)&(den>math.sin(math.radians(1))**2)
        good&=(np.linalg.norm(p-q,axis=1)<.025)&(uncertainty<.16)
        points=(p[good]+q[good])/2
        camera=(points-tw[:3,3])@tw[:3,:3]
        depth[ys.ravel()[good],xs.ravel()[good]]=camera[:,2]
        # The estimator's motion can be well constrained while individual
        # landmark depths are not. Only uncertainty-gated stereo points may
        # anchor a surface; do not treat every VIO landmark as measured range.
        patches=complete_patches(points,image,old['image'],tw,old['tw'],k,depth)
        points=np.concatenate((points,patches))
        return depth,tw,k,points,{'points':int(sum(good)),'baseline_m':float(np.linalg.norm(base)),
                                 'plane_patch_points':len(patches),
                                 'median_range_uncertainty_m':float(np.median(uncertainty[good])) if sum(good) else None,
                                 'source':'Bidirectional image optical flow + estimated visual-inertial camera motion'}
