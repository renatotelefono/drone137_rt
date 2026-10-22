"""Frozen room packages: independent render mesh, surveyed collisions and provenance."""
import hashlib
import json
import math
from pathlib import Path
import struct


def inspect_glb(data):
    if len(data)>128*1024**2 or len(data)<20:raise ValueError('Room GLB must fit the 128 MiB asset budget')
    magic,version,length=struct.unpack_from('<4sII',data)
    if magic!=b'glTF' or version!=2 or length!=len(data):raise ValueError('Invalid GLB header')
    n,kind=struct.unpack_from('<I4s',data,12)
    if kind!=b'JSON' or 20+n>len(data):raise ValueError('Invalid GLB JSON chunk')
    gltf=json.loads(data[20:20+n]);triangles=0
    if gltf.get('animations') or gltf.get('skins'):raise ValueError('Room mesh must be static')
    if any(b.get('uri') for b in gltf.get('buffers',[])) or any(i.get('uri') for i in gltf.get('images',[])):
        raise ValueError('Room GLB must embed all buffers/textures; external resources are not allowed')
    for mesh in gltf.get('meshes',[]):
        for p in mesh['primitives']:
            if p.get('mode',4)!=4:raise ValueError('Use triangle geometry')
            index=p.get('indices',p['attributes'].get('POSITION'))
            count=gltf['accessors'][index]['count'];triangles+=count//3
    if not 1<=triangles<=250000:raise ValueError('Room mesh must contain 1..250000 triangles')
    return {'triangles':triangles,'bytes':len(data)}


def validate_room(room):
    if room.get('version')!=1 or room.get('source_kind') not in ('real-capture','public-reconstruction','synthetic-fixture'):raise ValueError('Declare room source_kind')
    if not isinstance(room.get('provenance'),str) or len(room['provenance'])<10:raise ValueError('Room provenance required')
    dimensions=room['dimensions_m']
    if len(dimensions)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 2<=v<=40 for v in dimensions):raise ValueError('Invalid room dimensions')
    if room.get('coordinate_frame')!='ENU-metres; GLB is x=east,y=up,z=south':raise ValueError('Room coordinate convention must be explicit')
    boxes=room['collision_boxes']+room['unknown_boxes']
    if not boxes:raise ValueError('Surveyed collision/unknown regions required; a visual scan is not a free-space map')
    for b in boxes:
        if set(b)!={'x','y','sx','sy','bottom','height'} or any(type(v) not in (int,float) or not math.isfinite(v) for v in b.values()):raise ValueError('Invalid collision box')
        if min(b['sx'],b['sy'],b['height'])<=0 or b['bottom']<0 or b['bottom']+b['height']>dimensions[2]:raise ValueError('Invalid collision dimensions')
        if b['x']-b['sx']/2<0 or b['y']-b['sy']/2<0 or b['x']+b['sx']/2>dimensions[0] or b['y']+b['sy']/2>dimensions[1]:raise ValueError('Collision outside room bounds')
    checks=room.get('control_points',[])
    if len(checks)<3:raise ValueError('At least three surveyed alignment control points required')
    errors=[]
    for check in checks:
        a,b=check['mesh_enu_m'],check['measured_enu_m']
        if len(a)!=3 or len(b)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in a+b):raise ValueError('Invalid control point')
        errors.append(math.dist(a,b))
    if max(errors)>.05:raise ValueError('Room/control-point alignment exceeds 5 cm')
    return {'alignment_max_m':max(errors),'control_points':len(checks),'physical_agreement_verified':False,
            'interpretation':'Checks supplied control-point coordinates. Independent survey and reserved photographs still require review.'}


def load_room(path):
    path=Path(path).resolve();r=json.loads(path.read_text());audit=validate_room(r)
    asset=(path.parent/r['visual_glb']).resolve()
    if asset.parent!=path.parent:raise ValueError('Room mesh must be inside its package')
    data=asset.read_bytes()
    if hashlib.sha256(data).hexdigest()!=r['visual_sha256']:raise ValueError('Room mesh checksum changed')
    return r,asset,{**audit,**inspect_glb(data)}


def attach_room(world,package):
    import copy
    r,asset,audit=load_room(package)
    if r['dimensions_m']!=[12,10,3]:raise ValueError('Current native challenge uses a 12 × 10 × 3 m operating volume; crop/align the room package to that volume')
    result=copy.deepcopy(world)
    # Keep only the separately authored movable target/decoys. The captured room
    # must have these removed before reconstruction to prevent baked duplicates.
    result['obstacles']=[b for b in result['obstacles'] if b['kind'] in ('extinguisher','red-canister') and not b.get('detail')]
    for i,b in enumerate(r['collision_boxes']+r['unknown_boxes']):
        result['obstacles'].append({**b,'id':f'room-solid-{i}','kind':'scan-collision','render_hidden':True})
    result['fixtures']=[]
    result['room_asset']={'path':str(asset),'url':'/room.glb','sha256':r['visual_sha256'],'source_kind':r['source_kind'],'provenance':r['provenance'],'audit':audit}
    result['complexity']['props']=len(result['obstacles'])
    result['complexity']['imported_instances']=sum('asset' in b for b in result['obstacles'])
    return result
