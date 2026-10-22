"""Apply frozen hardware profiles to the actual simulator, without editing PX4."""
import copy
import math
import xml.etree.ElementTree as ET
from app.airframes import validate


def apply_profile(world, snapshot, observed=False):
    result=copy.deepcopy(world);p=validate(snapshot['profile']);c=p['camera']
    result['hardware']=copy.deepcopy(snapshot)
    result['home']=[4.4,1.25]  # Operator-declared clear launch pad for larger rotor envelopes.
    result['camera'].update(width=c['width'],height=c['height'],vertical_fov=math.degrees(2*math.atan(c['height']/(2*c['fy']))),
        latency_ms=c['latency_ms'],jpeg_quality=c['jpeg_quality'],optics=copy.deepcopy(c))
    # Do not stack the old arbitrary radial warp on calibrated optics.
    result['camera']['effects']['distortion']=0
    result['camera_mount']={'pitch_degrees':c['pitch_degrees'],'body_offset_flu_m':c['offset_flu_m']}
    result['navigation_mode']='observed-range' if observed else 'operator-map'
    result['position_source']='simulated-visual-odometry' if observed else 'simulated-gnss'
    result['title']=p['name']+' · '+result['title']
    return result


def configure_sdf(model, base, snapshot, deny_gps=False):
    p=validate(snapshot['profile']);a=p['airframe'];s=a['geometry_xy_scale']
    root=base.getroot();links=root.findall('.//link')
    # Keep the base frame offset at .24 m. Scale horizontal geometry, mounts,
    # arm/rotor positions and collisions together; this is a quad-X family.
    for link in links:
        for pose in link.findall('.//pose'):
            if pose.text:
                vals=list(map(float,pose.text.split()))
                vals[0]*=s;vals[1]*=s;pose.text=' '.join(map(str,vals))
        for scale in link.findall('.//mesh/scale'):
            vals=list(map(float,scale.text.split()));vals[0]*=s;vals[1]*=s;scale.text=' '.join(map(str,vals))
        for size in link.findall('.//box/size'):
            vals=list(map(float,size.text.split()));vals[0]*=s;vals[1]*=s;size.text=' '.join(map(str,vals))
        for radius in link.findall('.//cylinder/radius'):radius.text=str(float(radius.text)*s)
        if link.get('name','').startswith('rotor_'):
            factor=a['rotor_radius_m']/(.2792307692307692/2*s)
            for element in link.findall('.//mesh/scale')+link.findall('.//box/size'):
                vals=list(map(float,element.text.split()));vals[0]*=factor;vals[1]*=factor;element.text=' '.join(map(str,vals))
    # Rotor mass fraction from the pinned base; total mass equals the profile.
    original=sum(float(l.findtext('inertial/mass','0')) for l in links)
    for link in links:
        mass=link.find('inertial/mass')
        if mass is not None:mass.text=str(float(mass.text)*a['mass_kg']/original)
        inertia=link.find('inertial/inertia')
        if inertia is not None:
            for v in inertia:v.text=str(float(v.text)*a['mass_kg']/original*s*s)
    inertia=root.find('.//link[@name="base_link"]/inertial/inertia')
    for tag,key in [('ixx','inertia_xx'),('iyy','inertia_yy'),('izz','inertia_zz')]:inertia.find(tag).text=str(a[key])
    for plugin in model.findall('plugin[@name="gz::sim::systems::MulticopterMotorModel"]'):
        for tag,key in [('motorConstant','motor_constant'),('momentConstant','moment_constant'),('timeConstantUp','motor_time_up_s'),
                        ('timeConstantDown','motor_time_down_s'),('maxRotVelocity','max_rotor_rad_s'),('rotorDragCoefficient','rotor_drag')]:
            plugin.find(tag).text=str(a[key])
    if deny_gps:
        for link in links:
            for sensor in link.findall('sensor[@type="navsat"]'):link.remove(sensor)
    return {'mass_kg':sum(float(l.findtext('inertial/mass','0')) for l in links),'rotors':4,
            'gps_sensor_removed':deny_gps,'profile_sha256':snapshot['sha256'],
            'geometry':'Scaled horizontal quad-X family; generic upstream collision geometry'}
