"""Check closed printable meshes and record volume, not material qualification."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,struct
import numpy as np

root=Path(__file__).parent/'mechanics';results=[]
for p in sorted(root.glob('*.stl')):
 raw=p.read_bytes()
 if raw.startswith(b'solid'):
  vertices=[list(map(float,line.split()[1:])) for line in raw.decode().splitlines() if line.strip().startswith('vertex ')]
  faces=np.array(vertices).reshape(-1,3,3)
 else:
  count=struct.unpack('<I',raw[80:84])[0];faces=np.array([struct.unpack('<12fH',raw[84+i*50:134+i*50])[3:12] for i in range(count)]).reshape(-1,3,3)
 keys=[tuple(tuple(round(float(v),4) for v in point) for point in f) for f in faces];edges=Counter();adj=defaultdict(list)
 for i,f in enumerate(keys):
  for a,b in zip(f,(*f[1:],f[0])):edges[tuple(sorted((a,b)))]+=1;adj[a].append(b);adj[b].append(a)
 remaining=set(adj);components=0
 while remaining:
  components+=1;stack=[remaining.pop()]
  while stack:
   for q in adj[stack.pop()]:
    if q in remaining:remaining.remove(q);stack.append(q)
 volume=abs(float(np.einsum('ij,ij->i',faces[:,0],np.cross(faces[:,1],faces[:,2])).sum()/6))
 bad=sum(n!=2 for n in edges.values());assert bad==0 and components==1,(p.name,bad,components)
 results.append(dict(file=p.name,sha256=hashlib.sha256(raw).hexdigest(),triangles=len(faces),nonmanifold_edges=bad,connected_components=components,bounds_mm=[faces.min(axis=(0,1)).tolist(),faces.max(axis=(0,1)).tolist()],solid_volume_mm3=volume,solid_PETG_mass_g_estimate=volume/1000*1.27))
report=dict(status='mesh_checks_passed',scope='Nominal geometry only; print fit, flex, actual mass, wire routing and material properties unmeasured',models=results,total_solid_PETG_mass_g_estimate=sum(r['solid_PETG_mass_g_estimate'] for r in results))
(root/'mesh-checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
