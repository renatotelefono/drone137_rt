"""Height-aware routing over an identity-free operator map.

The same spherical clearance applies in three dimensions. Controlled takeoff
and landing are the only floor-contact phases, so floor distance is excluded;
room walls, ceiling, objects, overhead shelves and moving-cart bounds remain.
"""
import math
from sim.flight_world import route


def boxes(scene):
    actor=scene['moving_actor']
    return [*scene['obstacles'], *scene.get('fixtures', []),
        dict(x=actor['center'][0],y=actor['center'][1],sx=actor['size'][0]+2*actor['amplitude_m'],
             sy=actor['size'][1],height=actor['size'][2],bottom=0)]


def clearance(scene, position):
    x,y,z=position[:3]
    distance=min(x,y,scene['width']-x,scene['depth']-y,3-z)
    for b in boxes(scene):
        d=[abs(x-b['x'])-b['sx']/2, abs(y-b['y'])-b['sy']/2,
           abs(z-(b.get('bottom',0)+b['height']/2))-b['height']/2]
        signed=math.sqrt(sum(max(v,0)**2 for v in d)) if max(d)>0 else max(d)
        distance=min(distance,signed)
    return distance


def segment_clear(scene, start, end, margin=.58):
    steps=max(1,math.ceil(math.dist(start[:3],end[:3])/.03))
    return all(clearance(scene,[a+(b-a)*i/steps for a,b in zip(start[:3],end[:3])])>=margin
               for i in range(steps+1))


def flight_path(scene, start, end, margin=.58):
    """Checked vertical legs and constant-height paths; no diagonal shortcuts."""
    start,end=list(start[:3]),list(end[:3])
    if not 0 <= end[2] <= 1.8:
        raise ValueError('Destination exceeds the command altitude bounds')
    if min(clearance(scene,start),clearance(scene,end))<margin:
        raise ValueError('Waypoint lacks three-dimensional vehicle clearance')
    choices=[]
    # Measured tracking overshoot is not a legal commanded altitude. Preserve
    # the actual start for collision checks, then descend to a bounded cruise.
    for altitude in sorted({min(1.8,max(1.5,start[2],end[2])),1.8}):
        first,last=[*start[:2],altitude],[*end[:2],altitude]
        if not segment_clear(scene,start,first,margin) or not segment_clear(scene,last,end,margin):
            continue
        try:
            horizontal=route(scene,first,last,margin=margin,altitude=altitude)
        except ValueError:
            continue
        path=[first,*[[*p[:2],altitude] for p in horizontal],end]
        # Recheck all segments in the same 3D metric used by the flight monitor.
        if all(segment_clear(scene,a,b,margin) for a,b in zip([start,*path],path)):
            length=sum(math.dist(a,b) for a,b in zip([start,*path],path))
            choices.append((length,path))
    if not choices:
        raise ValueError('No route with the required three-dimensional clearance')
    return min(choices)[1]
