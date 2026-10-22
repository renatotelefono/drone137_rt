"""PX4/Gazebo flight-test session. No physical transport and no model motor commands."""
import asyncio
import importlib.util
import json
import math
import os
import socket
import random
from collections import deque
from pathlib import Path
import time
from adapters.mavsdk_drone import MavsdkDrone
from app.native import unused_port
from app.watchdog import ProcessSupervisor
from sim.flight_world import HOME, clear, route, sdf
from scripts.tools import ROOT, BUILD


def quaternion(roll,pitch,yaw):
    cr,sr,cp,sp,cy,sy=math.cos(roll/2),math.sin(roll/2),math.cos(pitch/2),math.sin(pitch/2),math.cos(yaw/2),math.sin(yaw/2)
    return [sr*cp*cy-cr*sp*sy,cr*sp*cy+sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy]


def rotate(q,v):
    x,y,z,w=q
    tx,ty,tz=2*(y*v[2]-z*v[1]),2*(z*v[0]-x*v[2]),2*(x*v[1]-y*v[0])
    return [v[0]+w*tx+y*tz-z*ty,v[1]+w*ty+z*tx-x*tz,v[2]+w*tz+x*ty-y*tx]


def preflight_settled(health, telemetry, local_position=False):
    # MAVSDK's aggregate armable field includes global/home health. The actual
    # PX4 arm command still runs every firmware arming check in GPS-free mode.
    sensors_ok=(health.is_gyrometer_calibration_ok and health.is_accelerometer_calibration_ok
                and health.is_magnetometer_calibration_ok) if local_position else health.is_armable
    return (sensors_ok and health.is_local_position_ok and telemetry.healthy
            and not telemetry.in_air and abs(telemetry.position[2])<.25 and telemetry.speed<.12)


def takeoff_confirmed(telemetry):
    # A high altitude estimate alone can occur while PX4 still reports landed.
    return telemetry.healthy and telemetry.in_air and telemetry.position[2]>=1.3


async def configure_float_parameters(param, desired, check):
    """A lost write acknowledgement is acceptable only after matching readback."""
    from mavsdk.param import ParamError, ParamResult
    actual={}
    for name,value in desired.items():
        for attempt in range(3):
            check()
            try:await param.set_param_float(name,value)
            except ParamError as e:
                if e._result.result!=ParamResult.Result.TIMEOUT:raise
            try:readback=await param.get_param_float(name)
            except ParamError as e:
                if e._result.result!=ParamResult.Result.TIMEOUT or attempt==2:raise
            else:
                if math.isfinite(readback) and math.isclose(readback,value,rel_tol=1e-5,abs_tol=1e-6):
                    actual[name]=readback;break
                if attempt==2:raise RuntimeError(f'PX4 parameter readback mismatch: {name} requested {value}, received {readback}')
            await asyncio.sleep(.25)
    return actual


