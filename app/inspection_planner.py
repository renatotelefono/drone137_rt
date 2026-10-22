"""Viewpoint hypotheses from an observed range map and estimated image rays only."""
from collections import deque
import math


def observed_viewpoints(snapshot, position, location, camera=None):
    """Find reachable camera stations with no known blocker before the candidate.

    Unknown cells along a sightline are uncertainty, not obstacles or verified
    visibility. Vehicle routes use only inflated observed-free cells. This
    function never authorizes recognition and receives no simulator world data.
    """
    grid=snapshot['grid'];safe=set(snapshot['safe']);nx=snapshot['width_cells'];ny=snapshot['height_cells'];cell=snapshot['cell_m']
    target=location['xyz_m']
    if any(not math.isfinite(v) for v in [*position,*target]):raise ValueError('Nonfinite inspection geometry')
    def index(x,y):
        if not (0<=x<nx*cell and 0<=y<ny*cell):return None
        return int(y/cell)*nx+int(x/cell)
    start=index(*position[:2])
    if start not in safe:return []
    reached={start};queue=deque([start])
    while queue:
        i=queue.popleft();x,y=i%nx,i//nx
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
            j=(y+dy)*nx+x+dx
            if 0<=x+dx<nx and 0<=y+dy<ny and j in safe and j not in reached:
                reached.add(j);queue.append(j)
    offset=camera['offset_flu_m'] if camera else [.12,0,.02]
    pitch=camera['pitch_degrees'] if camera else -10
    choices=[];seen=set()
    for radius in (1.6,2.0,2.4,2.8):
        for n in range(32):
            angle=n*math.tau/32
            i=index(target[0]+radius*math.cos(angle),target[1]+radius*math.sin(angle))
            if i not in reached or i in seen:continue
            seen.add(i);x,y=(i%nx+.5)*cell,(i//nx+.5)*cell
            travel=math.dist(position[:2],[x,y]);distance=math.hypot(target[0]-x,target[1]-y)
            if not (.55<=travel<=3.5 and distance>=1.5):continue
            yaw=math.atan2(target[1]-y,target[0]-x)
            origin=[x+offset[0]*math.cos(yaw)-offset[1]*math.sin(yaw),y+offset[0]*math.sin(yaw)+offset[1]*math.cos(yaw)]
            length=math.dist(origin,target[:2]);unknown=0;blocked=False
            count=max(1,math.ceil(max(0,length-.45)/(cell/2)))
            for step in range(count+1):
                fraction=step/count*max(0,length-.45)/max(length,1e-9)
                j=index(*(origin[k]+(target[k]-origin[k])*fraction for k in (0,1)))
                if j is None or grid[j]==2:blocked=True;break
                unknown+=grid[j]==0
            if blocked:continue
            centre=target[2]+distance*math.tan(math.radians(-pitch))-offset[2]
            height=max(.9,min(1.8,position[2]+.3,max(position[2]-.3,centre)))
            uncertainty=unknown/(count+1)
            choices.append({'pose':[x,y,height,yaw],'mode':'observed-map-sightline',
                'relocation_m':travel,'estimated_standoff_m':distance,'unknown_sightline_fraction':uncertainty,
                'known_sightline_blockers':0,'route_basis':'Connected component of inflated observed-free cells',
                'score':travel+.3*abs(distance-2)+.5*uncertainty})
    return sorted(choices,key=lambda c:(c['score'],c['pose']))
