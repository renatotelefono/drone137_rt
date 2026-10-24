import asyncio
import tempfile
import time
from pathlib import Path
import unittest

import aiohttp
from aiohttp import web

from hardware.esp32.link_client import AircraftLink,endpoint
from hardware.esp32.link_emulator import AircraftEmulator,provision,tls_context
from hardware.esp32.link_protocol import ProtocolError


class AircraftLinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory()
        identity=Path(self.folder.name)/'identity'
        self.profile=provision(identity)
        self.emulator=AircraftEmulator(self.profile)
        self.runner=web.AppRunner(self.emulator.app(),access_log=None)
        await self.runner.setup()
        self.site=web.TCPSite(self.runner,'127.0.0.1',0,ssl_context=tls_context(identity))
        await self.site.start()
        port=self.site._server.sockets[0].getsockname()[1]
        self.url=f'https://127.0.0.1:{port}'
        self.link=self.new_link()
        await self.link.start()

    def new_link(self,**overrides):
        values={'fingerprint':self.profile['certificate_sha256'],'credential':self.profile['credential'],
                'client_id':'ground-test',**overrides}
        return AircraftLink(self.url,**values)

    async def asyncTearDown(self):
        await self.link.close()
        await self.runner.cleanup()
        self.folder.cleanup()

    async def test_tls_authentication_and_pinned_identity(self):
        wrong=self.new_link(credential='wrong'*10)
        with self.assertRaises(ProtocolError) as error:await wrong.start()
        self.assertEqual(error.exception.status,401)
        wrong=self.new_link(fingerprint='0'*64)
        with self.assertRaises(aiohttp.ServerFingerprintMismatch):await wrong.start()

    async def test_actual_encrypted_command_and_camera_path(self):
        await self.link.claim()
        reply=await self.link.command('arm')
        self.assertEqual(reply['state'],'armed')
        await self.link.command('attitude',setpoint=dict(roll_rad=.1,pitch_rad=0,yaw_rate_rad_s=0,thrust=.4))
        frame=await self.link.capture()
        self.assertTrue(frame['jpeg'].startswith(b'\xff\xd8'))
        self.assertLess(frame['clock_uncertainty_us'],20_000)
        self.assertEqual(frame['boot_id'],self.emulator.core.boot_id)
        imu=await self.link.imu()
        self.assertTrue(imu['samples'])
        self.assertEqual(imu['boot_id'],frame['boot_id'])
        await self.link.command('disarm')
        self.assertEqual(self.emulator.core.state,'disarmed')

    async def test_imu_ring_overrun_is_not_silently_treated_as_continuous_pose(self):
        self.link.last_imu_us=1
        with self.assertRaisesRegex(ProtocolError,'overrun'):await self.link.imu()

    async def test_reconnection_starts_at_newest_continuous_sensor_history(self):
        from unittest.mock import AsyncMock
        now=int(self.link.device_time())
        samples=[dict(time_us=t,gyro_flu_rad_s=[0,0,0],specific_force_flu_m_s2=[0,0,9.8]) for t in (now-60000,now-5000,now)]
        self.link.request=AsyncMock(return_value=dict(boot_id=self.link.boot_id,overrun=False,oldest_time_us=now-60000,samples=samples))
        result=await self.link.imu()
        self.assertEqual(result['initial_history_discarded_samples'],1)
        self.assertEqual(len(result['samples']),2)
        self.assertEqual(result['oldest_time_us'],now-5000)

    async def test_internal_imu_gap_is_rejected_even_without_overrun_flag(self):
        from unittest.mock import AsyncMock
        now=int(self.link.device_time());self.link.last_imu_us=now-30000
        self.link.request=AsyncMock(return_value=dict(boot_id=self.link.boot_id,overrun=False,samples=[dict(time_us=now,gyro_flu_rad_s=[0,0,0],specific_force_flu_m_s2=[0,0,9.8])]))
        with self.assertRaisesRegex(ProtocolError,'sample gap'):await self.link.imu()

    async def test_expired_and_replayed_images_never_reach_model_consumer(self):
        self.emulator.frame_age_us=500_000
        with self.assertRaisesRegex(ProtocolError,'Stale'):await self.link.capture()
        self.emulator.frame_age_us=0
        await self.link.capture()
        self.emulator.replay_frame=True
        with self.assertRaisesRegex(ProtocolError,'Replayed'):await self.link.capture()

    async def test_stop_bypasses_stalled_control_and_camera_channels(self):
        await self.link.claim()
        await self.link.command('arm')
        self.emulator.camera_delay=.8
        capture=asyncio.create_task(self.link.capture())
        await self.link.lock.acquire()
        try:
            result=await asyncio.wait_for(self.link.emergency('disarm'),.5)
            self.assertEqual(result['state'],'disarmed')
            self.assertIsNone(self.link.session_id)
        finally:
            self.link.lock.release()
            capture.cancel()
            await asyncio.gather(capture,return_exceptions=True)

    async def test_reboot_and_clock_expiry_require_reconnection(self):
        self.link.last_clock_sync_us-=11_000_000
        with self.assertRaisesRegex(ProtocolError,'stale'):self.link.deadline()
        await self.link.synchronize()
        self.emulator.core.boot_id='f'*32
        with self.assertRaisesRegex(ProtocolError,'rebooted'):await self.link.synchronize()

    def test_no_plaintext_public_hosts_credentials_or_redirect_addresses(self):
        for value in ('http://127.0.0.1:8160','https://8.8.8.8','https://example.com',
                      'https://user:password@192.168.1.2','https://192.168.1.2/other'):
            with self.assertRaises(ValueError):endpoint(value)


if __name__=='__main__':unittest.main()
