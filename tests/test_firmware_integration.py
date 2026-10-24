import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from aiohttp import web

from hardware.esp32.firmware_sil import FirmwareSIL
from hardware.esp32.link_client import AircraftLink
from hardware.esp32.link_emulator import provision,tls_context
from hardware.esp32.link_protocol import ProtocolError
from hardware.esp32.connection import AircraftConnection
from scripts.esp32_firmware import provision as provision_board,stage


class FirmwareIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.identity=Path(self.folder.name)/'identity'
        self.profile=provision(self.identity);self.device=FirmwareSIL(self.profile)
        self.runners=[];ports=[]
        for channel in ('control','camera','emergency'):
            runner=web.AppRunner(self.device.app(channel),access_log=None);await runner.setup()
            self.runners.append(runner)
            site=web.TCPSite(runner,'127.0.0.1',0,ssl_context=tls_context(self.identity));await site.start()
            ports.append(site._server.sockets[0].getsockname()[1])
        self.device.channels=dict(camera_port=ports[1],emergency_port=ports[2])
        self.url=f'https://127.0.0.1:{ports[0]}'
        self.link=AircraftLink(self.url,self.profile['certificate_sha256'],self.profile['credential'],'sil-test')
        await self.device.start();await self.link.start()

    async def asyncTearDown(self):
        await self.link.close()
        for runner in self.runners:await runner.cleanup()
        await self.device.close();self.folder.cleanup()

    async def arm(self):
        await self.link.claim();await self.link.command('arm')
        await self.link.command('attitude',setpoint=dict(roll_rad=.05,pitch_rad=0,yaw_rate_rad_s=0,thrust=.45))

    async def test_exact_cpp_firmware_over_tls_and_separate_camera(self):
        self.assertNotEqual(self.link.url,self.link.camera_url)
        await self.arm();await asyncio.sleep(.01)
        hello=await self.link.request('/v1/hello')
        self.assertEqual(hello['firmware'],'shared-cpp-software-in-loop')
        self.assertGreater(max(hello['controller']['motor_duty']),0)
        self.assertTrue((await self.link.capture())['jpeg'])
        self.assertTrue((await self.link.imu())['samples'])
        await self.link.emergency('disarm')
        self.assertEqual(self.device.core.hello(self.device.clock())['controller']['motor_duty'],[0]*4)

    async def test_wifi_or_ground_process_loss_stops_cpp_controller(self):
        await self.arm();await self.link.close()
        await asyncio.sleep(.35)
        self.assertEqual(self.device.core.hello(self.device.clock())['state'],'landing')
        await asyncio.sleep(1.5)
        self.assertEqual(self.device.core.hello(self.device.clock())['controller']['motor_duty'],[0]*4)

    async def test_inference_and_video_stall_cannot_queue_stop(self):
        await self.arm();self.device.camera_delay=.8
        task=asyncio.create_task(self.link.capture());await self.link.lock.acquire()
        try:
            result=await asyncio.wait_for(self.link.emergency('disarm'),.25)
            self.assertEqual(result['state'],'disarmed')
        finally:
            self.link.lock.release();task.cancel();await asyncio.gather(task,return_exceptions=True)

    async def test_stale_image_and_missing_imu_fail_closed(self):
        self.device.frame_age_us=500000
        with self.assertRaisesRegex(ProtocolError,'Stale'):await self.link.capture()
        await self.arm();self.device.freeze_imu=True;await asyncio.sleep(.04)
        hello=self.device.core.hello(self.device.clock())
        self.assertTrue(hello['fault_latched']);self.assertEqual(hello['state'],'disarmed')

    async def test_duplicate_wire_fields_rejected_before_arming(self):
        async with self.link.session.post(self.url+'/v1/session',
                data='{"client_id":"a","client_id":"b"}',ssl=self.link.fingerprint) as response:
            self.assertEqual(response.status,400)

    async def test_mission_control_consumes_cpp_sensors_without_arming(self):
        connection=AircraftConnection(dict(id=self.profile['device_id'],kind='protocol-emulator',
            endpoint=self.url,fingerprint=self.profile['certificate_sha256'],credential=self.profile['credential']))
        try:
            state=await connection.connect()
            self.assertEqual(state['connection'],'connected')
            self.assertEqual(state['aircraft_state'],'disarmed')
            self.assertFalse(state['mission_ready'])
            self.assertTrue(connection.take_imu()['samples'])
            self.assertTrue(connection.latest_frame()['jpeg'])
            self.assertEqual((await connection.stop('disarm'))['state'],'disarmed')
        finally:await connection.close()

    async def test_mission_control_stop_does_not_depend_on_control_server(self):
        connection=AircraftConnection(dict(id=self.profile['device_id'],kind='protocol-emulator',endpoint=self.url,fingerprint=self.profile['certificate_sha256'],credential=self.profile['credential']))
        try:
            await connection.connect();await self.arm();self.device.control_delay=1.
            result=await asyncio.wait_for(connection.stop('disarm'),.35)
            self.assertEqual(result['state'],'disarmed')
            # The cached pinned emergency endpoint survives a sensor disconnect.
            await connection.close()
            result=await asyncio.wait_for(connection.stop('disarm'),.35)
            self.assertEqual(result['state'],'disarmed')
        finally:self.device.control_delay=0.;await connection.close()

    async def test_channel_changes_require_reconnection(self):
        self.device.channels['camera_port']+=1
        with self.assertRaisesRegex(ProtocolError,'changed'):await self.link.synchronize()

    async def test_explicit_bench_tool_stops_and_records_exact_firmware(self):
        from scripts.esp32_firmware import bench_action
        self.device.core.lib.d137_bench(self.device.core.ptr,True)
        result=await bench_action(self.identity,self.url,Path(self.folder.name)/'motor',motor=2)
        self.assertTrue(result['completed']);self.assertEqual(result['stop']['state'],'disarmed')
        self.device.core.lib.d137_rig(self.device.core.ptr)
        result=await bench_action(self.identity,self.url,Path(self.folder.name)/'rig',seconds=.3,collective=.1)
        self.assertTrue(result['telemetry']);self.assertEqual(result['stop']['state'],'disarmed')

    async def test_read_only_sensor_recording_preserves_clock_and_hashes(self):
        from hardware.esp32.sensor_recording import record
        output=Path(self.folder.name)/'recording'
        result=await record(self.identity,self.url,output,seconds=1)
        self.assertTrue(result['complete']);self.assertFalse(result['armed_by_recorder'])
        self.assertGreater(result['imu_samples'],100)
        saved=json.loads((output/'recording.json').read_text())
        self.assertTrue(saved['imu_sha256']);self.assertGreater(len(saved['frames']),1)
        self.assertEqual(self.device.core.hello(self.device.clock())['state'],'disarmed')


