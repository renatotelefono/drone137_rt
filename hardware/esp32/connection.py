"""Bounded sensor connection owned by Mission Control, independent of inference.

This is a connection/monitor, not an autopilot. It never arms or emits thrust.
An operator can explicitly stop a paired aircraft even if someone else owns it.
"""
import asyncio
from collections import deque
import time

from hardware.esp32.link_client import AircraftLink
from hardware.esp32.link_protocol import ProtocolError


class AircraftConnection:
    def __init__(self, record):
        self.identity = record['id']
        self.kind = record['kind']
        self.link = AircraftLink(record['endpoint'], record['fingerprint'], record['credential'], 'drone137')
        self.emergency_endpoint = self.link.url
        self.state = 'disconnected'
        self.error = None
        self.hello = None
        self.frame = None
        self.imu_samples = deque(maxlen=512)
        self.imu_received = self.frame_received = None
        self.dropped_imu = 0
        self.tasks = []

    def check_identity(self, hello):
        if hello.get('device_id') != self.identity or hello.get('kind') != self.kind:
            raise ProtocolError('Aircraft identity or type differs from its pairing record', 409)

    async def connect(self):
        if self.state not in ('disconnected', 'fault'):
            raise ProtocolError('Aircraft is already connected or connecting', 409)
        await self.close()
        self.state = 'connecting'
        self.error = None
        try:
            self.hello = await self.link.start()
            self.check_identity(self.hello)
            self.emergency_endpoint = self.link.emergency_url
            self.frame = await self.link.capture()
            self.frame_received = time.monotonic()
            await self.read_imu()
            if not self.imu_samples:
                raise ProtocolError('No fresh IMU samples received', 409)
            self.state = 'connected'
            self.tasks = [asyncio.create_task(self.guard(self.poll_imu())),
                          asyncio.create_task(self.guard(self.poll_camera())),
                          asyncio.create_task(self.guard(self.poll_clock()))]
        except BaseException:
            await self.close()
            self.state = 'fault'
            self.error = 'Connection failed; check pairing, Wi-Fi and sensor health'
            raise
        return self.snapshot()

    async def guard(self, routine):
        try:
            await routine
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # aiohttp exceptions can include request headers. Do not expose them.
            self.error = str(exc)[:180] if isinstance(exc, ProtocolError) else 'Aircraft link unavailable'
            self.state = 'fault'
            self.frame = None
            self.imu_samples.clear()
            current = asyncio.current_task()
            for task in self.tasks:
                if task is not current:
                    task.cancel()
            await self.link.close()

    async def read_imu(self):
        packet = await self.link.imu()
        samples = packet['samples']
        if samples:
            self.imu_received = time.monotonic()
            for sample in samples:
                if len(self.imu_samples) == self.imu_samples.maxlen:
                    self.dropped_imu += 1
                self.imu_samples.append(sample)
        elif self.imu_received is None or time.monotonic() - self.imu_received > .05:
            raise ProtocolError('IMU stream stopped', 409)

    async def poll_imu(self):
        while True:
            await asyncio.sleep(.04)
            await self.read_imu()

    async def poll_camera(self):
        while True:
            await asyncio.sleep(.4)
            self.frame = await self.link.capture()
            self.frame_received = time.monotonic()

    async def poll_clock(self):
        while True:
            await asyncio.sleep(3)
            self.hello = await self.link.synchronize()
            self.check_identity(self.hello)

    def take_imu(self):
        """Consumers must treat overflow as lost history and reinitialize pose."""
        if self.state != 'connected':
            raise ProtocolError('Aircraft is not connected', 409)
        samples = list(self.imu_samples)
        self.imu_samples.clear()
        lost = self.dropped_imu
        self.dropped_imu = 0
        return {'boot_id': self.link.boot_id, 'samples': samples, 'dropped_samples': lost,
                'clock_offset_us': self.link.offset_us, 'clock_uncertainty_us': self.link.uncertainty_us}

    def latest_frame(self):
        if self.state != 'connected' or not self.frame:
            raise ProtocolError('Aircraft camera unavailable', 409)
        age = self.link.device_time() - self.frame['capture_time_us']
        if age + self.link.uncertainty_us > 600_000:
            raise ProtocolError('Camera preview expired', 409)
        return self.frame

    def snapshot(self):
        hello = self.hello or {}
        return {'id': self.identity, 'connection': self.state, 'kind': self.kind,
                'error': self.error, 'aircraft_state': hello.get('state'),
                'voltage_v': hello.get('voltage_v'), 'owner': hello.get('owner'),
                'camera_ready': self.state == 'connected' and self.frame is not None,
                'imu_buffered': len(self.imu_samples), 'imu_dropped': self.dropped_imu,
                'clock_uncertainty_ms': (self.link.uncertainty_us / 1000
                                          if self.link.uncertainty_us is not None else None),
                'mission_ready': False,
                'firmware': hello.get('firmware'),
                'commissioned': hello.get('commissioned',False),
                'restrained_rig': hello.get('restrained_rig',False),
                'bench_motor_tests': hello.get('bench_motor_tests',False),
                'calibrated': hello.get('calibrated',False),
                'controller': hello.get('controller'),
                'mission_blocker': 'Physical commissioning, tuned flight control and calibrated navigation are pending'}

    async def stop(self, operation='land'):
        if operation not in ('land', 'disarm'):
            raise ProtocolError('Unknown stop action')
        # This fresh channel can also reconnect after a failed sensor monitor.
        emergency = AircraftLink(self.emergency_endpoint, self.link.fingerprint.fingerprint.hex(),
                                 self.link.credential, 'drone137-stop')
        try:
            hello = await emergency.start()
            self.check_identity(hello)
            result = await emergency.emergency(operation)
            if self.hello:
                self.hello['state'] = result['state']
                self.hello['owner'] = None
            return result
        finally:
            await emergency.close()

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        await self.link.close()
        self.state = 'disconnected'
        self.frame = self.hello = None
        self.frame_received = self.imu_received = None
        self.imu_samples.clear()
        self.dropped_imu = 0
