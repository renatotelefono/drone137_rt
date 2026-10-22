"""Post-flight physical checks from generated SDF and measured joint telemetry.

These are simulation checks, not calibration against a physical aircraft.
Never called by recognition, guidance or the language models.
"""
import math
import statistics
import xml.etree.ElementTree as ET


def audit(folder, samples, landed):
    base=ET.parse(folder/'x500-base-draft.sdf').getroot()
    model=ET.parse(folder/'world.sdf').getroot().find('.//model[@name="x500_0"]')
    motors=model.findall('plugin[@name="gz::sim::systems::MulticopterMotorModel"]')
    by_number={int(p.findtext('motorNumber')):p for p in motors}
    structure=len(motors)==4 and set(by_number)==set(range(4))
    directions=[];scales=[];maxima=[]
    for i in range(4):
        link=base.find(f'.//link[@name="rotor_{i}"]');joint=base.find(f'.//joint[@name="rotor_{i}_joint"]')
        structure &= (link is not None and joint is not None and link.find('collision') is not None
                      and float(link.findtext('inertial/mass','0'))>0
                      and joint.findtext('parent')=='base_link' and joint.findtext('child')==f'rotor_{i}')
        p=by_number.get(i)
        if p is not None:
            directions.append(p.findtext('turningDirection'))
            scales.append(float(p.findtext('rotorVelocitySlowdownSim','1')))
            maxima.append(float(p.findtext('maxRotVelocity')))
            structure &= (p.findtext('jointName')==f'rotor_{i}_joint'
                          and float(p.findtext('motorConstant','0'))>0
                          and float(p.findtext('timeConstantUp','0'))>0)
    mass=sum(float(l.findtext('inertial/mass','0')) for l in base.findall('.//link'))
    structure &= sorted(directions)==['ccw','ccw','cw','cw'] and mass>0
    steady=[s for s in samples if s['phase']=='inspection']
    observed=[s for s in steady if len(s['truth'].get('rotor_joint_rad_s',[]))==4]
    fresh=[s for s in observed if abs(s['sim_time']-s['truth']['rotor_stamp'])<.2]
    rotor_ok=bool(steady) and len(fresh)>=.95*len(steady)
    speeds=[[],[],[],[]]
    for s in fresh:
        for i,v in enumerate(s['truth']['rotor_joint_rad_s']):
            physical=v*scales[i];speeds[i].append(abs(physical))
            rotor_ok &= (math.isfinite(physical) and 100<abs(physical)<=maxima[i]*1.05
                         and (physical>0)==(directions[i]=='ccw'))
    altitudes=[s['truth']['model_position'][2] for s in samples]
    tracking=[math.dist(s['estimated']['position'],s['goal'][:3]) for s in steady if s['goal']]
    tracking_rmse=math.sqrt(statistics.mean(x*x for x in tracking)) if tracking else None
    tilt=[math.degrees(math.acos(max(-1,min(1,1-2*(s['truth']['quaternion'][0]**2+s['truth']['quaternion'][1]**2))))) for s in steady]
    liftoff=bool(altitudes) and max(altitudes)-min(altitudes)>1.0
    hover=len(steady)>=20 and tracking_rmse is not None and tracking_rmse<.2 and max(tilt)<15
    checks={'four_connected_physical_rotors':bool(structure),'rotors_spinning_in_correct_directions':bool(rotor_ok),
            'lift_off_over_one_metre':liftoff,'stable_inspection_hover':hover,'landed':bool(landed)}
    return {'checks':checks,'all_pass':all(checks.values()),'total_mass_kg':mass,
        'inspection_samples':len(steady),'fresh_rotor_samples':len(fresh),
        'rotor_equivalent_rad_s':[{ 'min':min(v) if v else None,'max':max(v) if v else None,
                                  'mean':statistics.mean(v) if v else None} for v in speeds],
        'maximum_model_altitude_m':max(altitudes,default=None),'hover_tracking_rmse_m':tracking_rmse,
        'maximum_hover_tilt_degrees':max(tilt,default=None),
        'measurement':'Gazebo joint velocities multiplied by the SDF rotor slowdown factor; actual simulated joints, not commanded motor speeds.',
        'limitations':'Generic rigid-body, motor and collision models. No physical airframe calibration or propeller flex/propwash validation.'}
