"""One metre-scale scene manifest drives Three.js visuals and Gazebo collisions.

The operator route uses a known floor plan. Target truth is evaluator-only.
Tenfold complexity counts independent props, not triangles or a realism score.
"""
import copy
import heapq
import math
import random
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from sim.recon_world import world

HOME = [1.25, 1.25]
VIEWS = [[2.5, 4.8, 1.5, 2.1], [4.35, 5.8, 1.5, 1.6],
         [8., 4.1, 1.5, -1.0], [8.5, 4.9, 1.5, .75]]


def scene(seed=417, target=True, condition='nominal', target_xy=None):
    result = world(seed, 'realism', 'baseline', condition)
    count = len(result['obstacles'])
    result['obstacles'] = [b for b in result['obstacles'] if b['kind'] != 'extinguisher']
    target_xy = target_xy or [4.4, 8.9]
    result['obstacles'].append(dict(x=target_xy[0], y=target_xy[1], sx=.5, sy=.5, height=1.3,
                                    kind='extinguisher' if target else 'red-canister'))
    rng = random.Random(seed)
    # Storage against walls, stacked at varied heights. Open aisles remain usable.
    for i in range(count*10-count):
        zone = i % 4
        stack = i // 4
        column, level = stack % 9, stack // 9
        if zone == 0:
            x, y = .32, 1.8 + column*.82
        elif zone == 1:
            x, y = 11.65, .8 + column*.95
        elif zone == 2:
            x, y = .9 + column*.51, 9.68
        else:
            x, y = 6.8 + column*.52, 9.64
        w, d, h = rng.uniform(.25,.43), rng.uniform(.25,.42), rng.uniform(.25,.48)
        result['obstacles'].append(dict(x=x, y=y, sx=w, sy=d, height=h,
            bottom=.02+level*.55, kind=['carton','storage-bin','paint-tin','red-canister','tool-case'][i%5],
            color=['#a7855c','#3c6172','#b2b8b2','#a9362b','#d0a23e'][i%5],
            scuff=rng.random(), detail=True))
    result.update(title='Dense workshop · native flight', visual_revision='native-workshop-v1',
                  complexity={'baseline_props': count, 'props': len(result['obstacles']),
                              'ratio': len(result['obstacles'])/count,
                              'definition': 'Independent props, including stacked containers; excludes decorative mesh parts.'},
                  moving_actor={'center': [9.4, 8.85], 'amplitude_m': .5, 'period_s': 9.,
                                'size': [.55,.4,1.25], 'description': 'Kinematic rolling stock cart'},
                  camera_mount={'pitch_degrees':-10, 'body_offset_flu_m':[.12,0,.02]},
                  wind={'mean_enu_m_s':[.6,.15,0.], 'gust_fraction':.25, 'period_s':7.,
                        'force_scale':.25, 'calibration':'Synthetic uniform draft; no CFD or real-aircraft calibration'},
                  home=HOME, checkpoints=[])
    result['fixtures']=[]
    # Real shelves support every elevated container; their bounds also collide.
    for x,y,sx,sy in ((.32,5.08,.6,7.55),(11.65,4.6,.6,8.25),(2.94,9.68,4.65,.6),(8.88,9.64,4.65,.6)):
        for level in range(3):
            result['fixtures'].append(dict(x=x,y=y,sx=sx,sy=sy,bottom=max(0,level*.55-.03),height=.05,color='#576c73'))
        if sx>sy:
            posts=[(x-sx/2+.035,y-.25),(x+sx/2-.035,y-.25),(x-sx/2+.035,y+.25),(x+sx/2-.035,y+.25)]
        else:
            posts=[(x-.25,y-sy/2+.035),(x+.25,y-sy/2+.035),(x-.25,y+sy/2-.035),(x+.25,y+sy/2-.035)]
        result['fixtures'] += [dict(x=px,y=py,sx=.045,sy=.045,bottom=0,height=1.7,color='#3c525e') for px,py in posts]
    result['camera'].update(width=960,height=540,bitrate=1400000)
    # Distortion remains in pixels. Ray estimation intentionally assumes nominal
    # intrinsics; this mismatch is part of the test, never corrected from truth.
    result['camera']['effects'].update(jitter=.001)
    for i,b in enumerate(result['obstacles']):
        b['id'] = f'prop-{i:03}'
        b.setdefault('bottom',0.)
    return result


