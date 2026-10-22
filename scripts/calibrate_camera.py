"""Offline checkerboard calibration with reserved-view reprojection checks.

Uses an optional calibration environment; OpenCV is not a flight dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path


def fit(manifest_path, output):
    import cv2
    import numpy as np
    spec=json.loads(manifest_path.read_text());columns,rows=spec['board_inner_corners'];square=spec['square_size_m']
    if not (3<=columns<=20 and 3<=rows<=20 and .001<=square<=.2):raise ValueError('Invalid measured board dimensions')
    points=np.zeros((rows*columns,3),np.float32);points[:,:2]=np.mgrid[0:columns,0:rows].T.reshape(-1,2)*square
    groups={'fit':[],'check':[]};seen=set();size=None;sources=[]
    for item in spec['images']:
        path=(manifest_path.parent/item['path']).resolve();data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if digest in seen:raise ValueError('Duplicate calibration image')
        seen.add(digest)
        if item['split'] not in groups:raise ValueError('Use fit/check split fixed before calibration')
        im=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_GRAYSCALE)
        if im is None:raise ValueError('Cannot decode '+str(path))
        if size is not None and size!=im.shape[::-1]:raise ValueError('Mixed camera resolution')
        size=im.shape[::-1]
        ok,corners=cv2.findChessboardCornersSB(im,(columns,rows),flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not ok:raise ValueError('Board not detected: '+str(path))
        groups[item['split']].append(corners.astype(np.float32));sources.append({'path':str(path),'sha256':digest,'split':item['split']})
    if len(groups['fit'])<10 or len(groups['check'])<3:raise ValueError('Need at least 10 fit and 3 reserved check views')
    rms,k,dist,rv,tv=cv2.calibrateCamera([points]*len(groups['fit']),groups['fit'],size,None,None)
    errors=[]
    for corners in groups['check']:
        ok,r,t=cv2.solvePnP(points,corners,k,dist)
        if not ok:raise ValueError('Reserved-view pose failed')
        pred,_=cv2.projectPoints(points,r,t,k,dist)
        errors.append(float(np.sqrt(np.mean(np.sum((pred-corners)**2,axis=2)))))
    result={'version':1,'camera_id':spec['camera_id'],'source_kind':spec.get('source_kind','unspecified'),
            'intrinsics':{'width':size[0],'height':size[1],'fx':float(k[0,0]),'fy':float(k[1,1]),'cx':float(k[0,2]),'cy':float(k[1,2]),'distortion':dist.ravel().tolist()},
            'fit_reprojection_rms_px':rms,'reserved_reprojection_rms_px':errors,'reserved_gate_px':spec.get('maximum_reprojection_px',1.),
            'passed':max(errors)<=spec.get('maximum_reprojection_px',1.),'sources':sources,'opencv':cv2.__version__,
            'limitations':'Intrinsics only at these settings. Mount/timing/exposure require separate measurement; reserved poses are fitted, intrinsics are frozen.'}
    output.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Output must be new')
    r=fit(a.manifest,a.output);print(json.dumps({k:r[k] for k in ('passed','fit_reprojection_rms_px','reserved_reprojection_rms_px')}))
    raise SystemExit(0 if r['passed'] else 1)