class NativeFlight:
    def __init__(self, scene, folder, watch):
        self.scene,self.folder,self.watch=scene,Path(folder),watch
        self.home=scene.get('home',HOME)
        self.observed=scene.get('navigation_mode')=='observed-range'
        self.profile=scene.get('hardware',{}).get('profile')
        self.owned=ProcessSupervisor();self.drone=MavsdkDrone(speed_limit=self.profile['limits']['speed_m_s'] if self.profile else .6,local_position=self.observed)
        self.truth=None;self.truth_at=0;self.attitude=None;self.attitude_at=0
        self.phase='starting';self.message='Connecting to native simulator';self.trail=[];self.samples=[];self.tasks=[]
        self.goal=None;self.motion=False;self.failed=None;self.angular_speed=0;self.monitor_error=None
        self.angular_velocity_flu=[0,0,0];self.sensor_events=[];self.odometry_at=0;self.odometry_sigma=0;self.airborne_at=None
        self.fault_states={};self.landed=False
        self.nav=None
        if self.observed:
            from app.observed_navigation import ObservedNavigation
            from sim.range_sensor import RangeSensor
            self.nav=ObservedNavigation(scene['width'],scene['depth'],self.home,self.profile['airframe']['body_radius_m'],self.profile['limits']['clearance_margin_m']+.08,
                braking_acceleration=self.profile['limits']['acceleration_m_s2'])
            self.range_sensor=RangeSensor(scene,self.profile['sensors'])

    def estimated(self):
        t=self.drone.telemetry()
        return {'position':[t.position[0]+self.home[0],t.position[1]+self.home[1],t.position[2]+.24],
                'quaternion':self.attitude,'received_monotonic':t.received_monotonic,'attitude_monotonic':self.attitude_at}

    def snapshot(self):
        return {'truth':self.truth,'estimated':self.estimated(),'wall_time':time.time()-(time.monotonic()-self.truth_at),
                'phase':self.phase,'message':self.message,'speed':self.drone.telemetry().speed,
                'angular_speed':self.angular_speed,'angular_velocity_flu':self.angular_velocity_flu,'trail':self.trail[-1500:]}

    async def start(self):
        unused_port(50051)
        for port in (14540,14580):
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                try:sock.bind(('127.0.0.1',port))
                except OSError as e:raise RuntimeError(f'SITL UDP port {port} is already occupied') from e
        px4=BUILD/'PX4-Autopilot';models=px4/'Tools/simulation/gz/models'
        native_world=sdf(self.scene,px4,self.folder/'world.sdf')
        env=dict(os.environ);env.pop('DRONE137_OWNERSHIP_FILE',None)
        env.update(PX4_GZ_WORLD='dense_workshop',HEADLESS='1',PX4_GZ_STANDALONE='1',
            PX4_GZ_MODEL_NAME='x500_0',PX4_GZ_NO_FOLLOW='1',GZ_IP='127.0.0.1',
            PX4_SIM_MODEL='gz_x500',GZ_SIM_RESOURCE_PATH=str(models),
            GZ_SIM_SYSTEM_PLUGIN_PATH=str(px4/'build/px4_sitl_default/src/modules/simulation/gz_plugins'))
        if self.observed:
            # Applied by the pinned PX4 rcS before EKF2 starts, including parameters
            # that require reboot. No GNSS sensor exists in this generated model.
            for k,v in {'SYS_HAS_GPS':0,'SIM_GPS_USED':0,'EKF2_GPS_CTRL':0,'EKF2_EV_CTRL':11,
                        'EKF2_HGT_REF':3,'EKF2_EV_DELAY':self.profile['sensors']['position_delay_ms'],
                        'COM_ARM_WO_GPS':1}.items():env['PX4_PARAM_'+k]=str(v)
        self.env=env
        await self.owned.spawn('gazebo',[str(ROOT/'scripts/with-sim.sh'),'gz','sim','-r','-s',str(native_world)],self.folder/'gazebo.log',env=env)
        workspace=self.folder/'px4';workspace.mkdir();
        await self.owned.spawn('px4',[str(ROOT/'scripts/with-sim.sh'),str(px4/'build/px4_sitl_default/bin/px4'),'-d','-w',str(workspace),str(px4/'build/px4_sitl_default/etc')],self.folder/'px4.log',env=env)
        spec=importlib.util.find_spec('mavsdk');sdk=Path(spec.origin).parent/'bin/mavsdk_server'
        await self.owned.spawn('mavsdk',[str(sdk),'-p','50051','udpin://127.0.0.1:14540'],self.folder/'mavsdk.log',env=env)
        self.bridge=await asyncio.create_subprocess_exec(str(ROOT/'scripts/with-sim.sh'),str(BUILD/'image-bridge/drone137-pose-bridge'),'/model/x500_0/pose','x500_0',stdout=asyncio.subprocess.PIPE,env=env,start_new_session=True)
        async def read_truth():
            while line:=await self.bridge.stdout.readline():
                value=json.loads(line)
                if self.truth and value['sim_time']<=self.truth['sim_time']:continue
                self.truth=value;self.truth_at=time.monotonic()
                # x500's merged base frame is 0.24 m above its model origin.
                self.truth['model_position']=self.truth['position']
                offset=rotate(self.truth['quaternion'],[0,0,.24])
                self.truth['position']=[a+b for a,b in zip(self.truth['position'],offset)]
            raise RuntimeError('Ground-truth renderer bridge ended')
        self.tasks.append(asyncio.create_task(read_truth()))
        async def connected():
            if self.observed:self.tasks.append(asyncio.create_task(self.send_odometry()))
        connecting=asyncio.create_task(self.drone.connect(connected))
        try:
            while not connecting.done():
                if not self.owned.healthy():raise RuntimeError('Native startup failed; inspect PX4/Gazebo logs')
                self.watch.check();await asyncio.sleep(.2)
            await connecting
        finally:
            if not connecting.done():
                connecting.cancel();await asyncio.gather(connecting,return_exceptions=True)
        await self.drone.system.telemetry.set_rate_position_velocity_ned(20)
        await self.drone.system.telemetry.set_rate_attitude_euler(20)
        async def attitude():
            async for a in self.drone.system.telemetry.attitude_euler():
                now=time.monotonic();q=quaternion(math.radians(a.roll_deg),-math.radians(a.pitch_deg),math.pi/2-math.radians(a.yaw_deg))
                if self.attitude:
                    dot=min(1,abs(sum(x*y for x,y in zip(q,self.attitude))))
                    self.angular_speed=2*math.acos(dot)/max(.01,now-self.attitude_at)
                    # Quaternion delta in body FLU, for signed rotational exposure.
                    x,y,z,w=self.attitude;u,v,r,s=q
                    delta=[w*u-x*s-y*r+z*v,w*v+x*r-y*s-z*u,w*r-x*v+y*u-z*s,w*s+x*u+y*v+z*r]
                    sign=1 if delta[3]>=0 else -1
                    self.angular_velocity_flu=[2*sign*d/max(.01,now-self.attitude_at) for d in delta[:3]]
                self.attitude,self.attitude_at=q,now
        self.tasks.append(asyncio.create_task(attitude()))
        async with asyncio.timeout(20):
            while self.truth is None or self.attitude is None:await asyncio.sleep(.1)
        speed=self.profile['limits']['speed_m_s'] if self.profile else .6
        acceleration=self.profile['limits']['acceleration_m_s2'] if self.profile else .8
        self.parameters=await configure_float_parameters(self.drone.system.param,
            {'MPC_XY_VEL_MAX':speed+.05,'MPC_XY_CRUISE':speed,'MPC_ACC_HOR':acceleration,'MPC_ACC_HOR_MAX':1.2,'MPC_JERK_MAX':2.0,'MIS_TAKEOFF_ALT':1.5},self.check)
        if self.observed:
            self.parameters.update({name:await self.drone.system.param.get_param_int(name) for name in ('EKF2_GPS_CTRL','EKF2_EV_CTRL','SYS_HAS_GPS')})
            if self.parameters['EKF2_GPS_CTRL']!=0 or self.parameters['EKF2_EV_CTRL']!=11:raise RuntimeError('GPS-denied estimator configuration not active')
        self.phase='ready'
        async def monitor():
            try:
                while True:
                    self.check()
                    t=self.drone.telemetry();est=self.estimated();truth=self.truth
                    if self.nav and not self.fault_active('range'):
                        ranges=await asyncio.to_thread(self.range_sensor.scan,truth,time.monotonic())
                        forward=rotate(est['quaternion'],[1,0,0]);yaw=math.atan2(forward[1],forward[0])
                        await asyncio.to_thread(self.nav.integrate,[*est['position'][:2],yaw],ranges,time.monotonic())
                    self.samples.append({'host_time':time.monotonic(),'sim_time':truth['sim_time'],
                        'phase':self.phase,'truth':truth,'estimated':est,'speed':t.speed,'goal':self.goal,
                        'clearance_m':clear(self.scene,truth['position']),
                        'position_error_m':math.dist(est['position'],truth['position'])})
                    self.trail.append(truth['position'][:2]);await asyncio.sleep(.1)
            except Exception as e:
                self.monitor_error=repr(e)
                # Stop movement immediately on stale data / budget / boundary failures.
                if self.motion:
                    try:await self.drone.hold()
                    except Exception:pass
        self.tasks.append(asyncio.create_task(monitor()))

    def fault_active(self,kind):
        elapsed=0 if self.airborne_at is None else time.monotonic()-self.airborne_at
        active=any(f['sensor']==kind and f['start_s']<=elapsed<f['start_s']+f['duration_s'] for f in self.scene.get('sensor_faults',[]))
        if active!=self.fault_states.get(kind,False):
            self.sensor_events.append({'event':'fault-start' if active else 'fault-end','sensor':kind,'airborne_seconds':elapsed,'time':time.monotonic()})
        self.fault_states[kind]=active
        return active

    async def send_odometry(self):
        """Explicit synthetic odometry sensor, not image-derived VIO.

        This isolated adapter may read truth. PX4 and the policy receive only a
        delayed noisy measurement with reported covariance, never exact pose.
        """
        from mavsdk.mocap import VisionPositionEstimate,PositionBody,AngleBody,Covariance
        rng=random.Random(self.scene['seed']+719);history=deque(maxlen=16);origin=None;last=-1
        sensors=self.profile['sensors'];start=time.monotonic()
        while True:
            now=time.monotonic();truth=self.truth
            if truth and truth['sim_time']!=last:
                last=truth['sim_time'];history.append((now,truth))
            eligible=[item for item in history if now-item[0]>=sensors['position_delay_ms']/1000]
            if eligible and not self.fault_active('odometry'):
                captured,t=eligible[-1];elapsed=now-start;sigma=sensors['position_noise_m']+sensors['drift_m_per_s']*elapsed
                drift=sensors['drift_m_per_s']*elapsed
                pos=[t['position'][0]-self.home[0]+drift+rng.gauss(0,sensors['position_noise_m']),
                     t['position'][1]-self.home[1]-drift*.4+rng.gauss(0,sensors['position_noise_m']),
                     t['position'][2]-.24+rng.gauss(0,sensors['position_noise_m'])]
                x,y,z,w=t['quaternion'];roll=math.atan2(2*(w*x+y*z),1-2*(x*x+y*y));pitch=math.asin(max(-1,min(1,2*(w*y-z*x))));yaw=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
                covariance=[0.]*21
                for i in (0,6,11):covariance[i]=sigma*sigma
                for i in (15,18,20):covariance[i]=.01**2
                await self.drone.system.mocap.set_vision_position_estimate(VisionPositionEstimate(0,
                    PositionBody(pos[1],pos[0],-pos[2]),AngleBody(roll,-pitch,math.pi/2-yaw),Covariance(covariance),0))
                self.odometry_at=now;self.odometry_sigma=sigma
            await asyncio.sleep(.05)

    def check(self):
        self.watch.check()
        if self.monitor_error:raise RuntimeError(self.monitor_error)
        if self.profile and self.airborne_at is not None and self.phase not in ('landed','landing') and time.monotonic()-self.airborne_at>self.profile['limits']['mission_seconds']:
            raise RuntimeError('Frozen hardware mission time budget exceeded')
        if not self.owned.healthy():raise RuntimeError('Native simulator process failed')
        if time.monotonic()-self.truth_at>.6:raise RuntimeError('Simulator truth stale')
        t=self.drone.telemetry()
        if not t.healthy or time.monotonic()-t.received_monotonic>.6 or time.monotonic()-self.attitude_at>.6:
            raise RuntimeError('Estimator telemetry stale')
        if self.motion and not self.observed and clear(self.scene,self.estimated()['position'])<.38:
            raise RuntimeError('Estimated vehicle envelope entered obstacle margin')
        for task in self.tasks:
            if task.done() and not task.cancelled():task.result()

    async def setpoint(self, p, yaw):
        from mavsdk.offboard import PositionNedYaw
        await self.drone.system.offboard.set_position_ned(PositionNedYaw(p[1]-self.home[1],p[0]-self.home[0],-(p[2]-.24),(90-math.degrees(yaw))%360))
        self.goal=[*p,yaw]

    async def takeoff(self):
        self.phase='preflight'
        from mavsdk.action import ActionError,ActionResult
        await self.drone.system.action.set_takeoff_altitude(1.5)
        if self.observed:
            # Select local Offboard while disarmed. The generic auto/hold mode
            # may require a global origin even when the local estimator is ready.
            await self.setpoint(self.estimated()['position'],math.pi/2)
            await asyncio.sleep(1.1)
            await self.drone.system.offboard.start()
        # PX4 can temporarily deny arming while its altitude estimator converges.
        # Keep all checks enabled and let PX4 decide; never force-arm.
        stable_since=None
        async with asyncio.timeout(60):
            while True:
                await asyncio.sleep(.1)
                health=self.drone.latest_health
                if health is None:continue
                self.check()
                telemetry=self.drone.telemetry()
                # An instant armable flag is insufficient while height is
                # converging. Use estimator data only, never simulator truth.
                if not preflight_settled(health,telemetry,self.observed):
                    stable_since=None;continue
                stable_since=stable_since or time.monotonic()
                if time.monotonic()-stable_since<5:continue
                try:
                    await self.drone.system.action.arm();break
                except ActionError as e:
                    if e._result.result != ActionResult.Result.COMMAND_DENIED:raise
                    stable_since=None
                    await asyncio.sleep(2)
        self.phase='takeoff'
        self.motion=True
        if self.observed:await self.setpoint([*self.home,1.74],math.pi/2)
        else:await self.drone.system.action.takeoff()
        try:
            async with asyncio.timeout(35):
                while not takeoff_confirmed(self.drone.telemetry()):self.check();await asyncio.sleep(.1)
        except TimeoutError as e:
            raise TimeoutError('PX4 did not confirm airborne takeoff at the requested height') from e
        self.airborne_at=time.monotonic()
        await self.setpoint([*self.home,1.5],math.pi/2)
        if not self.observed:await self.drone.system.offboard.start()
        await self.reach([*self.home,1.5],math.pi/2)
        if self.nav:await asyncio.sleep(1)

    async def reach(self, p, yaw, tolerance=.18):
        await self.setpoint(p,yaw);stable=None
        async with asyncio.timeout(50):
            while True:
                self.check();est=self.estimated();forward=rotate(est['quaternion'],[1,0,0]);a=math.atan2(forward[1],forward[0])
                if self.nav and self.phase=='transit':
                    if (time.monotonic()-self.odometry_at>.35 or self.odometry_sigma>self.profile['sensors']['max_position_sigma_m']
                        or time.monotonic()-self.nav.last>.35
                        or (math.dist(est['position'][:2],p[:2])>.2 and not self.nav.motion_clear(est['position'],p,self.drone.telemetry().speed,time.monotonic()))):
                        await self.setpoint(est['position'],a)
                        self.sensor_events.append({'event':'hold','time':time.monotonic(),'reason':'Range/position freshness or clearance'})
                        async with asyncio.timeout(3):
                            while True:
                                self.check()
                                if (time.monotonic()-self.odometry_at<.35 and time.monotonic()-self.nav.last<.35
                                    and self.odometry_sigma<=self.profile['sensors']['max_position_sigma_m']
                                    and (math.dist(self.estimated()['position'][:2],p[:2])<=.2 or self.nav.motion_clear(self.estimated()['position'],p,0,time.monotonic()))):break
                                await asyncio.sleep(.1)
                        self.sensor_events.append({'event':'resume','time':time.monotonic()})
                        await self.setpoint(p,yaw);stable=None
                yaw_error=abs(math.atan2(math.sin(a-yaw),math.cos(a-yaw)))
                if math.dist(est['position'],p)<tolerance and self.drone.telemetry().speed<.14 and yaw_error<.09:
                    stable=stable or time.monotonic()
                    if time.monotonic()-stable>.5:break
                else:stable=None
                await asyncio.sleep(.1)

    async def fly(self, pose):
        self.phase='transit'
        if getattr(self,'nav',None):
            async with asyncio.timeout(self.profile['limits']['mission_seconds']):
                for _ in range(180):
                    self.check();position=self.estimated()['position']
                    if math.dist(position[:2],pose[:2])<.18:
                        await self.reach(pose[:3],pose[3]);break
                    async with asyncio.timeout(3):
                        while time.monotonic()-self.nav.last>.35:await asyncio.sleep(.1)
                    # Stop-and-scan allows contradictory cells from a delayed,
                    # noisy turn to clear before declaring the route unavailable.
                    # Clearance is unchanged; no unobserved cell is traversed.
                    for attempt in range(16):
                        try:
                            point=await asyncio.to_thread(self.nav.next_step,self.estimated()['position'],pose);break
                        except RuntimeError:
                            if attempt==15:raise
                            await asyncio.sleep(.15);self.check()
                    await self.reach([*point,pose[2]],pose[3],tolerance=.05)
                else:raise RuntimeError('Observed-map route exceeded finite step budget')
            self.phase='inspection';self.check();return
        # Dense-map A* can take >0.5 s. Keep pose readers and the watchdog live
        # while PX4 holds the last setpoint; never relax freshness to hide stalls.
        points=await asyncio.to_thread(route,self.scene,self.estimated()['position'],pose)
        for xy in points:await self.reach([*xy,pose[2]],pose[3])
        self.phase='inspection';self.check()

    def can_inspect(self, candidate):
        if self.nav:return self.nav.segment(self.estimated()['position'],candidate)
        return clear(self.scene,candidate)>.65

    async def return_land(self):
        self.phase='return'
        await self.fly([*self.home,1.5,math.pi/2]);self.phase='landing'
        # MAVSDK offboard.stop() requests global Hold, unavailable without a
        # global origin. PX4 accepts Land directly from local Offboard.
        if not self.observed:await self.drone.system.offboard.stop()
        await self.drone.land()
        self.motion=False;self.phase='landed';self.landed=True

    async def close(self):
        if self.motion:
            try:
                await asyncio.wait_for(self.drone.land(),35)
                self.landed=True;self.motion=False;self.phase='landed'
            except Exception as e:self.failed='Emergency landing unconfirmed: '+repr(e)
        for t in self.tasks:t.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.drone.close()
        if getattr(self,'bridge',None) and self.bridge.returncode is None:
            self.bridge.terminate();await self.bridge.wait()
        await self.owned.close()
        (self.folder/'flight.json').write_text(json.dumps({'parameters':getattr(self,'parameters',{}),'samples':self.samples,'cleanup_error':self.failed,'monitor_error':self.monitor_error,
            'landed':self.landed,'navigation':self.nav.report() if self.nav else None,'sensor_events':self.sensor_events,'hardware':self.scene.get('hardware')}))
