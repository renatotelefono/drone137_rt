"""Read-only physical camera/IMU recording and calibrated offline VIO replay.

The recorder has no arm or setpoint path. A recording never certifies flight.
"""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

from hardware.esp32.link_client import AircraftLink


async def record(identity,address,output,seconds=30):
    if not 1<=seconds<=120:raise ValueError('Recording duration must be 1–120 seconds')
    profile=json.loads((Path(identity)/'pairing.json').read_text())
    folder=Path(output);folder.mkdir(parents=True,exist_ok=False)
    if shutil.disk_usage(folder).free<256*1024**2:raise ValueError('Need 256 MiB free for bounded sensor recording')
    link=AircraftLink(address,profile['certificate_sha256'],profile['credential'],'sensor-recorder')
    report=dict(version=1,device_id=profile['device_id'],kind=profile['kind'],
                armed_by_recorder=False,frames=[],imu_packets=0,imu_samples=0,complete=False,
                sensor_units='device monotonic microseconds; FLU radians/s and m/s2')
    task=None;first_imu=None;last_imu=None
    try:
        hello=await link.start()
        if hello.get('device_id')!=profile['device_id'] or hello.get('kind')!=profile['kind']:
            raise ValueError('Paired sensor identity differs')
        report['boot_id']=hello['boot_id'];report['hello']=hello
        report['clock_uncertainty_us']=link.uncertainty_us
        begin=time.monotonic();last_sync=begin
        with (folder/'imu.jsonl').open('w') as imu_log:
            async def imu_loop():
                nonlocal first_imu,last_imu
                while True:
                    packet=await link.imu()
                    imu_log.write(json.dumps(packet,allow_nan=False)+'\n');imu_log.flush()
                    report['imu_packets']+=1;report['imu_samples']+=len(packet['samples'])
                    if packet['samples']:
                        if first_imu is None:first_imu=packet['samples'][0]['time_us']
                        last_imu=packet['samples'][-1]['time_us']
                    await asyncio.sleep(.02)
            task=asyncio.create_task(imu_loop())
            while time.monotonic()-begin<seconds:
                if task.done():task.result()
                if time.monotonic()-last_sync>3:await link.synchronize();last_sync=time.monotonic()
                frame=await link.capture();pixels=frame.pop('jpeg')
                name=f'camera-{len(report["frames"])+1:05}.jpg';(folder/name).write_bytes(pixels)
                report['frames'].append(dict(frame,path=name,sha256=hashlib.sha256(pixels).hexdigest()))
                if shutil.disk_usage(folder).free<64*1024**2:raise RuntimeError('Low disk space; recording stopped')
                await asyncio.sleep(.08)
            await asyncio.sleep(.03)
            if task.done():task.result()
        report['duration_s']=time.monotonic()-begin
        report['camera_fps']=len(report['frames'])/report['duration_s']
        span=(last_imu-first_imu)/1e6 if first_imu is not None and last_imu is not None else 0
        report['imu_sensor_span_s']=span
        report['imu_hz']=(report['imu_samples']-1)/span if span>0 else None
        report['camera_fps_definition']='Received images / wall duration; includes capture and transport waits'
        report['imu_hz_definition']='Intervals / first-to-last device timestamp span; initial ring backlog does not inflate rate'
        report['complete']=bool(report['frames'] and report['imu_samples'])
    except Exception as exc:
        # Preserve useful samples without leaking headers/credentials in errors.
        report['error_type']=type(exc).__name__
        raise
    finally:
        if task:task.cancel();await asyncio.gather(task,return_exceptions=True)
        await link.close()
        imu_path=folder/'imu.jsonl'
        if imu_path.exists():report['imu_sha256']=hashlib.sha256(imu_path.read_bytes()).hexdigest()
        (folder/'recording.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return {k:v for k,v in report.items() if k not in ('frames','hello')}


def replay_inputs(recording,calibration):
    """Validate identity, provenance, ordering and continuity before native VIO."""
    folder=Path(recording);record=json.loads((folder/'recording.json').read_text())
    calibration=json.loads(Path(calibration).read_text())
    if calibration.get('device_id')!=record['device_id']:raise ValueError('Calibration belongs to another aircraft')
    if calibration.get('source_kind')!='measured' or calibration.get('passed') is not True:
        raise ValueError('Measured, passing camera/mount/timing calibration is required')
    if record.get('complete') is not True:raise ValueError('Incomplete recording is diagnostic evidence only')
    optics=calibration.get('optics',{});mount=calibration.get('mount',{})
    values=[optics.get(k) for k in ('fx','fy','cx','cy')]
    distortion=optics.get('distortion',[]);body=mount.get('body_offset_flu_m',[])
    values+=distortion+body+[mount.get('pitch_degrees'),calibration.get('launch_imu_height_m')]
    if (len(distortion)!=5 or len(body)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in values) or
            optics['fx']<=0 or optics['fy']<=0 or calibration['launch_imu_height_m']<0 or
            not -90<=mount['pitch_degrees']<=90 or
            any(type(optics.get(k)) is not int or not 1<=optics[k]<=4096 for k in ('width','height'))):
        raise ValueError('Invalid measured camera/mount calibration')
    # The current native bridge supports a level, forward camera with pitch only.
    if mount.get('roll_degrees',0)!=0 or mount.get('yaw_degrees',0)!=0:
        raise ValueError('This bridge requires forward camera yaw and zero mount roll')
    calibration['width']=optics['width'];calibration['height']=optics['height']
    offset=calibration.get('camera_to_imu_time_offset_us')
    if type(offset) not in (int,float) or not -100000<=offset<=100000:
        raise ValueError('Measured camera-to-IMU time offset is required')
    raw=(folder/'imu.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record['imu_sha256']:raise ValueError('IMU evidence changed')
    samples=[];last=-1
    for line in raw.splitlines():
        packet=json.loads(line)
        if packet['boot_id']!=record['boot_id'] or packet['overrun']:raise ValueError('Discontinuous IMU recording')
        for s in packet['samples']:
            stamp=s['time_us']
            values=s['gyro_flu_rad_s']+s['specific_force_flu_m_s2']
            if (type(stamp) is not int or stamp<0 or len(values)!=6 or
                    any(type(v) not in (int,float) or not math.isfinite(v) for v in values)):
                raise ValueError('Invalid IMU sample')
            if stamp<=last or (last>=0 and stamp-last>20000):raise ValueError('Missing or unordered IMU samples')
            last=stamp;samples.append(s)
    if not samples:raise ValueError('Empty IMU recording')
    epoch=samples[0]['time_us'];last=-1;frames=[]
    for frame in record['frames']:
        # Recording manifests cannot escape their evidence directory.
        path=(folder/frame['path']).resolve()
        if not path.is_relative_to(folder.resolve()):raise ValueError('Frame path escapes recording')
        pixels=path.read_bytes()
        if hashlib.sha256(pixels).hexdigest()!=frame['sha256']:raise ValueError('Image evidence changed')
        stamp=frame['capture_time_us']+offset
        if frame['boot_id']!=record['boot_id'] or stamp<=last:raise ValueError('Discontinuous camera recording')
        last=stamp
        if [frame['width'],frame['height']]!=[calibration['optics']['width'],calibration['optics']['height']]:
            raise ValueError('Camera calibration resolution differs')
        if stamp>=epoch:frames.append((stamp,pixels))
    if not frames:raise ValueError('No camera frames overlap the IMU recording')
    if frames[-1][0]>samples[-1]['time_us']+20000:raise ValueError('Camera outlasts IMU recording')
    return record,calibration,epoch,samples,frames


async def replay(recording,calibration,output):
    from app.visual_inertial import VisualInertial
    from app.temporal_geometry import TemporalGeometry
    from app.voxel_mapping import RaycastMap
    record,calibration,epoch,samples,frames=replay_inputs(recording,calibration)
    folder=Path(output);folder.mkdir(parents=True,exist_ok=False)
    vio=VisualInertial();mapper=RaycastMap();geometry=TemporalGeometry();cursor=0;initialized=0
    try:
        # No automatic ground constraint for hand-carried sensor recordings.
        await vio.start(calibration,folder/'vio',calibration['launch_imu_height_m'],stationary_phase=False)
        for stamp,pixels in frames:
            batch=[]
            while cursor<len(samples) and samples[cursor]['time_us']<=stamp+2000:
                s=samples[cursor];cursor+=1
                batch.append(dict(time_s=(s['time_us']-epoch)/1e6,
                                  gyro_flu=s['gyro_flu_rad_s'],specific_force_flu=s['specific_force_flu_m_s2']))
            if not batch:continue
            frame=dict(capture_time_s=(stamp-epoch)/1e6)
            result=await vio.observe(frame,pixels,dict(oldest_time_s=batch[0]['time_s'],imu=batch))
            if result and result['initialized']:
                initialized+=1
                pose={k:result[k] for k in ('time_s','position','quaternion')}
                _,transform,_,points,_=await asyncio.to_thread(geometry.observe,pixels,pose,calibration,result['landmarks'])
                if len(points):
                    evidence=await asyncio.to_thread(mapper.prepare_cloud,points,transform[:3,3])
                    mapper.integrate_prepared(evidence,transform[:3,3],pose['position'])
        report=dict(device_id=record['device_id'],source_kind=record['kind'],
                    initialized_images=initialized,images=len(frames),map=mapper.snapshot(),
                    qualified=False,note='Sensor-derived estimate; no independent physical accuracy reference.')
        (folder/'replay.json').write_text(json.dumps(report,allow_nan=False))
        return {k:v for k,v in report.items() if k!='map'}
    finally:await vio.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--recording',required=True)
    p.add_argument('--calibration',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(asyncio.run(replay(a.recording,a.calibration,a.output)),indent=2))
