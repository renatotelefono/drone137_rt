"""Conservative plane patches supported by triangulated image features.

This fills textureless interiors, not unseen extensions of a wall or tabletop.
Every added point must lie inside a measured support hull and agree with the
second camera image. Planarity remains an explicit reconstruction assumption.
"""
import cv2
import numpy as np


def supported_planes(points):
    points=np.asarray(points,dtype=float)
    if len(points)<30:return []
    points=points[np.isfinite(points).all(axis=1)&(points[:,2]>.25)&(points[:,2]<6)]
    if len(points)<30:return []
    # Balance sampling so a dense small image patch cannot dominate a fit.
    _,ids=np.unique(np.rint(points/.04).astype(int),axis=0,return_index=True)
    points=points[ids];planes=[]
    if len(points)<20:return []
    remaining=points.copy()
    for _ in range(4):
        zbin=np.rint(remaining[:,2]/.04).astype(int)
        values,counts=np.unique(zbin,return_counts=True)
        if not len(values) or counts.max()<15:break
        z=values[np.argmax(counts)]*.04
        support=remaining[np.abs(remaining[:,2]-z)<.035]
        z=float(np.median(support[:,2]))
        support=remaining[np.abs(remaining[:,2]-z)<.025]
        remaining=remaining[np.abs(remaining[:,2]-z)>=.035]
        if len(support)>=20 and np.ptp(support[:,0])>.35 and np.ptp(support[:,1])>.35:
            planes.append((np.array([0.,0.,1.]),z,support))
    remaining=points.copy();rng=np.random.default_rng(137)
    for _ in range(5):
        if len(remaining)<25:break
        pairs=rng.integers(0,len(remaining),(60,2))
        delta=remaining[pairs[:,1],:2]-remaining[pairs[:,0],:2]
        normals=np.c_[-delta[:,1],delta[:,0]]
        lengths=np.linalg.norm(normals,axis=1)
        valid=lengths>.4
        if not valid.any():break
        normals=normals[valid]/lengths[valid,None]
        offsets=np.sum(normals*remaining[pairs[valid,0],:2],axis=1)
        errors=np.abs(remaining[:,:2]@normals.T-offsets)
        counts=(errors<.025).sum(axis=0);best=int(np.argmax(counts))
        if counts[best]<25:break
        support=remaining[errors[:,best]<.025]
        remaining=remaining[errors[:,best]>=.04]
        tangent=np.array([-normals[best,1],normals[best,0]])
        if np.ptp(support[:,2])<.35 or np.ptp(support[:,:2]@tangent)<.4:continue
        planes.append((np.r_[normals[best],0.],float(offsets[best]),support))
    return planes


def near_measured_support(points,normal,support,radius=.35):
    """Limit planar interpolation in metres, including holes inside the hull.

    A convex hull joins disjoint wall segments across doorways. Proximity to
    actual triangulated support prevents an unmeasured opening being filled
    merely because there are coplanar features on both sides of it.
    """
    tangent=np.array([1.,0.,0.]) if abs(normal[2])>.9 else np.array([-normal[1],normal[0],0.])
    basis=np.c_[tangent,np.cross(normal,tangent)]
    uv=support@basis;query=points@basis
    resolution=.05;lower=uv.min(axis=0)-radius-.1
    shape=np.ceil((uv.max(axis=0)+radius+.1-lower)/resolution).astype(int)+1
    indices=np.floor((uv-lower)/resolution).astype(int)
    grid=np.ones(tuple(shape),np.uint8);grid[indices[:,0],indices[:,1]]=0
    distance=cv2.distanceTransform(grid,cv2.DIST_L2,cv2.DIST_MASK_PRECISE)*resolution
    cells=np.floor((query-lower)/resolution).astype(int)
    inside=np.all((cells>=0)&(cells<shape),axis=1)
    result=np.zeros(len(query),bool)
    result[inside]=distance[cells[inside,0],cells[inside,1]]<=radius
    return result


def complete_patches(points, image, old_image, tw, old_tw, k, sparse_depth):
    height,width=image.shape
    y,x=np.mgrid[12:height-12:3,12:width-12:3]
    uv=np.c_[x.ravel(),y.ravel()]
    rays=np.c_[uv,np.ones(len(uv))]@np.linalg.inv(k).T@tw[:3,:3].T
    avg=cv2.blur(image.astype(np.float32),(7,7))
    variance=cv2.blur(image.astype(np.float32)**2,(7,7))-avg**2
    # Measured depth vetoes completion on either side of a discontinuity.
    # Foreground protects objects; background protects openings inside a wall's
    # convex support hull. Photometric agreement alone cannot distinguish two
    # similarly coloured walls at different depths.
    foreground=cv2.erode(np.nan_to_num(sparse_depth,nan=1e6),np.ones((15,15),np.uint8))
    background=cv2.dilate(np.nan_to_num(sparse_depth,nan=0),np.ones((15,15),np.uint8))
    added=[]
    for normal,offset,support in supported_planes(points):
        camera=(support-tw[:3,3])@tw[:3,:3]
        camera=camera[camera[:,2]>.1]
        if len(camera)<20:continue
        projected=camera@k.T;projected=projected[:,:2]/projected[:,2,None]
        hull=cv2.convexHull(projected.astype(np.float32))
        if cv2.contourArea(hull)<600:continue
        mask=np.zeros(image.shape,np.uint8)
        cv2.fillConvexPoly(mask,np.rint(hull).astype(np.int32),1)
        # No expansion beyond the support hull: even a plausible plane is not
        # evidence about a doorway or an unseen object outside that hull.
        mask=cv2.erode(mask,np.ones((7,7),np.uint8))
        denominator=rays@normal
        distance=np.divide(offset-tw[:3,3]@normal,denominator,
                           out=np.full(len(rays),np.nan),where=np.abs(denominator)>.1)
        world=tw[:3,3]+rays*distance[:,None]
        previous=(world-old_tw[:3,3])@old_tw[:3,:3]
        projected=previous@k.T
        old_uv=projected[:,:2]/np.maximum(projected[:,2,None],.001)
        other=cv2.remap(old_image,old_uv[:,0].astype(np.float32).reshape(y.shape),
                       old_uv[:,1].astype(np.float32).reshape(y.shape),cv2.INTER_LINEAR).ravel()
        good=(mask[y,x].ravel()>0)&(variance[y,x].ravel()<20)
        good&=(distance>.2)&(distance<8)&(previous[:,2]>.2)
        good&=(old_uv[:,0]>12)&(old_uv[:,0]<width-12)&(old_uv[:,1]>12)&(old_uv[:,1]<height-12)
        good&=np.abs(other.astype(float)-image[y,x].ravel())<6
        good&=distance<=foreground[y,x].ravel()+.06
        good&=distance>=background[y,x].ravel()-.12
        if good.any():
            candidates=world[good]
            candidates=candidates[near_measured_support(candidates,normal,support)]
            if len(candidates):added.append(candidates)
    return np.concatenate(added) if added else np.empty((0,3))
