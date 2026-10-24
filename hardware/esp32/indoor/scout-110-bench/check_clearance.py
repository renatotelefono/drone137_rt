"""Nominal rigid mesh/rotor slab separation; excludes intended motor shafts.

This is a geometry check, not a measurement of blade flex or printed tolerance.
"""
from pathlib import Path
import json,math,hashlib
import numpy as np
root=Path(__file__).parent/'mechanics'
placements={'scout-frame-a':(0,0,0),'electronics-bridge-a':(0,0,7),'camera-cradle-a':(0,8,23),'imu-tray-a':(0,-7,23),'battery-cradle-a':(0,0,-12)}
a=110/(2*math.sqrt(2));rotors=np.array([[a,a],[a,-a],[-a,-a],[-a,a]])
def cross2(a,b):return float(a[0]*b[1]-a[1]*b[0])
def clip(poly,z,above):
 out=[]
 for p,q in zip(poly,poly[1:]+poly[:1]):
  p_in=p[2]>=z if above else p[2]<=z;q_in=q[2]>=z if above else q[2]<=z
  if p_in:out.append(p)
  if p_in!=q_in:out.append(p+(q-p)*(z-p[2])/(q[2]-p[2]))
 return out
checks=[]
for name,offset in placements.items():
 raw=(root/(name+'.stl')).read_text();vertices=[list(map(float,line.split()[1:])) for line in raw.splitlines() if line.strip().startswith('vertex ')]
 faces=np.array(vertices).reshape(-1,3,3)+offset;minimum=float('inf')
 for face in faces:
  poly=clip(clip(list(face),11,True),13,False)
  if not poly:continue
  for center in rotors:
   # A disk center inside a projected face also intersects it, even when
   # every edge is far away (for example a broad horizontal plate).
   cross=[cross2(q[:2]-p[:2],center-p[:2]) for p,q in zip(poly,poly[1:]+poly[:1])]
   area=sum(cross2(p[:2],q[:2]) for p,q in zip(poly,poly[1:]+poly[:1]))
   if abs(area)>1e-8 and (all(v>=-1e-8 for v in cross) or all(v<=1e-8 for v in cross)):
    minimum=min(minimum,-32.5)
   for p,q in zip(poly,poly[1:]+poly[:1]):
    delta=q[:2]-p[:2];den=delta@delta;t=float(np.clip((center-p[:2])@delta/den,0,1)) if den>0 else 0
    minimum=min(minimum,float(np.linalg.norm(p[:2]+t*delta-center))-32.5)
 assert minimum>=1.,(name,minimum)
 checks.append({'part':name,'mesh_sha256':hashlib.sha256((root/(name+'.stl')).read_bytes()).hexdigest(),'minimum_radial_margin_in_rotor_z11_to13_mm':None if not math.isfinite(minimum) else minimum,'passed':True})
report={'passed':True,'scope':'Rigid STL surfaces against a 65 mm rotor disk expanded vertically to Z=11–13 mm. No actual blade flex, shaft alignment, wiring or print tolerance measurement.','checks':checks}
(root/'rotor-clearance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