def clear(scene, point):
    x,y = point[:2]
    value=min(x,y,scene['width']-x,scene['depth']-y)
    # Conservative vertical projection of all solid props plus swept moving cart.
    boxes=list(scene['obstacles'])+scene.get('fixtures',[])
    actor=scene['moving_actor']
    boxes.append(dict(x=actor['center'][0], y=actor['center'][1],
                      sx=actor['size'][0]+2*actor['amplitude_m'], sy=actor['size'][1]))
    for b in boxes:
        dx,dy=abs(x-b['x'])-b['sx']/2,abs(y-b['y'])-b['sy']/2
        value=min(value,math.hypot(max(dx,0),max(dy,0)) if dx>0 or dy>0 else max(dx,dy))
    return value


class _RouteGeometry:
    """Per-plan snapshot; no cache survives a changed operator map.

    Routing needs a clearance threshold, not the minimum distance to every
    object. Keep the exact distance arithmetic and sampling of ``clear`` while
    skipping boxes that provably cannot violate the threshold.
    """
    def __init__(self, scene):
        self.width, self.depth = scene['width'], scene['depth']
        boxes = list(scene['obstacles'])+scene.get('fixtures', [])
        actor = scene['moving_actor']
        boxes.append(dict(x=actor['center'][0], y=actor['center'][1],
                          sx=actor['size'][0]+2*actor['amplitude_m'], sy=actor['size'][1]))
        self.boxes = tuple((b['x'], b['y'], b['sx']/2, b['sy']/2) for b in boxes)

    def point_clear(self, point, margin):
        x, y = point[:2]
        if not min(x, y, self.width-x, self.depth-y) >= margin:
            return False
        for bx, by, hx, hy in self.boxes:
            dx, dy = abs(x-bx)-hx, abs(y-by)-hy
            if dx >= margin or dy >= margin:
                continue
            distance = math.hypot(max(dx,0),max(dy,0)) if dx>0 or dy>0 else max(dx,dy)
            if distance < margin:
                return False
        return True

    def segment_clear(self, start, end, margin):
        n=max(1,math.ceil(math.dist(start[:2],end[:2])/.06))
        return all(self.point_clear([start[0]+(end[0]-start[0])*i/n,
                                     start[1]+(end[1]-start[1])*i/n], margin) for i in range(n+1))


def segment_clear(scene, start, end, margin=.58):
    return _RouteGeometry(scene).segment_clear(start, end, margin)


def inspection_sightline_clear(scene, camera_position, candidate_position, endpoint_margin=.7):
    """Conservative visibility against the same known operator map as routing.

    Candidate position comes from predicted pixels/estimated pose, never a scene
    object lookup. Leave the last 0.7 m untested so the candidate's own surface
    does not count as an occluder. No object kind/id influences this check.
    """
    length = math.dist(camera_position, candidate_position)
    if length <= endpoint_margin:
        return False
    boxes = list(scene['obstacles'])+scene.get('fixtures', [])
    actor = scene.get('moving_actor')
    if actor:
        boxes.append(dict(x=actor['center'][0], y=actor['center'][1],
                          sx=actor['size'][0]+2*actor['amplitude_m'], sy=actor['size'][1],
                          bottom=0, height=actor['size'][2]))
    steps = max(1, math.ceil((length-endpoint_margin)/.05))
    for i in range(steps+1):
        distance = (length-endpoint_margin)*i/steps
        p = [a+(b-a)*distance/length for a,b in zip(camera_position,candidate_position)]
        for box in boxes:
            if (abs(p[0]-box['x']) <= box['sx']/2 and abs(p[1]-box['y']) <= box['sy']/2
                    and box.get('bottom',0) <= p[2] <= box.get('bottom',0)+box['height']):
                return False
    return True


