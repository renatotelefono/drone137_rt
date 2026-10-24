"""Enumerate voxel interiors crossed by measured free-space ray segments.

Fixed-distance point samples skip cells at oblique grid crossings. Advance to
each next grid plane instead, retaining the same near and surface exclusions.
A ray remains evidence from estimated image geometry, not a range sensor.
"""
import numpy as np


def traversed_voxels(points, origin, shape, voxel_size, offset):
    origin=np.asarray(origin,dtype=float)
    voxel_size=np.asarray(voxel_size,dtype=float)
    offset=np.asarray(offset,dtype=float)
    delta=np.asarray(points,dtype=float)-origin
    length=np.linalg.norm(delta,axis=1)
    valid=np.isfinite(delta).all(axis=1)&(length>.22)
    delta=delta[valid];length=length[valid]
    if not len(length):return np.array([],dtype=np.int64)
    direction=delta/length[:,None]
    limit=np.minimum(8.,length-.14)
    # The epsilon selects the interior when the near point is on a grid plane.
    cell=np.floor((origin+direction*(.08+1e-10)+offset)/voxel_size).astype(int)
    step=np.sign(direction).astype(int)
    boundary=(cell+(step>0))*voxel_size-offset
    tmax=np.divide(boundary-origin,direction,out=np.full_like(direction,np.inf),
                   where=np.abs(direction)>1e-12)
    tdelta=np.divide(voxel_size,np.abs(direction),out=np.full_like(direction,np.inf),
                     where=np.abs(direction)>1e-12)
    active=np.ones(len(length),dtype=bool);crossed=[]
    for _ in range(int(np.ceil(8*np.linalg.norm(1/voxel_size)))+3):
        inside=np.all((cell>=0)&(cell<shape),axis=1)
        ids=np.flatnonzero(active&inside)
        if len(ids):crossed.append(np.ravel_multi_index(cell[ids].T,shape))
        next_t=tmax.min(axis=1)
        active &= next_t<limit-1e-10
        if not active.any():break
        # At an edge/corner cross tied axes together: a zero-length touch is
        # not a ray through the neighbouring voxel's interior.
        axes=(tmax<=next_t[:,None]+1e-10)&active[:,None]
        cell+=step*axes
        tmax=np.where(axes,tmax+tdelta,tmax)
    else:
        raise RuntimeError('Free-space ray traversal exceeded its geometric bound')
    return np.unique(np.concatenate(crossed)) if crossed else np.array([],dtype=np.int64)
