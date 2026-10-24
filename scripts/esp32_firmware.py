"""Provision, build, inspect and flash Scout firmware. Only explicit rig-test arms."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from hardware.esp32.link_emulator import provision as create_identity
from hardware.esp32.link_protocol import identifier

ROOT=Path(__file__).resolve().parents[1]
FQBN='esp32:esp32:XIAO_ESP32S3:PSRAM=opi'


def private_json(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2,allow_nan=False)


def provision(folder,device,network):
    identifier(device)
    wifi=json.loads(Path(network).read_text())
    if (set(wifi)!={'ssid','password'} or not isinstance(wifi['ssid'],str)
            or not 1<=len(wifi['ssid'].encode())<=32 or not isinstance(wifi['password'],str)
            or not 8<=len(wifi['password'].encode())<=63 or '\0' in wifi['ssid'] or '\0' in wifi['password']):
        raise ValueError('Network file requires ssid (1–32 bytes) and WPA password (8–63 bytes)')
    folder=Path(folder)
    profile=create_identity(folder)
    profile.update(device_id=device,kind='aircraft')
    (folder/'pairing.json').write_text(json.dumps(profile,indent=2))
    private_json(folder/'network.json',wifi)
    return {'device_id':device,'pairing_file':str((folder/'pairing.json').resolve()),
            'outputs_enabled':False,'physical_qualification':'not_run'}


def commissioning(folder,rig=False):
    path=Path(folder)/'commissioning.json'
    if not path.exists():return None
    data=json.loads(path.read_text())
    required=('electrical_inspection','motor_order_and_direction','imu_axes','battery_adc')
    required+=('restraint_verified',) if rig else ('restrained_tuning','loaded_power_and_temperature','camera_control_timing','link_loss_and_stop')
    if (data.get('device_id')!=json.loads((Path(folder)/'pairing.json').read_text())['device_id']
            or any(data.get('checks',{}).get(k) is not True for k in required)
            or not data.get('operator') or not data.get('evidence_directory')):
        raise ValueError('Physical commissioning evidence is incomplete; motor-enabled build refused')
    return data


def stage(folder,output,enable=False,bench=False,rig=False):
    folder=Path(folder);output=Path(output)
    if sum((enable,bench,rig))>1:raise ValueError('Bench, restrained rig and commissioned builds are separate modes')
    if output.exists():raise ValueError('Use a new build directory to preserve previous firmware')
    profile=json.loads((folder/'pairing.json').read_text());identifier(profile['device_id'])
    if profile.get('kind')!='aircraft':raise ValueError('Only an aircraft identity can build board firmware')
    wifi=json.loads((folder/'network.json').read_text())
    checked=commissioning(folder,rig) if enable or rig else None
    if (enable or rig) and checked is None:raise ValueError('No physical commissioning record; outputs remain disabled')
    output.mkdir(parents=True,mode=0o700)
    sketch=output/'flight';sketch.mkdir(mode=0o700)
    for source in (ROOT/'hardware/esp32/flight').iterdir():
        if source.suffix in ('.h','.ino') and source.name!='config.h':shutil.copyfile(source,sketch/source.name)
    values={'D137_DEVICE_ID':profile['device_id'],'D137_WIFI_SSID':wifi['ssid'],
            'D137_WIFI_PASSWORD':wifi['password'],'D137_CREDENTIAL':profile['credential'],
            'D137_CERTIFICATE':(folder/'device-cert.pem').read_text(),
            'D137_PRIVATE_KEY':(folder/'device-key.pem').read_text()}
    config='#pragma once\n'+''.join('#define '+k+' '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in values.items())
    scale=(checked or {}).get('battery_divider_scale',2.)
    if type(scale) not in (int,float) or not 1.8<=scale<=2.2:raise ValueError('Invalid measured divider scale')
    rotation=(checked or {}).get('imu_to_flu',[1,0,0,0,1,0,0,0,1])
    # Only right-handed signed axis permutations are supported for this mount.
    import numpy as np
    matrix=np.asarray(rotation,dtype=float).reshape(3,3)
    if not np.all(np.isin(matrix,[-1,0,1])) or not np.allclose(matrix@matrix.T,np.eye(3)) or np.linalg.det(matrix)<.99:
        raise ValueError('IMU rotation must be a right-handed signed axis permutation')
    config+=f'#define D137_PROVISIONED 1\n#define D137_OUTPUTS_ENABLED {int(enable or rig)}\n#define D137_COMMISSIONED {int(enable)}\n#define D137_VBAT_SCALE {scale}\n'
    config+=f'#define D137_BENCH_OUTPUTS {int(bench)}\n#define D137_RESTRAINED_RIG {int(rig)}\n'
    config+='static const float D137_IMU_TO_FLU[9]={'+','.join(str(int(v)) for v in matrix.flat)+'};\n'
    fd=os.open(sketch/'config.h',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(config)
    return sketch


def cli():
    path=ROOT/'.local/esp32-toolchain/bin/arduino-cli'
    executable=str(path) if path.exists() else shutil.which('arduino-cli')
    if not executable:raise RuntimeError('Install Arduino CLI and esp32 core 3.3.12 before building offline')
    args=[executable]
    config=ROOT/'.local/esp32-toolchain/arduino-cli.yaml'
    if config.exists():args+=['--config-file',str(config)]
    return args


def build(folder,output,enable=False,bench=False,rig=False):
    sketch=stage(folder,output,enable,bench,rig)
    subprocess.run(cli()+['compile','--fqbn',FQBN,'--build-path',str(Path(output)/'compiled'),str(sketch)],check=True)
    binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(output)/'compiled').glob('*.bin')}
    manifest={'device_id':json.loads((Path(folder)/'pairing.json').read_text())['device_id'],
              'fqbn':FQBN,'outputs_enabled':enable or rig,'bench_motor_tests':bench,'restrained_rig':rig,'physical_flight_qualified':False,
              'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sketch.iterdir() if p.name!='config.h'},
              'binaries_sha256':binaries,'note':'Compiled binaries contain device credentials; keep this directory private.'}
    private_json(Path(output)/'build-manifest.json',manifest)
    return manifest


async def diagnose(identity,address,output):
    from hardware.esp32.link_client import AircraftLink
    profile=json.loads((Path(identity)/'pairing.json').read_text())
    link=AircraftLink(address,profile['certificate_sha256'],profile['credential'],'commissioning-read-only')
    report={'kind':profile['kind'],'device_id':profile['device_id'],'armed_by_tool':False}
    try:
        hello=await link.start()
        if hello.get('device_id')!=profile['device_id']:raise ValueError('Paired identity differs')
        report['hello']=hello
        image=await link.capture();imu=await link.imu()
        report.update(camera_dimensions=[image['width'],image['height']],
                      camera_age_us=link.device_time()-image['capture_time_us'],
                      clock_uncertainty_us=link.uncertainty_us,imu_samples=len(imu['samples']),
                      imu_overrun=imu['overrun'],connected=True)
        folder=Path(output);folder.mkdir(parents=True,exist_ok=False)
        (folder/'camera.jpg').write_bytes(image['jpeg'])
        (folder/'diagnostic.json').write_text(json.dumps(report,indent=2))
        return report
    finally:await link.close()


async def bench_action(identity,address,output,*,motor=None,duty=.1,milliseconds=100,seconds=1.,roll=0.,pitch=0.,collective=0.):
    """Explicit operator-run bounded test; never called by Mission Control."""
    import math,time
    from hardware.esp32.link_client import AircraftLink
    if motor is not None and (not 1<=motor<=4 or not .01<=duty<=.2 or not 20<=milliseconds<=200):
        raise ValueError('Bench pulse: motor 1–4, duty .01–.20, duration 20–200 ms')
    if motor is None and (not .2<=seconds<=4 or not 0<=collective<=.65 or not abs(roll)<=8 or not abs(pitch)<=8):
        raise ValueError('Restrained test: .2–4 seconds, collective 0–.65, angles within 8 degrees')
    profile=json.loads((Path(identity)/'pairing.json').read_text())
    folder=Path(output);folder.mkdir(parents=True,exist_ok=False)
    link=AircraftLink(address,profile['certificate_sha256'],profile['credential'],'explicit-bench-tool')
    report=dict(device_id=profile['device_id'],kind=profile['kind'],test='motor-pulse' if motor is not None else 'restrained-attitude',qualified=False,telemetry=[])
    connected=False
    try:
        hello=await link.start()
        if hello['device_id']!=profile['device_id'] or hello.get('kind')!=profile['kind']:raise ValueError('Device identity differs')
        if not hello.get('bench_motor_tests' if motor is not None else 'restrained_rig'):
            raise ValueError('Matching propeller-free or restrained-rig firmware is required')
        await link.claim();connected=True
        if motor is not None:
            await link.command('motor_test',motor=motor-1,duty=duty,duration_ms=milliseconds)
            await asyncio.sleep(milliseconds/1000+.05)
            report.update(motor=motor,duty=duty,duration_ms=milliseconds)
        else:
            await link.command('arm');begin=time.monotonic();next_sample=begin
            while time.monotonic()-begin<seconds:
                await link.command('attitude',setpoint=dict(roll_rad=math.radians(roll),pitch_rad=math.radians(pitch),yaw_rate_rad_s=0,thrust=collective))
                if time.monotonic()>=next_sample:
                    report['telemetry'].append(await link.request('/v1/hello'));next_sample=time.monotonic()+.25
                await asyncio.sleep(.04)
            report.update(seconds=seconds,collective=collective,roll_deg=roll,pitch_deg=pitch)
        report['completed']=True
    except Exception as exc:
        report['error_type']=type(exc).__name__;raise
    finally:
        if connected:
            try:report['stop']=await link.emergency('disarm')
            except Exception as exc:report['stop_error_type']=type(exc).__name__
        await link.close();(folder/'bench-result.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('provision');s.add_argument('--identity',required=True);s.add_argument('--device',required=True);s.add_argument('--network-file',required=True)
    s=sub.add_parser('build');s.add_argument('--identity',required=True);s.add_argument('--output',required=True);s.add_argument('--enable-commissioned-motors',action='store_true');s.add_argument('--propeller-free-bench',action='store_true');s.add_argument('--restrained-rig',action='store_true')
    s=sub.add_parser('flash');s.add_argument('--build',required=True);s.add_argument('--port',required=True)
    s=sub.add_parser('diagnose');s.add_argument('--identity',required=True);s.add_argument('--address',required=True);s.add_argument('--output',required=True)
    s=sub.add_parser('record');s.add_argument('--identity',required=True);s.add_argument('--address',required=True);s.add_argument('--output',required=True);s.add_argument('--seconds',type=float,default=30)
    s=sub.add_parser('motor-test');s.add_argument('--identity',required=True);s.add_argument('--address',required=True);s.add_argument('--output',required=True);s.add_argument('--motor',type=int,required=True);s.add_argument('--duty',type=float,default=.1);s.add_argument('--milliseconds',type=int,default=100);s.add_argument('--propellers-removed',action='store_true',required=True)
    s=sub.add_parser('rig-test');s.add_argument('--identity',required=True);s.add_argument('--address',required=True);s.add_argument('--output',required=True);s.add_argument('--seconds',type=float,default=1);s.add_argument('--collective',type=float,default=0);s.add_argument('--roll-deg',type=float,default=0);s.add_argument('--pitch-deg',type=float,default=0);s.add_argument('--restraint-confirmed',action='store_true',required=True)
    a=p.parse_args()
    if a.action=='provision':result=provision(a.identity,a.device,a.network_file)
    elif a.action=='build':result=build(a.identity,a.output,a.enable_commissioned_motors,a.propeller_free_bench,a.restrained_rig)
    elif a.action=='diagnose':result=asyncio.run(diagnose(a.identity,a.address,a.output))
    elif a.action=='motor-test':result=asyncio.run(bench_action(a.identity,a.address,a.output,motor=a.motor,duty=a.duty,milliseconds=a.milliseconds))
    elif a.action=='rig-test':result=asyncio.run(bench_action(a.identity,a.address,a.output,seconds=a.seconds,collective=a.collective,roll=a.roll_deg,pitch=a.pitch_deg))
    elif a.action=='record':
        from hardware.esp32.sensor_recording import record
        result=asyncio.run(record(a.identity,a.address,a.output,a.seconds))
    else:
        folder=Path(a.build);manifest=json.loads((folder/'build-manifest.json').read_text())
        if manifest.get('fqbn')!=FQBN or 'flight.ino.bin' not in manifest.get('binaries_sha256',{}):raise ValueError('Unexpected firmware manifest')
        for name,digest in manifest['binaries_sha256'].items():
            if Path(name).name!=name:raise ValueError('Invalid firmware path')
            if hashlib.sha256((folder/'compiled'/name).read_bytes()).hexdigest()!=digest:raise ValueError('Firmware binary changed after build')
        subprocess.run(cli()+['upload','--fqbn',FQBN,'--port',a.port,'--input-dir',str(folder/'compiled')],check=True)
        result={'flashed':True,'outputs_enabled':manifest['outputs_enabled'],'flight_qualified':False}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
