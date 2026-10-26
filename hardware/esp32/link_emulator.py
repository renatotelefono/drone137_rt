"""Local HTTPS aircraft-protocol emulator, explicitly without flight dynamics."""
import argparse
import asyncio
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess

from aiohttp import web

from hardware.esp32.link_protocol import AircraftProtocol, ProtocolError, integer

ROOT=Path(__file__).resolve().parents[2]


def provision(folder):
    """Create a unique local emulator identity; never overwrite paired keys."""
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=False,mode=0o700)
    key,cert=folder/'device-key.pem',folder/'device-cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1',
        '-nodes','-keyout',str(key),'-out',str(cert),'-days','365','-subj','/CN=drone137-emulator'],
        check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    key.chmod(0o600)
    der=ssl.PEM_cert_to_DER_cert(cert.read_text())
    profile={'device_id':'emulator-'+secrets.token_hex(4),'credential':secrets.token_urlsafe(32),
             'certificate_sha256':hashlib.sha256(der).hexdigest(),'kind':'protocol-emulator'}
    fd=os.open(folder/'pairing.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(profile,f,indent=2)
    return profile


def tls_context(folder):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(Path(folder)/'device-cert.pem'),str(Path(folder)/'device-key.pem'))
    return context


class AircraftEmulator:
    def __init__(self,profile,*,clock=None):
        self.profile=profile
        self.core=AircraftProtocol(profile['device_id'],clock,flight_enabled=True)
        self.frames=0
        self.samples=deque(maxlen=256)
        self.freeze_imu=False
        self.camera_delay=0.
        self.frame_age_us=0
        self.replay_frame=False
        self.last_frame=None
        self.task=None
        self.image=(ROOT/'sim/assets/fixture-01.jpg').read_bytes()
        from adapters.esp32_camera import jpeg_dimensions
        self.width,self.height=jpeg_dimensions(self.image)

    async def sensors(self):
        # Samples are timed like a firmware IMU interrupt, 5 ms apart on the device clock, so a
        # busy request loop delays their delivery but never opens a gap in the stream.
        next_us=None
        while True:
            now=self.core.clock()
            if self.freeze_imu:
                next_us=None
            else:
                if next_us is None or now-next_us>200_000:
                    next_us=now
                while next_us<=now:
                    self.samples.append({'time_us':next_us,'gyro_flu_rad_s':[0.,0.,0.],
                                         'specific_force_flu_m_s2':[0.,0.,9.81]})
                    next_us+=5_000
                self.core.sensor_health(calibrated=True,voltage_v=4.,imu_time_us=self.samples[-1]['time_us'])
            self.core.tick()
            await asyncio.sleep(.005)

    def app(self):
        @web.middleware
        async def authenticate(request,handler):
            expected='Bearer '+self.profile['credential']
            if not secrets.compare_digest(request.headers.get('Authorization','').encode(),expected.encode()):
                return web.json_response({'error':'Aircraft authentication required'},status=401)
            try:return await handler(request)
            except (ProtocolError,ValueError) as exc:
                return web.json_response({'error':str(exc)},status=getattr(exc,'status',400))
        app=web.Application(middlewares=[authenticate],client_max_size=4096)
        async def hello(request):
            return web.json_response({**self.core.hello(),'kind':'protocol-emulator',
                'physics':'none','camera':'static fixture','imu':'stationary synthetic samples'},
                headers={'Cache-Control':'no-store'})
        async def claim(request):
            body=await request.json()
            if not isinstance(body,dict) or set(body)!={'client_id'}:raise ProtocolError('Invalid session request')
            return web.json_response(self.core.claim(body['client_id']))
        async def command(request):return web.json_response(self.core.command(await request.json()))
        async def emergency(request):return web.json_response(self.core.emergency(await request.json()))
        async def imu(request):
            try:after=integer(int(request.query.get('after_us','0')),'IMU cursor')
            except ValueError as exc:raise ProtocolError('Invalid IMU cursor') from exc
            values=list(self.samples)
            oldest=values[0]['time_us'] if values else None
            return web.json_response({'boot_id':self.core.boot_id,'clock_us':self.core.clock(),
                'oldest_time_us':oldest,'overrun':bool(after and oldest and oldest>after+20_000),
                'samples':[s for s in values if s['time_us']>after]})
        async def camera(request):
            await asyncio.sleep(self.camera_delay)
            if not self.replay_frame or not self.last_frame:
                self.frames+=1
                self.last_frame=(self.frames,self.core.clock()-self.frame_age_us)
            sequence,capture=self.last_frame
            return web.Response(body=self.image,content_type='image/jpeg',headers={
                'Cache-Control':'no-store','X-Boot-Id':self.core.boot_id,'X-Frame-Id':str(sequence),
                'X-Capture-Time-Us':str(capture),'X-Width':str(self.width),'X-Height':str(self.height)})
        async def startup(app):self.task=asyncio.create_task(self.sensors())
        async def cleanup(app):
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
        app.on_startup.append(startup);app.on_cleanup.append(cleanup)
        app.router.add_get('/v1/hello',hello)
        app.router.add_post('/v1/session',claim)
        app.router.add_post('/v1/command',command)
        app.router.add_post('/v1/emergency',emergency)
        app.router.add_get('/v1/imu',imu)
        app.router.add_get('/v1/camera',camera)
        return app


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identity',type=Path,required=True)
    p.add_argument('--provision',action='store_true')
    p.add_argument('--port',type=int,default=8160)
    args=p.parse_args()
    profile=provision(args.identity) if args.provision else json.loads((args.identity/'pairing.json').read_text())
    print(json.dumps({'endpoint':f'https://127.0.0.1:{args.port}',
        'device_id':profile['device_id'],'certificate_sha256':profile['certificate_sha256'],
        'pairing_file':str((args.identity/'pairing.json').resolve()),'kind':'protocol-emulator'}),flush=True)
    web.run_app(AircraftEmulator(profile).app(),host='127.0.0.1',port=args.port,
                ssl_context=tls_context(args.identity),access_log=None)


if __name__=='__main__':main()