def route(scene, start, end, margin=.58):
    """A* on an operator-provided map, followed by swept-path simplification."""
    geometry = _RouteGeometry(scene)
    segment = lambda a,b: geometry.segment_clear(a,b,margin)
    if not geometry.point_clear(start,margin) or not geometry.point_clear(end,margin):
        raise ValueError('Waypoint lacks vehicle clearance')
    if segment(start,end): return [list(end[:2])]
    step=.25
    cell=lambda p:(round(p[0]/step),round(p[1]/step))
    point=lambda c:[c[0]*step,c[1]*step]
    first,last=cell(start),cell(end)
    if not segment(start,point(first)) or not segment(point(last),end):
        raise ValueError('Waypoint cannot connect to navigation grid')
    # Ordered endpoints preserve floating-point sampling direction. Bounded and
    # local to this plan: no stale geometry or cross-mission memory growth.
    @lru_cache(maxsize=4096)
    def edge_clear(a,b):
        return segment(point(a),point(b))
    queue=[(0,first)]; costs={first:0}; parent={first:None}
    while queue:
        _,current=heapq.heappop(queue)
        if current==last: break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nxt=(current[0]+dx,current[1]+dy)
            if not edge_clear(current,nxt): continue
            cost=costs[current]+math.hypot(dx,dy)
            if cost<costs.get(nxt,math.inf):
                parent[nxt]=current;costs[nxt]=cost
                heapq.heappush(queue,(cost+math.dist(nxt,last),nxt))
    if last not in parent: raise ValueError('No collision-free route in operator map')
    points=[list(end[:2])];c=last
    while c is not None:
        points.append(point(c));c=parent[c]
    points.append(list(start[:2]));points.reverse()
    simplified=[];i=0
    while i<len(points)-1:
        j=len(points)-1
        while j>i+1 and not segment(points[i],points[j]):j-=1
        simplified.append(points[j]);i=j
    return simplified