class ProvisionTests(unittest.TestCase):
    def test_rig_build_requires_initial_checks_but_not_completed_tuning(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);network=root/'wifi.json'
            network.write_text(json.dumps(dict(ssid='local-test',password='test-password')))
            provision_board(root/'device','scout-rig',network)
            with self.assertRaisesRegex(ValueError,'commissioning'):stage(root/'device',root/'rejected',rig=True)
            record=dict(device_id='scout-rig',operator='test fixture only',evidence_directory='fixture',checks={k:True for k in ('electrical_inspection','motor_order_and_direction','imu_axes','battery_adc','restraint_verified')})
            (root/'device/commissioning.json').write_text(json.dumps(record))
            sketch=stage(root/'device',root/'rig',rig=True)
            config=(sketch/'config.h').read_text()
            self.assertIn('#define D137_RESTRAINED_RIG 1',config)
            self.assertIn('#define D137_COMMISSIONED 0',config)
            with self.assertRaisesRegex(ValueError,'incomplete'):stage(root/'device',root/'flight',enable=True)

    def test_per_aircraft_identity_and_default_outputs_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);network=root/'wifi.json'
            network.write_text(json.dumps(dict(ssid='local-test',password='test-password')))
            provision_board(root/'one','scout-one',network)
            provision_board(root/'two','scout-two',network)
            a=json.loads((root/'one/pairing.json').read_text());b=json.loads((root/'two/pairing.json').read_text())
            self.assertNotEqual(a['credential'],b['credential'])
            self.assertNotEqual(a['certificate_sha256'],b['certificate_sha256'])
            sketch=stage(root/'one',root/'safe-build')
            self.assertIn('#define D137_OUTPUTS_ENABLED 0',(sketch/'config.h').read_text())
            self.assertEqual((sketch/'config.h').stat().st_mode&0o777,0o600)
            with self.assertRaisesRegex(ValueError,'commissioning'):stage(root/'one',root/'unsafe',True)
            with self.assertRaises(FileExistsError):provision_board(root/'one','scout-one',network)


if __name__=='__main__':unittest.main()
