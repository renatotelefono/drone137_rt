"""HTTP camera/model contract tests using recorded pixels; no ESP32 or flight."""
import asyncio
import base64
import json
from pathlib import Path
import tempfile
import time
import types
import unittest

from aiohttp import web
from adapters.esp32_camera import Esp32Camera, camera_url, jpeg_dimensions
from scripts.esp32_camera_bench import run

JPEG = Path('sim/assets/fixture-01.jpg').read_bytes()
WIDTH, HEIGHT = jpeg_dimensions(JPEG)


class CameraTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seq = 0
        self.boot = 'boot1'
        self.fixed_sequence = None
        self.fixed_time = None
        self.body = JPEG
        self.delay = 0
        self.redirects = 0
        self.bad_dimensions = False
        self.with_metadata = True
        self.slow = asyncio.Event()
        async def capture(request):
            self.slow.set()
            await asyncio.sleep(self.delay)
            self.seq += 1
            headers = {'X-Boot-Id':self.boot,
                       'X-Frame-Id':str(self.fixed_sequence if self.fixed_sequence is not None else self.seq),
                       'X-Capture-Time-Us':str(self.fixed_time if self.fixed_time is not None else self.seq*100000),
                       'X-Width':str(1 if self.bad_dimensions else WIDTH), 'X-Height':str(HEIGHT)}
            return web.Response(body=self.body, content_type='image/jpeg',
                                headers=headers if self.with_metadata else {})
        async def redirect(request):
            raise web.HTTPFound('/other')
        async def other(request):
            self.redirects += 1
            return web.Response(body=JPEG,content_type='image/jpeg')
        self.app = web.Application()
        self.app.router.add_get('/capture', capture)
        self.app.router.add_get('/redirect/capture',redirect)
        self.app.router.add_get('/other',other)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}/capture'
        self.camera = None

    async def asyncTearDown(self):
        if self.camera:
            await self.camera.close()
        await self.runner.cleanup()

    async def camera_once(self, **kwargs):
        import aiohttp
        self.camera = Esp32Camera(self.url, **kwargs)
        self.camera.begin_episode('first')
        self.camera.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.camera.timeout))
        await self.camera._capture()
        return self.camera

    async def test_preserves_pixels_dimensions_and_unmapped_sensor_clock(self):
        camera = await self.camera_once()
        frame = camera.latest()
        self.assertEqual(frame.jpeg, JPEG)
        self.assertEqual((frame.width, frame.height), (WIDTH, HEIGHT))
        self.assertEqual(frame.sensor_time_s, .1)
        self.assertEqual(frame.timestamp_basis, 'device_monotonic_unmapped')
        self.assertIsNone(camera.status()['capture_age_s'])
        self.assertFalse(camera.status()['clock_mapping_verified'])
        await camera._capture()
        self.assertEqual(camera.frames_received, 2)
        self.assertNotEqual(camera.latest().frame_id, frame.frame_id)

    async def test_repeated_capture_clock_rejected_even_with_new_sequence(self):
        camera = await self.camera_once()
        self.fixed_time = 100000
        with self.assertRaisesRegex(ValueError,'repeated'):
            await camera._capture()

    async def test_reboot_can_restart_sequence(self):
        camera = await self.camera_once()
        self.boot = 'boot2'
        self.fixed_sequence = 1
        self.fixed_time = 1
        await camera._capture()
        self.assertEqual(camera.latest().sensor_time_s,.000001)

    async def test_stale_frame_not_returned(self):
        camera = await self.camera_once(stale_after=.01)
        await asyncio.sleep(.02)
        self.assertIsNone(camera.latest())

    async def test_new_episode_drops_in_flight_old_frame(self):
        camera = await self.camera_once()
        self.slow.clear()
        self.delay = .04
        task = asyncio.create_task(camera._capture())
        await self.slow.wait()
        camera.begin_episode('second')
        await task
        self.assertIsNone(camera.latest())
        await camera._capture()
        self.assertEqual(camera.latest().episode_id,'second')

    async def test_invalid_large_jpeg_and_dimension_mismatch_rejected(self):
        camera = await self.camera_once()
        for data, bad_dimensions in ((b'not JPEG',False),(b'x'*200001,False),(JPEG,True)):
            self.body, self.bad_dimensions = data,bad_dimensions
            with self.assertRaises(ValueError):
                await camera._capture()

    async def test_missing_metadata_requires_explicit_degraded_mode(self):
        self.with_metadata = False
        with self.assertRaisesRegex(ValueError,'boot identity'):
            await self.camera_once()
        self.camera.require_metadata = False
        await self.camera._capture()
        self.assertEqual(self.camera.latest().timestamp_basis,'host_receipt_only')

    async def test_background_failure_clears_frame_and_recovers(self):
        self.camera = Esp32Camera(self.url, fps=10, timeout=.02)
        self.camera.begin_episode('test')
        await self.camera.start()
        for _ in range(50):
            if self.camera.latest(): break
            await asyncio.sleep(.01)
        self.assertIsNotNone(self.camera.latest())
        self.delay = .05
        for _ in range(50):
            if self.camera.errors: break
            await asyncio.sleep(.01)
        self.assertGreater(self.camera.errors,0)
        self.assertIsNone(self.camera.latest())
        self.delay = 0
        for _ in range(50):
            if self.camera.latest(): break
            await asyncio.sleep(.01)
        self.assertIsNotNone(self.camera.latest())

    async def test_no_redirect_followed(self):
        camera = await self.camera_once()
        # Replace the URL after validation solely to exercise the HTTP redirect guard.
        camera.url = f'http://127.0.0.1:{self.port}/redirect/capture'
        with self.assertRaisesRegex(ValueError,'HTTP 200'):
            await camera._capture()
        self.assertEqual(self.redirects,0)

    async def test_camera_pixels_reach_model_contract_and_recording(self):
        calls = []
        async def infer(request):
            body = await request.json()
            data = body['messages'][0]['content'][0]['image_url']['url']
            calls.append(base64.b64decode(data.split(',')[1]))
            return web.json_response({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
                'summary':'Fixture description only','objects':['Test image'], 'uncertainty':'Not real inference'})}}]})
        modelapp=web.Application()
        modelapp.router.add_get('/health',lambda _:web.json_response({'status':'ok'}))
        modelapp.router.add_post('/v1/chat/completions',infer)
        runner=web.AppRunner(modelapp)
        await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0)
        await site.start()
        port=site._server.sockets[0].getsockname()[1]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                args=types.SimpleNamespace(camera=self.url,output=tmp,fps=10,allow_receipt_only=False,
                    model=f'http://127.0.0.1:{port}',inference_timeout=1,inference_every=1,
                    port=0,seconds=.3)
                self.assertEqual(await run(args),0)
                result=json.loads((Path(tmp)/'report.json').read_text())
                self.assertTrue(result['passed'])
                self.assertFalse(result['physical_enabled'])
                self.assertFalse(result['hardware_flight_test'])
                self.assertEqual(calls,[JPEG])
                self.assertEqual((Path(tmp)/'latest.jpg').read_bytes(),JPEG)
        finally:
            await runner.cleanup()


class InputTests(unittest.TestCase):
    def test_private_capture_only(self):
        for value in ('https://192.168.1.2/capture','http://example.com/capture',
                      'http://8.8.8.8/capture','http://192.168.1.2/control',
                      'http://user:pw@192.168.1.2/capture','http://192.168.1.2/capture?q=1',
                      'http://169.254.169.254/capture','http://192.168.1.2:bad/capture'):
            with self.subTest(value=value),self.assertRaises(ValueError): camera_url(value)
        self.assertEqual(camera_url('http://192.168.1.2/capture'),'http://192.168.1.2/capture')

    def test_unbounded_timing_and_geometry_rejected(self):
        for options in ({'fps':float('nan')},{'timeout':0},{'fps':11}):
            with self.assertRaises(ValueError):Esp32Camera('http://127.0.0.1/capture',**options)
        malformed=b'\xff\xd8\xff\xc0\x00\x08\x08\x04\x00\x08\x00\x00\xff\xd9'
        with self.assertRaisesRegex(ValueError,'geometry'):jpeg_dimensions(malformed)


if __name__=='__main__': unittest.main()