def sdf(scene, px4, destination):
    """Native rotor dynamics; conservative collision boxes mirror scene manifest."""
    root=ET.Element('sdf',version='1.9');w=ET.SubElement(root,'world',name='dense_workshop')
    def tag(parent,name,text):ET.SubElement(parent,name).text=str(text)
    physics=ET.SubElement(w,'physics',name='250hz',type='ignored')
    tag(physics,'max_step_size',.004);tag(physics,'real_time_factor',1)
    for name in ('Physics','UserCommands','SceneBroadcaster','Imu','AirPressure','NavSat','Magnetometer'):
        filename={'AirPressure':'air-pressure','SceneBroadcaster':'scene-broadcaster','UserCommands':'user-commands'}.get(name,name.lower())
        plugin=ET.SubElement(w,'plugin',filename=f'gz-sim-{filename}-system',name=f'gz::sim::systems::{name}')
        if name=='Magnetometer':
            tag(plugin,'use_units_gauss','false');tag(plugin,'use_earth_frame_ned','false')
    wind=scene['wind'];tag(ET.SubElement(w,'wind'),'linear_velocity',' '.join(map(str,wind['mean_enu_m_s'])))
    plugin=ET.SubElement(w,'plugin',filename='gz-sim-wind-effects-system',name='gz::sim::systems::WindEffects')
    tag(plugin,'force_approximation_scaling_factor',wind['force_scale'])
    horizontal=ET.SubElement(plugin,'horizontal');magnitude=ET.SubElement(horizontal,'magnitude')
    tag(magnitude,'time_for_rise',1.);gust=ET.SubElement(magnitude,'sin')
    tag(gust,'amplitude_percent',wind['gust_fraction']);tag(gust,'period',wind['period_s'])
    tag(w,'gravity','0 0 -9.81');tag(w,'magnetic_field','6e-06 2.3e-05 -4.2e-05')
    coord=ET.SubElement(w,'spherical_coordinates')
    for key,value in dict(surface_model='EARTH_WGS84',world_frame_orientation='ENU',latitude_deg=47.397742,longitude_deg=8.545594,elevation=488,heading_deg=0).items():tag(coord,key,value)
    def box(name,x,y,z,sx,sy,sz):
        m=ET.SubElement(w,'model',name=name);tag(m,'static','true');tag(m,'pose',f'{x} {y} {z} 0 0 0')
        link=ET.SubElement(m,'link',name='body')
        for kind in ('collision','visual'):
            g=ET.SubElement(ET.SubElement(link,kind,name=kind),'geometry')
            tag(ET.SubElement(g,'box'),'size',f'{sx} {sy} {sz}')
    box('floor',6,5,-.08,12,10,.16)
    box('ceiling',6,5,3.1,12,10,.2)
    for i,(x,y,sx,sy) in enumerate(((6,0,12,.12),(6,10,12,.12),(0,5,.12,10),(12,5,.12,10))):
        box(f'wall-{i}',x,y,1.5,sx,sy,3)
    box('door-lintel',6,4,2.85,.25,2,.3)
    for b in scene['obstacles']:
        box(b['id'],b['x'],b['y'],b['bottom']+b['height']/2,b['sx'],b['sy'],b['height'])
    for i,b in enumerate(scene.get('fixtures',[])):
        box(f'fixture-{i}',b['x'],b['y'],b['bottom']+b['height']/2,b['sx'],b['sy'],b['height'])
    # The moving actor is a joint-driven collision body (sinusoidal motion).
    actor=scene['moving_actor'];m=ET.SubElement(w,'model',name='moving_cart')
    tag(m,'pose',f'{actor["center"][0]} {actor["center"][1]} 0 0 0 0')
    link=ET.SubElement(m,'link',name='body');tag(link,'gravity','false')
    inertia=ET.SubElement(link,'inertial');tag(inertia,'mass',10)
    for kind in ('collision','visual'):
        element=ET.SubElement(link,kind,name=kind);tag(element,'pose','0 0 .625 0 0 0')
        tag(ET.SubElement(ET.SubElement(element,'geometry'),'box'),'size','.55 .4 1.25')
    joint=ET.SubElement(m,'joint',name='slide',type='prismatic');tag(joint,'parent','world');tag(joint,'child','body')
    axis=ET.SubElement(joint,'axis');tag(axis,'xyz','1 0 0');limit=ET.SubElement(axis,'limit');tag(limit,'lower',-.5);tag(limit,'upper',.5)
    plugin=ET.SubElement(m,'plugin',filename='gz-sim-joint-position-controller-system',name='gz::sim::systems::JointPositionController')
    tag(plugin,'joint_name','slide');tag(plugin,'topic','/drone137/cart');tag(plugin,'p_gain',150);tag(plugin,'d_gain',30)
    publisher=ET.SubElement(m,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for key,value in dict(publish_link_pose='false',publish_model_pose='true',use_pose_vector_msg='true',update_frequency=20).items():tag(publisher,key,value)
    # Inherited PX4 x500 sensors retain upstream measured IMU/barometer noise.
    # No fake GPS denial: simulated GNSS is explicitly a remaining indoor gap.
    model=ET.parse(px4/'Tools/simulation/gz/models/x500/model.sdf').getroot().find('model')
    model=copy.deepcopy(model);model.set('name','x500_0');tag(model,'pose',f'{scene["home"][0]} {scene["home"][1]} .3 0 0 0')
    joints=ET.SubElement(model,'plugin',filename='gz-sim-joint-state-publisher-system',name='gz::sim::systems::JointStatePublisher')
    tag(joints,'topic','/drone137/rotor-joints');tag(joints,'update_rate',20)
    for i in range(4):tag(joints,'joint_name',f'rotor_{i}_joint')
    # Generated model derivative only; leave the pinned upstream tree unchanged.
    base=ET.parse(px4/'Tools/simulation/gz/models/x500_base/model.sdf')
    if scene.get('hardware'):
        from sim.hardware import configure_sdf
        import json
        audit=configure_sdf(model,base,scene['hardware'],scene.get('position_source')=='simulated-visual-odometry')
        (Path(destination).parent/'airframe-audit.json').write_text(json.dumps(audit,indent=2))
    tag(base.find('.//link[@name="base_link"]'),'enable_wind','true')
    base_path=Path(destination).parent/'x500-base-draft.sdf';base.write(base_path,encoding='unicode')
    model.find('include/uri').text=base_path.resolve().as_uri()
    # External read-only truth stream. No camera renderer inside Gazebo.
    plugin=ET.SubElement(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for key,value in dict(publish_link_pose='false',publish_sensor_pose='false',publish_collision_pose='false',publish_visual_pose='false',publish_nested_model_pose='true',publish_model_pose='true',use_pose_vector_msg='true',update_frequency=20).items():tag(plugin,key,value)
    w.append(model)
    ET.indent(root);ET.ElementTree(root).write(destination,encoding='unicode')
    return Path(destination)
