"""Camera rays using measured full attitude. No scene metadata or ground-truth pose."""
import math
from adapters.native_flight import rotate


def detail_view(position, location, side=1):
    """Bounded parallax/closer view from an estimated candidate, never scene truth.

    Caller must check clearance and route feasibility against the operator map.
    Lateral motion retains triangulation baseline; a purely forward move would not.
    """
    target = location['xyz_m']
    if any(not math.isfinite(v) for v in [*position, *target]) or side not in (-1, 1):
        raise ValueError('Invalid detail viewpoint inputs')
    dx, dy = target[0]-position[0], target[1]-position[1]
    distance = math.hypot(dx, dy)
    if distance < 1.4:
        return None
    ux, uy = dx/distance, dy/distance
    advance = min(.3, distance-1.4)
    x = position[0]+advance*ux-side*.65*uy
    y = position[1]+advance*uy+side*.65*ux
    # A slightly higher view helps resolve the top mechanism. Keep the estimated
    # candidate center within the nominal camera's vertical field of view.
    range_after = math.hypot(target[0]-x, target[1]-y)
    height = min(1.8, position[2]+.15, target[2]+range_after*math.tan(math.radians(25)))
    return [x, y, max(.9, height), math.atan2(target[1]-y, target[0]-x)]


def active_detail_views(position, location, camera=None, elevated=False):
    """Centred or elevated alternatives from estimated rays, never object truth.

    Each move is under one metre horizontally, at most 0.3 m vertically and
    retains at least 1.4 m estimated standoff. The caller must enforce observed
    clearance and parallax against the observation it will actually retain.
    """
    target=location['xyz_m']
    if any(not math.isfinite(v) for v in [*position,*target]):
        raise ValueError('Invalid detail viewpoint inputs')
    dx,dy=target[0]-position[0],target[1]-position[1]
    distance=math.hypot(dx,dy)
    if distance<1.4:return []
    ux,uy=dx/distance,dy/distance
    pitch=abs(camera['pitch_degrees'] if camera else -10)
    max_down=(-camera['pitch_degrees']+math.degrees(math.atan((camera['height']-camera['cy'])/camera['fy']))-5) if camera else 25
    if elevated and max_down<=0:return []
    poses=[]
    # A small, uncut box can mean occlusion. First look around/above it instead
    # of descending toward its visible fragment and hiding the rest of it.
    options=((0,.65),(.3,.65),(.55,.6),(.85,.4)) if elevated else ((.85,.4),(.55,.6),(.3,.65),(0,.65))
    for forward,lateral in options:
        advance=min(forward,distance-1.4)
        for side in (1,-1):
            x=position[0]+advance*ux-side*lateral*uy
            y=position[1]+advance*uy+side*lateral*ux
            after=math.hypot(target[0]-x,target[1]-y)
            if elevated:
                height=min(1.8,position[2]+.15,target[2]+after*math.tan(math.radians(max_down)))
                if height<position[2]-.02:continue
                height=max(.9,height)
            else:
                centre=target[2]+after*math.tan(math.radians(pitch))
                height=max(.9,min(1.8,position[2]+.3,max(position[2]-.3,centre)))
            poses.append([x,y,height,math.atan2(target[1]-y,target[0]-x)])
    return poses


def retained_observation(first, first_supported, current, current_supported):
    """The same reference must be used for planning and the next ray pair."""
    return current if current_supported or not first_supported else first


def planned_parallax(reference, pose, location, camera=None):
    """Check a proposed view against the retained observation, not the last pose.

    Uses only estimated candidate geometry. The captured rays still have to pass
    triangulate afterwards; predicted geometry never authorizes a found claim.
    """
    offset = camera['offset_flu_m'] if camera else [.12, 0, .02]
    yaw = pose[3]
    origin = [pose[0]+offset[0]*math.cos(yaw)-offset[1]*math.sin(yaw),
              pose[1]+offset[0]*math.sin(yaw)+offset[1]*math.cos(yaw), pose[2]+offset[2]]
    delta = [v-o for v, o in zip(location['xyz_m'], origin)]
    distance = math.sqrt(sum(v*v for v in delta))
    if distance == 0:
        return None
    ray = [v/distance for v in delta]
    baseline = math.dist(reference['origin'], origin)
    angle = math.degrees(math.acos(min(1, abs(sum(a*b for a,b in zip(reference['ray'], ray))))))
    # Leave room for tracking/box errors instead of aiming exactly at rejection.
    if baseline < .55 or angle < 7:
        return None
    return {'baseline_m': baseline, 'intersection_angle_degrees': angle}


def detection(estimated,bbox,view_id,camera=None):
    p=math.radians(-10);t=math.tan(math.radians(41)/2)
    u,v=(bbox[0]+bbox[2])/2000,(bbox[1]+bbox[3])/2000
    xn,yn=(2*u-1)*t*16/9,(1-2*v)*t
    if camera:
        from app.camera_geometry import undistort
        xn,yd=undistort(u*camera['width'],v*camera['height'],camera)
        yn=-yd;p=math.radians(camera['pitch_degrees'])
    # Body FLU: optical right is -Y; optical up accounts for the fixed camera pitch.
    ray=rotate(estimated['quaternion'],[math.cos(p)-yn*math.sin(p),-xn,math.sin(p)+yn*math.cos(p)])
    n=math.sqrt(sum(a*a for a in ray));ray=[a/n for a in ray]
    offset=rotate(estimated['quaternion'],camera['offset_flu_m'] if camera else [.12,0,.02])
    return {'origin':[a+b for a,b in zip(estimated['position'],offset)],'ray':ray,'view_id':view_id,
            'intrinsics_source':'hardware-profile' if camera else 'nominal'}


def triangulate(first,second):
    if first['view_id']==second['view_id']:return None
    p,q,a,b=first['origin'],second['origin'],first['ray'],second['ray']
    baseline=math.dist(p,q)
    if baseline<.45:return None
    dot=lambda a,b:sum(x*y for x,y in zip(a,b))
    ab=dot(a,b);det=1-ab*ab
    if det<math.sin(math.radians(5))**2:return None
    delta=[q[i]-p[i] for i in range(3)]
    ta=(dot(delta,a)-ab*dot(delta,b))/det
    tb=(ab*dot(delta,a)-dot(delta,b))/det
    if not (.3<=ta<=8 and .3<=tb<=8):return None
    x=[p[i]+ta*a[i] for i in range(3)];y=[q[i]+tb*b[i] for i in range(3)]
    residual=math.dist(x,y)
    if residual>.3:return None
    point=[(x[i]+y[i])/2 for i in range(3)]
    if not (0<=point[0]<=12 and 0<=point[1]<=10 and .05<=point[2]<=2.8):return None
    return {'xy_m':point[:2],'xyz_m':point,'ray_gap_m':residual,'baseline_m':baseline,
            'intersection_angle_degrees':math.degrees(math.acos(min(1,abs(ab)))),
            'source_views':[first['view_id'],second['view_id']],
            'method':'Predicted pixels + PX4 estimated position and full attitude; '+
                ('profile camera intrinsics and distortion' if first.get('intrinsics_source')==second.get('intrinsics_source')=='hardware-profile' else 'nominal camera intrinsics')}
