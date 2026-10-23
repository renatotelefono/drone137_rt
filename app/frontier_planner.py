"""Reachable information viewpoints from the observed map only."""
from collections import deque
import math
import cv2
import numpy as np


def visibility_rewards(occupied, seen, logodds, cells, resolution, interest=None):
    """Trace from the candidate cell, including obstacles less than 0.5 m away."""
    angles=np.arange(24)*2*math.pi/24
    lengths=np.arange(resolution,3.6,resolution)
    offsets=np.floor(.5+np.stack((np.cos(angles),np.sin(angles)),axis=1)[:,None,:]*lengths[None,:,None]/resolution).astype(int)
    rays=cells[:,None,None,:]+offsets[None,:,:,:]
    inside=np.all((rays>=0)&(rays<len(seen)),axis=-1)
    clipped=np.clip(rays,0,len(seen)-1);rx,ry=clipped[:,:,:,0],clipped[:,:,:,1]
    blocked=np.maximum.accumulate(occupied[rx,ry]|~inside,axis=2)
    novelty=(interest[rx,ry] if interest is not None else
             np.where(seen[rx,ry]==0,1.,np.where(logodds[rx,ry]>=-.3,.15,0.)))
    # Polar rays cover more area with distance, but monocular range uncertainty
    # also grows with distance squared at a fixed translation baseline. Area
    # alone rewarded backing away from an unresolved passage. Prefer useful
    # nearby measurements while retaining a bounded reward for farther views.
    weight=2*lengths/(.25+lengths**2)
    return angles,np.sum(novelty*~blocked*weight[None,None,:],axis=2)


def exploration_interest(mapping):
    """Prioritize unresolved volume above observed ground, not infinite void.

    A textureless wall can have an incomplete occupancy outline. Unseen space
    behind it must not dominate the next-view score just because it is large.
    A small ground-neighborhood reward still seeks new observations at edges.
    These are priorities only: ground evidence never grants flight clearance.
    """
    ground=mapping.ground>0
    near=cv2.distanceTransform(np.uint8(~ground),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)*mapping.resolution
    interior=cv2.distanceTransform(np.uint8(ground & (mapping.logodds<=.5)),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)*mapping.resolution
    unknown=mapping.seen==0
    interest=np.where(unknown & (near<.6),.05,0.)
    unresolved=(mapping.logodds>=-.3)|~mapping.flight_clear
    # A narrow wedge of observed floor can be the first glimpse through an
    # opening. A hard width cutoff gave that evidence zero value and made the
    # explorer abandon passages. Rank broad patches higher, but retain a
    # positive sensing reward for narrow ones. This never grants clearance.
    grounded=ground & unresolved
    interest[grounded]=np.minimum(1.,(interior[grounded]/.35)**2)
    interest[mapping.logodds>.5]=0.
    interest/=1+4*np.asarray(getattr(mapping,'view_attempts',np.zeros_like(interest)),dtype=float)
    return interest


def record_view_attempt(mapping,position,yaw):
    """Remember where an actual translated view tried to resolve uncertainty.

    Unresolved cells remain unknown. This only discounts redundant sensing;
    it never supplies geometry or makes a cell safe for navigation.
    """
    angles=yaw+np.linspace(-math.pi/3,math.pi/3,33)
    distances=np.arange(mapping.resolution,3.6,mapping.resolution)
    points=np.asarray(position[:2])+np.stack((np.cos(angles),np.sin(angles)),axis=1)[:,None,:]*distances[None,:,None]
    cells=np.floor((points+mapping.extent)/mapping.resolution).astype(int)
    inside=np.all((cells>=0)&(cells<len(mapping.seen)),axis=-1)
    cells=np.clip(cells,0,len(mapping.seen)-1)
    x,y=cells[:,:,0],cells[:,:,1]
    blocked=np.maximum.accumulate(mapping.visibility_obstacles[x,y]|~inside,axis=1)
    touched=np.unique(cells[~blocked],axis=0)
    if len(touched):
        x,y=touched.T
        mapping.view_attempts[x,y]=np.minimum(100,mapping.view_attempts[x,y]+1)


def choose_frontier(options, position, heading):
    """Finish a competitive nearby inspection before paying for a long detour.

    Small changes in sparse geometry used to reverse a promising approach on
    almost equal scores. Apply bounded hysteresis only to already-cleared
    candidates in front of the current camera. A substantially better view,
    exhausted local gain, or a rejected route still wins immediately.
    """
    if not options:
        return None
    best = options[0]
    if best['path_distance_m'] <= 2.:
        return best
    forward = np.array([math.cos(heading), math.sin(heading)])
    for option in options[1:]:
        delta = np.asarray(option['viewpoint']) - np.asarray(position[:2])
        turn = abs(math.atan2(math.sin(option['view_heading_rad']-heading),
                              math.cos(option['view_heading_rad']-heading)))
        if (option['score'] >= .8*best['score'] and option['path_distance_m'] <= 1.5
                and float(delta @ forward) > .15 and turn <= math.pi/3):
            return option
    return best


