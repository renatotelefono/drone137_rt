"""HTTPS software-in-loop for the real C++ controller. No physical outputs."""
import asyncio
from collections import deque
import json
import secrets
import time
from aiohttp import web
from hardware.esp32.flight_host import Firmware
from hardware.esp32.link_emulator import ROOT, tls_context


class FirmwareSIL:
    def __init__(self, profile):
        self.profile=profile
        self.core=Firmware(enabled=True,device=profile['device_id'])
        self.samples=deque(maxlen=256)
        self.control_delay=0.;self.camera_delay=0.;self.frame_age_us=0;self.freeze_imu=False
        self.channels=None;self.task=None;self.sequence=0
        self.image=(ROOT/'sim/assets/fixture-01.jpg').read_bytes()
        from adapters.esp32_camera import jpeg_dimensions
        self.width,self.height=jpeg_dimensions(self.image)
        # Synthetic stationary calibration history, never used on the aircraft.
        now=self.clock()
        for stamp in range(now-9_200_000,now,2000):self.core.imu(stamp)

    @staticmethod
    def clock(): return time.monotonic_ns()//1000

    async def sensors(self):
        while True:
            now=self.clock()
            if not self.freeze_imu:
                self.core.imu(now)
                self.samples.append(dict(time_us=now,gyro_flu_rad_s=[0.,0.,0.],
                                         specific_force_flu_m_s2=[0.,0.,9.80665]))
            self.core.tick(now)
            await asyncio.sleep(.002)

    def app(self, channel='all'):
        @web.middleware
        async def auth(request, handler):
            if not secrets.compare_digest(request.headers.get('Authorization','').encode(),
                                          ('Bearer '+self.profile['credential']).encode()):
                return web.json_response({'error':'Authentication required'},status=401)
            if channel=='control' and self.control_delay:await asyncio.sleep(self.control_delay)
            return await handler(request)
        app=web.Application(middlewares=[auth],client_max_size=1536)
        async def control(request):
            raw=await request.text() if request.method=='POST' else '{}'
            status,data=self.core.request(request.path,raw,self.clock())
            if request.path=='/v1/hello':
                data.update(kind='protocol-emulator',firmware='shared-cpp-software-in-loop',
                            physics='stationary synthetic sensors; native attitude plant tested separately',
                            mission_ready=False)
                if self.channels:data['channels']=self.channels
            return web.json_response(data,status=status,headers={'Cache-Control':'no-store'})
        async def camera(request):
            await asyncio.sleep(self.camera_delay)
            self.sequence+=1
            return web.Response(body=self.image,content_type='image/jpeg',headers={
                'X-Boot-Id':self.core.boot_id,'X-Frame-Id':str(self.sequence),
                'X-Capture-Time-Us':str(self.clock()-self.frame_age_us),
                'X-Width':str(self.width),'X-Height':str(self.height)})
        async def imu(request):
            try:
                after=int(request.query.get('after_us','0'))
                if after<0:raise ValueError()
            except ValueError:return web.json_response({'error':'Invalid IMU cursor'},status=400)
            values=list(self.samples);oldest=values[0]['time_us'] if values else 0
            return web.json_response(dict(boot_id=self.core.boot_id,clock_us=self.clock(),
                oldest_time_us=oldest,overrun=bool(after and oldest>after+20000),
                samples=[s for s in values if s['time_us']>after]))
        if channel in ('all','control'):
            app.router.add_get('/v1/hello',control);app.router.add_get('/v1/imu',imu)
            app.router.add_post('/v1/session',control);app.router.add_post('/v1/command',control)
        if channel in ('all','camera'):app.router.add_get('/v1/camera',camera)
        if channel=='emergency':app.router.add_get('/v1/hello',control)
        if channel in ('all','emergency'):app.router.add_post('/v1/emergency',control)
        return app

    async def start(self):
        self.task=asyncio.create_task(self.sensors())
        await asyncio.sleep(.01)

    async def close(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.core.close()


async def serve(identity,port):
    from pathlib import Path
    profile=json.loads((Path(identity)/'pairing.json').read_text())
    device=FirmwareSIL(profile);await device.start()
    device.channels={'camera_port':port+1,'emergency_port':port+2}
    runners=[]
    try:
        for index,channel in enumerate(('control','camera','emergency')):
            runner=web.AppRunner(device.app(channel),access_log=None);await runner.setup();runners.append(runner)
            await web.TCPSite(runner,'127.0.0.1',port+index,ssl_context=tls_context(identity)).start()
        print(json.dumps({'endpoint':f'https://127.0.0.1:{port}','kind':'protocol-emulator',
                          'firmware':'shared-cpp-software-in-loop'}),flush=True)
        await asyncio.Event().wait()
    finally:
        for runner in runners:await runner.cleanup()
        await device.close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--identity',required=True)
    p.add_argument('--port',type=int,default=8170)
    a=p.parse_args();asyncio.run(serve(a.identity,a.port))
