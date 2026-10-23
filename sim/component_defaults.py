"""Evidence-labelled seed components. No value here is a hardware qualification.

Tables from the cited experiment describe THAT propulsion system. Candidate
720/8520 curves are explicit hypotheses, never relabelled as measurements.
"""
import copy

CF = 'https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/functional-areas/pwm-to-thrust/'
DRONA = 'https://www.dronaaviation.com/hardware/parts'
SEEED = 'https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/#resources'
IMU = 'https://files.seeedstudio.com/wiki/Xadow_IMU_6DOF/res/MPU6050.pdf'
TOF = 'https://www.st.com/resource/en/datasheet/vl53l0x.pdf'


def seeds():
    components = []

    def add(identity, name, kind, params, published=None, notes='Engineering hypothesis; bench calibration required.'):
        evidence = {key: {'status': 'estimated', 'source': '', 'note': notes} for key in params}
        for key, (status, source, note) in (published or {}).items():
            evidence[key] = dict(status=status, source=source, note=note)
        components.append(dict(id=identity, name=name, kind=kind, parameters=params, evidence=evidence))

    # Total force/current in the original table belong to all FOUR motors.
    # Remove the measured 0.24 A idle draw, divide by four, and index by PWM*V.
    rows = [(0.24,0,4.01,0,0),(.37,1.6,3.98,6.25,4485),(.56,4.8,3.95,12.5,7570),
            (.75,7.9,3.92,18.75,9374),(.94,10.9,3.88,25,10885),(1.15,13.9,3.84,31.25,12277),
            (1.37,17.3,3.80,37.5,13522),(1.59,21,3.76,43.25,14691),(1.83,24.4,3.71,50,15924),
            (2.11,28.6,3.67,56.25,17174),(2.39,32.8,3.65,62.5,18179),(2.71,37.3,3.62,68.75,19397),
            (3.06,41.7,3.56,75,20539),(3.46,46,3.48,81.25,21692),(3.88,51.9,3.40,87.5,22598),
            (4.44,57.9,3.30,93.75,23882)]
    curve = [[round(v*d/100,8), round(g*.00981/4,8), round((a-.24)/4,8), rpm] for a,g,v,d,rpm in rows]
    add('cf2-published-propulsion', 'Crazyflie 2.x published propulsion reference', 'propulsion',
        dict(mass_kg=.0018, prop_diameter_m=.045, curve=curve, time_up_s=.025, time_down_s=.04,
             torque_per_thrust_m=.006, max_voltage_v=4.2),
        {'curve': ('derived', CF, '2015 four-motor table: thrust/4; (current-0.24 A)/4; effective voltage=PWM*V. Assumes motor symmetry and average-voltage equivalence. Clamp outside measured domain; no extrapolation. RPM column is published average.')})
    for identity, name, mass, diameter, force, current, rpm in [
            ('motor-720-55-hypothesis','720 + 55 mm (unmeasured thrust)',.0034,.055,.27,1.6,26000),
            ('motor-8520-65-hypothesis','8520 + 65 mm (unmeasured thrust)',.0054,.065,.42,2.3,24000)]:
        add(identity,name,'propulsion',dict(mass_kg=mass,prop_diameter_m=diameter,
            curve=[[0,0,0,0],[1,.03, .2,6000],[2,force*.30,current*.38,14000],
                   [3,force*.65,current*.73,20000],[3.7,force,current,rpm]],
            time_up_s=.035,time_down_s=.055,torque_per_thrust_m=.007,max_voltage_v=4.2),
            {'prop_diameter_m':('specified', 'https://speedyfpv.com/collections/brushed-motors/brand-speedyfpv',
                'Matched propeller diameter listed by supplier; this does not validate the assumed thrust curve.')})
    for identity, name, mass, diagonal, guard, drag in [
            ('frame-micro','Micro 90 guarded frame',.008,.09,.0015,.004),
            ('frame-scout','Scout 110 guarded frame',.012,.11,.0015,.006),
            ('frame-guard','Guard 110 upper-hoop frame',.020,.11,.0022,.008),
            ('frame-reference','Published-mass reference frame surrogate',.008,.065,.0001,.002)]:
        add(identity,name,'frame',dict(mass_kg=mass,motor_diagonal_m=diagonal,guard_clearance_m=guard,
            drag_area_m2=drag,body_height_m=.024))
    for capacity,mass,resistance in [(350,.010,.12),(500,.014,.09),(550,.016,.085),(240,.0073,.12)]:
        add(f'battery-{capacity}',f'1S {capacity} mAh provisional pack','battery',
            dict(mass_kg=mass,capacity_mah=capacity,resistance_ohm=resistance,full_v=4.2,empty_v=3.2,cutoff_v=3.1))
    p=dict(mass_kg=.016,capacity_mah=600,resistance_ohm=.070,full_v=4.2,empty_v=3.2,cutoff_v=3.1)
    add('pluto-600','Pluto 600 published pack specification','battery',p,
        {k:('specified',DRONA,'Manufacturer table. Resistance uses the published <0.070 ohm bound conservatively; ageing and wiring are not included.')
         for k in ('mass_kg','capacity_mah','resistance_ohm','full_v','empty_v')})
    add('ao3400a-drivers','Four AO3400A drivers + suppression','driver',
        dict(mass_kg=.002,resistance_ohm=.048),
        {'resistance_ohm':('specified','https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a',
            '48 milliohm maximum at 2.5 V gate drive used as a conservative nominal-temperature value. PCB thermal and switching losses unmodelled.')})
    add('reference-drivers','Reference effective motor drivers','driver',dict(mass_kg=.0005,resistance_ohm=0))
    for identity,name,mass,current in [('sense-single','XIAO Sense + carrier + wiring',.012,.20),
                                      ('sense-dual','Sense + dedicated flight MCU + carrier',.016,.27),
                                      ('reference-avionics','Reference avionics mass surrogate',.003,.24)]:
        add(identity,name,'avionics',dict(mass_kg=mass,idle_current_a=current,control_hz=250,
            camera_width=640,camera_height=480,camera_fps=5,camera_latency_ms=120,link_timeout_s=.5),
            {'camera_width':('estimated',SEEED,'Configured test resolution; not a measured camera pipeline.'),
             'camera_height':('estimated',SEEED,'Configured test resolution; not a measured camera pipeline.')})
    add('mpu6050','MPU6050 + breakout','imu',dict(mass_kg=.002,gyro_noise_rad_s=.003,gyro_bias_rad_s=.001),
        {'gyro_noise_rad_s':('estimated',IMU,'Effective sampled noise hypothesis; datasheet density requires bandwidth/filter configuration.')})
    add('reference-imu','Reference IMU mass surrogate','imu',dict(mass_kg=.001,gyro_noise_rad_s=.003,gyro_bias_rad_s=.001))
    add('vl53l0x','VL53L0X + mount','range',dict(mass_kg=.002,noise_m=.03,max_range_m=1.2),
        {'max_range_m':('specified',TOF,'Nominal default profile; lighting, reflectance and timing affect actual usable range.')})
    motor_source = 'https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw'
    prop_source = 'https://speedyfpv.com/products/hqprop-65mm-ultralight-propeller-set-2x-cw-2x-ccw-gray'
    # A purchasable bench build is distinct from the exploratory power-v2 pack.
    # It borrows the same UNMEASURED propulsion hypothesis, not a measured curve.
    propulsion = copy.deepcopy(next(c['parameters'] for c in components if c['id']=='motor-8520-65-hypothesis'))
    propulsion['mass_kg'] = .00539
    add('utm8520-hq65-bench', 'UTM 41C-069-230 + HQProp 65 mm (unmeasured)', 'propulsion', propulsion,
        {'mass_kg': ('derived', motor_source+' ; '+prop_source, 'Supplier approximately 5 g motor plus 0.39 g propeller. Wiring/production variation requires weighing.'),
         'prop_diameter_m': ('specified', prop_source, '65 mm, two blades, 1 mm shaft. Actual thrust/current/RPM with this motor remains unmeasured.')},
        notes='The generic 8520/65 mm hypothesis is reused for sensitivity testing only. No loaded motor curve is published for this exact purchased combination; bench calibration is mandatory.')
    add('betafpv450-4v2-bench', 'BETAFPV 450 mAh BT2.0, limited to 4.2 V (unmeasured)', 'battery',
        dict(mass_kg=.0137, capacity_mah=400, resistance_ohm=.10, full_v=4.2, empty_v=3.2, cutoff_v=3.1),
        {'mass_kg': ('derived', 'https://betafpv.com/collections/batt-1s/products/bt2-0-450mah-1s-30c-battery-4pcs',
            'Manufacturer 12.7 g pack plus provisional 1 g aircraft pigtail. Actual mass required.')},
        notes='Manufacturer rates the cell 450 mAh at a 4.35 V charge. This build limits charge to 4.2 V: 400 mAh usable capacity and 0.10 ohm resistance are provisional assumptions, not measured or manufacturer values. Sweep and measure them before flight.')
    # Explicit design revisions, not changes to the original battery hypotheses.
    # Ideal parallel-cell arithmetic; cell properties AND harness remain estimates.
    for count in (2,3):
        add(f'battery-240-{count}p',f'1S{count}P 240 mAh cells + 1 g harness (unmeasured)','battery',
            dict(mass_kg=.0073*count+.001,capacity_mah=240*count,resistance_ohm=.12/count,
                 full_v=4.2,empty_v=3.2,cutoff_v=3.1),
            notes=f'Design hypothesis: {count} matched battery-240@1 cells in parallel. Mass=count*7.3 g+1 g harness; capacity=count*240 mAh; ideal cell resistance=0.12/count ohm. Parent cell data, interconnect resistance, current sharing and price are unmeasured; not a sourced commercial pack.')
    configs=[]
    for identity,name,frame,motor,battery,avionics,imu,extra in [
        ('micro-90','D137 Micro 90','frame-micro','motor-720-55-hypothesis','battery-350','sense-single','mpu6050',None),
        ('scout-110','D137 Scout 110','frame-scout','motor-8520-65-hypothesis','battery-500','sense-single','mpu6050',None),
        ('guard-110','D137 Guard 110','frame-guard','motor-8520-65-hypothesis','battery-550','sense-single','mpu6050',None),
        ('height-110','D137 Height 110','frame-scout','motor-8520-65-hypothesis','battery-500','sense-single','mpu6050','vl53l0x'),
        ('split-110','D137 Split 110','frame-scout','motor-8520-65-hypothesis','battery-500','sense-dual','mpu6050',None),
        ('scout-published-pack','Scout 110 / published Pluto battery','frame-scout','motor-8520-65-hypothesis','pluto-600','sense-single','mpu6050',None),
        ('cf2-reference','27 g published-propulsion reference','frame-reference','cf2-published-propulsion','battery-240','reference-avionics','reference-imu',None)]:
        slots=dict(frame=frame,propulsion=motor,battery=battery,avionics=avionics,imu=imu)
        slots['driver']='reference-drivers' if identity=='cf2-reference' else 'ao3400a-drivers'
        if extra:slots['range']=extra
        configs.append(dict(id=identity,name=name,components={k:v+'@1' for k,v in slots.items()},
            notes=('Reference experiment only: 27 g total matches CF2 datasheet; mass distribution, controller, battery dynamics and drag remain assumptions. No priced camera aircraft implied.'
                if identity=='cf2-reference' else 'Exploratory indoor design. Motor thrust and most masses unmeasured. Budget not recalculated after swaps.')))
    for original,parallel in [('micro-90',2),('scout-110',2),('guard-110',3),('height-110',3),('split-110',3)]:
        variant=copy.deepcopy(next(c for c in configs if c['id']==original))
        variant['id']=f'{original}-power-v2'
        variant['name']+=f' / power v2 (1S{parallel}P)'
        variant['components']['battery']=f'battery-240-{parallel}p@1'
        variant['notes']='Battery design revision; original frame/motors/camera/sensors retained. Parallel 240 mAh cells and harness are unmeasured hypotheses; added mass included. Reprice and bench-test before accepting the original $50 budget. No hardware qualification.'
        configs.append(variant)
    bench = copy.deepcopy(next(c for c in configs if c['id']=='scout-110'))
    bench.update(id='scout-110-bench-b', name='Scout 110-B / commercial parts bench prototype',
        notes='See hardware/esp32/indoor/scout-110-bench/README.md. Single purchased BETAFPV 450 mAh pack limited to 4.2 V, UTM 8520 motors and HQProp 65 mm props. Camera-only firmware exists; flight firmware/carrier/localization and measured propulsion are outstanding. Does not inherit power-v2 mission qualification.')
    bench['components'].update(propulsion='utm8520-hq65-bench@1', battery='betafpv450-4v2-bench@1')
    configs.append(bench)
    return copy.deepcopy(components),configs