def candidates(mapping, position, heading, limit=5):
    start=mapping.cell(position);resolution=mapping.resolution
    free=(mapping.seen>0)&(mapping.logodds<-.3)
    if hasattr(mapping,'flight_clear'):free&=mapping.flight_clear
    radius=.2 if hasattr(mapping,'flight_clear') else .38
    n=math.ceil((radius+resolution/2)/resolution)
    x,y=np.mgrid[-n:n+1,-n:n+1]
    kernel=np.uint8(np.hypot(x,y)*resolution<=radius+resolution/2)
    clear=cv2.erode(free.astype(np.uint8),kernel,borderType=cv2.BORDER_CONSTANT,borderValue=0)>0
    distance=cv2.distanceTransform(free.astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)*resolution
    queue=deque([start]);parent={start:None};cost={start:0}
    while queue:
        cell=queue.popleft()
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=cell[0]+dx,cell[1]+dy
            if nxt in parent or not mapping.inside(nxt) or not free[nxt]:continue
            safe=clear[nxt]
            if not safe and not clear[cell]:
                safe=(mapping.clear(mapping.xy(nxt),radius=.12) and distance[nxt]>=distance[cell])
            if not safe:continue
            parent[nxt]=cell;cost[nxt]=cost[cell]+resolution;queue.append(nxt)
    # Close sub-clearance-size holes only for visibility scoring. This does
    # not change the saved occupancy map or certify any new flight space.
    surfaces=getattr(mapping,'visibility_obstacles',mapping.logodds>.5)
    occupied=cv2.morphologyEx(np.uint8(surfaces),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))>0
    separation=cv2.distanceTransform(np.uint8(~occupied),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)*resolution
    # The separate clearance test already includes the aircraft and grid
    # margins. A 0.65 m viewpoint exclusion prevented approaching ordinary
    # doorways even when their observed passage was collision-clear.
    cells=np.array([c for c in parent if c!=start and clear[c] and separation[c]>.35],dtype=int)
    if not len(cells):return []
    interest=exploration_interest(mapping) if hasattr(mapping,'ground') else None
    angles,rewards=visibility_rewards(occupied,mapping.seen,mapping.logodds,cells,resolution,interest)
    scores=sum(np.roll(rewards,j,axis=1) for j in range(-3,4))
    points=(cells+.5)*resolution-mapping.extent
    for old in getattr(mapping,'explored_views',[]):
        # A closer view can resolve depth that the previous view could not.
        # Suppressing a 1.2 m disk prevented incremental approach to a newly
        # observed doorway. Only suppress essentially the same camera station;
        # per-cell view attempts still discount repeated unresolved content.
        nearby=np.linalg.norm(points-np.asarray(old[:2]),axis=1)<.25
        viewed=np.abs(np.arctan2(np.sin(angles-old[2]),np.cos(angles-old[2])))<math.pi/3
        scores[nearby[:,None]&viewed[None,:]]=0
    hint=np.ones(len(cells))
    for view in getattr(mapping,'semantic_views',[]):
        delta=points-np.asarray(view['position']);distance=np.linalg.norm(delta,axis=1)
        if view['navigation_view']=='wall_closeup':
            viewed=np.abs(np.arctan2(np.sin(angles-view['yaw']),np.cos(angles-view['yaw'])))<math.pi/3
            scores[(distance<1.5)[:,None]&viewed[None,:]]*=.1
        if view['navigation_view']=='room_view' and view.get('opening_bearing') is not None:
            bearing=view['opening_bearing']
            angle=np.arctan2(delta[:,1],delta[:,0])-bearing
            aligned=(np.abs(np.arctan2(np.sin(angle),np.cos(angle)))<.3)&(distance>.6)&(distance<6)
            hint=np.maximum(hint,np.where(aligned,1.8,1.))
    best=np.argmax(scores,axis=1);gain=scores[np.arange(len(cells)),best]
    turn=np.abs(np.arctan2(np.sin(angles[best]-heading),np.cos(angles[best]-heading)))
    travel=np.array([cost[tuple(c)] for c in cells])
    value=gain*hint/(4+travel/.55+turn/.65)/(1+.02*mapping.visits[cells[:,0],cells[:,1]])
    selected=[]
    for i in np.argsort(-value):
        if gain[i]<.5:continue
        point=points[i].tolist()
        if any(math.dist(point,o['viewpoint'])<1 for o in selected):continue
        route=[];c=tuple(cells[i])
        while c is not None:route.append(c);c=parent[c]
        route.reverse();route=[list(position[:2])]+[mapping.xy(c) for c in route[1:]]
        next_point=None
        for p in route[1:]:
            if math.dist(position[:2],p)>2.:break
            if mapping.segment_clear(position[:2],p):next_point=p
        if next_point is None:continue
        yaw=float(angles[best[i]]) if math.dist(next_point,point)<.3 else math.atan2(next_point[1]-position[1],next_point[0]-position[0])
        selected.append({'score':float(value[i]),'information_gain':float(gain[i]),'path_distance_m':float(travel[i]),
                         'viewpoint':point,'view_heading_rad':float(angles[best[i]]),'target':[*next_point,1.5,yaw]})
        if len(selected)>=limit:break
    return selected
