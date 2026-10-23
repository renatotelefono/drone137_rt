"""Pinned-TLS adapter for the Drone137 aircraft protocol; no cloud dependency."""
import asyncio
import ipaddress
import re
import time
from urllib.parse import urlsplit

import aiohttp

from hardware.esp32.link_protocol import MAX_DEADLINE_US, ProtocolError


def endpoint(value):
    if not isinstance(value,str):raise ValueError('Aircraft address must be HTTPS')
    url=urlsplit(value)
    try:
        ip=ipaddress.ip_address(url.hostname or '')
        private=(ip.version==4 and (ip.is_loopback or any(ip in ipaddress.ip_network(n)
                  for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))))
        port=url.port
    except ValueError:private=False
    if (not private or url.scheme!='https' or url.path not in ('','/')
            or url.query or url.fragment or url.username or url.password):
        raise ValueError('Use a literal private IPv4 HTTPS aircraft address')
    return value.rstrip('/')


class AircraftLink:
    def __init__(self,url,fingerprint,credential,client_id,clock=None):
        self.url=endpoint(url)
        if not isinstance(fingerprint,str) or not re.fullmatch('[a-fA-F0-9]{64}',fingerprint):
            raise ValueError('Expected SHA-256 certificate fingerprint')
        if not isinstance(credential,str) or len(credential)<32 or '\n' in credential or '\r' in credential:
            raise ValueError('Expected a per-aircraft pairing credential')
        self.fingerprint=aiohttp.Fingerprint(bytes.fromhex(fingerprint))
        self.credential=credential
        self.client_id=client_id
        self.clock=clock or (lambda:time.monotonic_ns()//1000)
        self.session=None
        self.camera_session=self.emergency_session=None
        self.boot_id=self.session_id=None
        self.offset_us=self.uncertainty_us=None
        self.sequence=0
        self.lock=asyncio.Lock()
        self.last_clock_sync_us=None
        self.last_frame=None
        self.last_imu_us=0

    async def start(self):
        if self.session:raise RuntimeError('Aircraft link is already open')
        def client(limit):
            return aiohttp.ClientSession(trust_env=False,
                timeout=aiohttp.ClientTimeout(total=3),auto_decompress=False,
                headers={'Authorization':'Bearer '+self.credential},
                connector=aiohttp.TCPConnector(limit=limit))
        self.session=client(2)
        self.camera_session=client(1)
        self.emergency_session=client(1)
        try:return await self.synchronize()
        except BaseException:
            await self.close()
            raise

    async def request(self,path,body=None,*,emergency=False):
        method='GET' if body is None else 'POST'
        client=self.emergency_session if emergency else self.session
        async with client.request(method,self.url+path,json=body,
                    ssl=self.fingerprint,allow_redirects=False) as response:
            data=bytearray()
            async for chunk in response.content.iter_chunked(8192):
                data.extend(chunk)
                if len(data)>65_536:raise ProtocolError('Oversized aircraft response')
            import json
            try:value=json.loads(data)
            except (ValueError,UnicodeError) as exc:raise ProtocolError('Invalid aircraft response') from exc
            if not isinstance(value,dict):raise ProtocolError('Expected an aircraft object')
            if response.status!=200:
                raise ProtocolError(str(value.get('error','Aircraft request failed'))[:200],response.status)
            return value

    async def synchronize(self):
        measurements=[]
        for _ in range(4):
            sent=self.clock();hello=await self.request('/v1/hello');received=self.clock()
            if hello.get('protocol')!=1 or not re.fullmatch('[a-f0-9]{32}',str(hello.get('boot_id',''))):
                raise ProtocolError('Unsupported aircraft identity/protocol')
            stamp=hello.get('clock_us')
            if type(stamp) is not int or stamp<0 or received<sent:raise ProtocolError('Invalid aircraft clock')
            if self.boot_id and hello['boot_id']!=self.boot_id:
                self.session_id=None
                raise ProtocolError('Aircraft rebooted; reconnect and review mission',409)
            self.boot_id=hello['boot_id']
            measurements.append(((received-sent)/2,stamp-(sent+received)/2))
        self.uncertainty_us,self.offset_us=min(measurements)
        if self.uncertainty_us>20_000:raise ProtocolError('Aircraft clock uncertainty exceeds 20 ms',409)
        self.last_clock_sync_us=self.clock()
        return hello

    def device_time(self):
        if self.offset_us is None or self.clock()-self.last_clock_sync_us>10_000_000:
            raise ProtocolError('Aircraft clock mapping is stale',409)
        return self.clock()+self.offset_us

    def deadline(self):
        # Keep expiry conservative under the measured round-trip uncertainty.
        return int(self.device_time()+MAX_DEADLINE_US-2*self.uncertainty_us-10_000)

    async def claim(self):
        if self.session_id:raise ProtocolError('Client already has a control session',409)
        result=await self.request('/v1/session',{'client_id':self.client_id})
        if result.get('boot_id')!=self.boot_id:raise ProtocolError('Aircraft boot changed',409)
        value=result.get('session_id')
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):raise ProtocolError('Invalid session identity')
        self.session_id=value;self.sequence=0
        return result

    async def command(self,operation,**extra):
        async with self.lock:
            if not self.session_id:raise ProtocolError('Claim aircraft control first',409)
            if set(extra) != ({'setpoint'} if operation=='attitude' else set()):
                raise ProtocolError('Unexpected command fields')
            self.sequence+=1
            body={'boot_id':self.boot_id,'session_id':self.session_id,'sequence':self.sequence,
                  'deadline_us':self.deadline(),'operation':operation,**extra}
            result=await self.request('/v1/command',body)
            if result.get('sequence')!=self.sequence or result.get('accepted') is not True:
                raise ProtocolError('Mismatched command acknowledgement',409)
            if operation in ('land','disarm'):self.session_id=None
            return result

    async def emergency(self,operation='land'):
        # Separate request: never queued behind an inference/control lock.
        self.session_id=None
        result=await self.request('/v1/emergency',{'boot_id':self.boot_id,
                         'deadline_us':self.deadline(),'operation':operation},emergency=True)
        return result

    async def capture(self):
        from adapters.esp32_camera import jpeg_dimensions
        async with self.camera_session.get(self.url+'/v1/camera',ssl=self.fingerprint,
                    allow_redirects=False) as response:
            if response.status!=200 or response.content_type!='image/jpeg':
                raise ProtocolError('Aircraft camera unavailable',response.status)
            data=bytearray()
            async for block in response.content.iter_chunked(8192):
                data.extend(block)
                if len(data)>200_000:raise ProtocolError('Camera frame exceeds 200 KB')
            width,height=jpeg_dimensions(bytes(data))
            try:
                boot=response.headers['X-Boot-Id']
                sequence=int(response.headers['X-Frame-Id'])
                capture=int(response.headers['X-Capture-Time-Us'])
                reported=(int(response.headers['X-Width']),int(response.headers['X-Height']))
            except (KeyError,ValueError) as exc:raise ProtocolError('Invalid camera timing metadata') from exc
            age=self.device_time()-capture
            if (boot!=self.boot_id or sequence<0 or capture<0 or reported!=(width,height)
                    or age < -self.uncertainty_us or age+self.uncertainty_us>300_000):
                raise ProtocolError('Stale or inconsistent camera frame',409)
            if self.last_frame and (sequence<=self.last_frame[0] or capture<=self.last_frame[1]):
                raise ProtocolError('Replayed camera frame',409)
            self.last_frame=(sequence,capture)
            return {'jpeg':bytes(data),'boot_id':boot,'sequence':sequence,
                    'capture_time_us':capture,'host_capture_time_us':capture-self.offset_us,
                    'clock_uncertainty_us':self.uncertainty_us,'width':width,'height':height}

    async def imu(self):
        import math
        result=await self.request('/v1/imu?after_us='+str(self.last_imu_us))
        if result.get('boot_id')!=self.boot_id or result.get('overrun') is not False:
            raise ProtocolError('IMU reboot or ring overrun',409)
        samples=result.get('samples')
        if not isinstance(samples,list) or len(samples)>256:raise ProtocolError('Invalid IMU packet')
        previous=self.last_imu_us
        for sample in samples:
            if not isinstance(sample,dict):raise ProtocolError('Invalid IMU sample')
            stamp=sample.get('time_us')
            if type(stamp) is not int or stamp<=previous:raise ProtocolError('Out-of-order IMU sample',409)
            for key in ('gyro_flu_rad_s','specific_force_flu_m_s2'):
                vector=sample.get(key)
                if (not isinstance(vector,list) or len(vector)!=3
                        or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector)):
                    raise ProtocolError('Invalid IMU vector')
            previous=stamp
        if samples:
            age=self.device_time()-previous
            if age < -self.uncertainty_us or age+self.uncertainty_us>50_000:
                raise ProtocolError('Stale IMU packet',409)
            self.last_imu_us=previous
        return result

    async def close(self):
        for session in (self.session,self.camera_session,self.emergency_session):
            if session:await session.close()
        self.session=self.camera_session=self.emergency_session=None
        self.session_id=self.boot_id=self.offset_us=self.last_clock_sync_us=None
        self.last_frame=None
        self.last_imu_us=0
