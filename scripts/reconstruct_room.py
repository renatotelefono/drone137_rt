"""Offline RGB-D surface reconstruction into bounded, self-contained GLB.

Requires registered, rectified RGB/depth and measured camera poses in ENU. Does
not infer scale, fill unseen space or turn a few pictures into a surveyed room.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def reconstruct(specification,output):
    import numpy as np
    from PIL import Image
    spec=json.loads(specification.read_text());output.mkdir(parents=True,exist_ok=False)
    if not 1<=len(spec['frames'])<=64:raise ValueError('Use 1..64 registered frames per bounded reconstruction')
    camera=spec['camera'];step=spec.get('stride',8)
    if not isinstance(step,int) or not 4<=step<=32:raise ValueError('Stride must be 4..32')
    if camera.get('rectified') is not True:raise ValueError('Rectify/register RGB-D before reconstruction')
    vertices=[];colors=[];triangles=[];sources=[];offset=0
    for frame in spec['frames']:
        rgbpath=(specification.parent/frame['rgb']).resolve();depthpath=(specification.parent/frame['depth']).resolve()
        rgb=np.asarray(Image.open(rgbpath).convert('RGB'));depth=np.asarray(Image.open(depthpath),dtype=np.float64)*spec['depth_scale_m']
        if depth.ndim!=2 or rgb.shape[:2]!=depth.shape or depth.shape!=(camera['height'],camera['width']):raise ValueError('RGB/depth calibration dimensions disagree')
        if depth.size>1280*720 or not np.isfinite(depth).all():raise ValueError('Invalid/big depth image')
        pose=np.asarray(frame['camera_to_enu'],float)
        if pose.shape!=(4,4) or not np.isfinite(pose).all() or not np.allclose(pose[3],[0,0,0,1]) or not np.allclose(pose[:3,:3].T@pose[:3,:3],np.eye(3),atol=1e-5) or not np.isclose(np.linalg.det(pose[:3,:3]),1,atol=1e-5):raise ValueError('Camera pose must be a metric rigid transform')
        ys,xs=np.mgrid[0:depth.shape[0]:step,0:depth.shape[1]:step];z=depth[ys,xs]
        v=np.stack(((xs-camera['cx'])/camera['fx']*z,(ys-camera['cy'])/camera['fy']*z,z),axis=-1).reshape(-1,3)
        enu=np.einsum('ij,kj->ik',v,pose[:3,:3])+pose[:3,3];valid=(z>.15)&(z<spec.get('max_depth_m',6.))
        if not np.isfinite(enu).all():raise ValueError('Nonfinite reconstruction coordinates')
        gltf=np.column_stack((enu[:,0],enu[:,2],-enu[:,1])).astype('<f4')
        h,w=z.shape;faces=[]
        for row in range(h-1):
            for col in range(w-1):
                ids=[row*w+col,row*w+col+1,(row+1)*w+col,(row+1)*w+col+1]
                for f in ((ids[0],ids[2],ids[1]),(ids[1],ids[2],ids[3])):
                    zz=z.ravel()[list(f)]
                    if valid.ravel()[list(f)].all() and np.ptp(zz)<spec.get('max_depth_jump_m',.08):faces.append([i+offset for i in f])
        vertices.append(gltf);colors.append((rgb[ys,xs].reshape(-1,3)/255.)**2.2);triangles.extend(faces);offset+=len(gltf)
        sources.extend({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (rgbpath,depthpath))
        if len(triangles)>250000:raise ValueError('Triangle budget exceeded; increase stride or reduce frames')
    if not triangles:raise ValueError('No valid observed surface triangles')
    pos=np.concatenate(vertices).astype('<f4');col=np.concatenate(colors).astype('<f4');idx=np.asarray(triangles,dtype='<u4').ravel()
    chunks=[pos.tobytes(),col.tobytes(),idx.tobytes()];offsets=[0,len(chunks[0]),len(chunks[0])+len(chunks[1])]
    document={'asset':{'version':'2.0','generator':'drone137 bounded RGB-D reconstruction'},'extensionsUsed':['KHR_materials_unlit'],
      'buffers':[{'byteLength':sum(map(len,chunks))}],'bufferViews':[{'buffer':0,'byteOffset':o,'byteLength':len(c)} for o,c in zip(offsets,chunks)],
      'accessors':[{'bufferView':0,'componentType':5126,'count':len(pos),'type':'VEC3','min':pos.min(0).tolist(),'max':pos.max(0).tolist()},
                   {'bufferView':1,'componentType':5126,'count':len(col),'type':'VEC3'}, {'bufferView':2,'componentType':5125,'count':len(idx),'type':'SCALAR'}],
      'materials':[{'extensions':{'KHR_materials_unlit':{}},'doubleSided':True}],
      'meshes':[{'primitives':[{'attributes':{'POSITION':0,'COLOR_0':1},'indices':2,'material':0}]}],
      'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    j=json.dumps(document,separators=(',',':')).encode();j+=b' '*((-len(j))%4);b=b''.join(chunks);b+=b'\0'*((-len(b))%4)
    data=struct.pack('<4sII',b'glTF',2,12+8+len(j)+8+len(b))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(b),b'BIN\0')+b
    mesh=output/'room.glb';mesh.write_bytes(data)
    room=spec['room'];room.update(version=1,visual_glb='room.glb',visual_sha256=hashlib.sha256(data).hexdigest(),sources=sources,
        reconstruction={'triangles':len(triangles),'stride':step,'method':'Registered RGB-D surfaces; depth discontinuities rejected, no hole filling','unobserved_space':'Must be bounded as unknown_boxes before flight'})
    from sim.room_assets import validate_room,inspect_glb
    audit={**validate_room(room),**inspect_glb(data)};(output/'room.json').write_text(json.dumps(room,indent=2)+'\n');return audit


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(reconstruct(a.manifest,a.output)))
