import asyncio
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from dataclasses import replace

from aiohttp import web, ClientSession
from adapters.llama import LlamaBackend
from app.watchdog import ProcessSupervisor
from app.server import make_app
from scripts.launch import monitor_app
from test_contracts import observation
from test_executor import eventually
import test_executor


class LlamaHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests=[]
        self.delay=0
        async def handler(request):
            self.requests.append(await request.json())
            await asyncio.sleep(self.delay)
            return web.json_response({"choices":[{"message":{"content":
                '{"observation":"open","action":"continue","target_view":null,"reason":"contract fixture"}'}}]})
        app=web.Application()
        app.router.add_post("/v1/chat/completions",handler)
        self.runner=web.AppRunner(app)
        await self.runner.setup()
        site=web.TCPSite(self.runner,"127.0.0.1",0)
        await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.backend=LlamaBackend(f"http://127.0.0.1:{port}",timeout=.15)

    async def asyncTearDown(self):
        await self.backend.close()
        await self.runner.cleanup()

    async def test_real_http_contract_mock_model(self):
        raw=await self.backend.infer(observation())
        self.assertEqual(json.loads(raw)["action"],"continue")
        request=self.requests[0]
        self.assertEqual(request["max_tokens"],128)
        content=request["messages"][0]["content"]
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("fixture-01",json.dumps(request))
        self.assertEqual(request["response_format"]["type"],"json_schema")

    async def test_timeout_quarantines_and_prevents_second_request(self):
        self.delay=.3
        with self.assertRaises(TimeoutError):
            await self.backend.infer(observation())
        with self.assertRaises(RuntimeError):
            await self.backend.infer(observation())
        self.assertEqual(len(self.requests),1)
        self.assertTrue(self.backend.quarantined)

    async def test_concurrent_request_rejected(self):
        self.delay=.08
        first=asyncio.create_task(self.backend.infer(observation()))
        await eventually(lambda:self.backend.busy)
        with self.assertRaises(RuntimeError):
            await self.backend.infer(observation())
        await first
        self.assertEqual(len(self.requests),1)

    async def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            LlamaBackend("https://remote.example")


class LocalAPI(unittest.IsolatedAsyncioTestCase):
    async def test_http_operator_routes_and_host_protection(self):
        fixture=test_executor.Missions()
        await fixture.asyncSetUp()
        runner=web.AppRunner(make_app(fixture.executor))
        await runner.setup()
        site=web.TCPSite(runner,"127.0.0.1",0)
        await site.start()
        url=f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        try:
            async with ClientSession() as session:
                async with session.get(url+"/") as response:
                    self.assertIn("Inspection console",await response.text())
                async with session.post(url+"/api/start") as response:
                    self.assertEqual(response.status,403)
                async with session.get(url+"/api/status",headers={"Host":"attacker.example"}) as response:
                    self.assertEqual(response.status,403)
                headers={"X-Drone137-Control":"local"}
                async with session.post(url+"/api/start",headers=headers) as response:
                    self.assertEqual(response.status,200)
                await eventually(lambda:fixture.drone.in_air)
                async with session.post(url+"/api/land",headers=headers) as response:
                    self.assertEqual(response.status,200)
                    self.assertEqual((await response.json())["state"],"failed")
        finally:
            await runner.cleanup()
            await fixture.asyncTearDown()


class Processes(unittest.IsolatedAsyncioTestCase):
    async def test_independent_heartbeat_detects_unresponsive_app(self):
        calls=0
        async def status(request):
            nonlocal calls
            calls+=1
            if calls>1:
                await asyncio.sleep(1.2)
            return web.json_response({"state":"observing"})
        app=web.Application()
        app.router.add_get("/api/status",status)
        runner=web.AppRunner(app)
        await runner.setup()
        site=web.TCPSite(runner,"127.0.0.1",0)
        await site.start()
        try:
            port=site._server.sockets[0].getsockname()[1]
            self.assertFalse(await asyncio.wait_for(monitor_app(port,asyncio.Event(),health_timeout=.1),3))
        finally:
            await runner.cleanup()

    async def test_native_log_output_has_hard_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor=ProcessSupervisor()
            log=Path(directory)/"log"
            process=await supervisor.spawn("verbose",[sys.executable,"-c","import sys; sys.stdout.write('x'*9000000)"],log)
            await process.wait()
            await supervisor.close()
            self.assertLessEqual(log.stat().st_size,8*1024*1024)
            self.assertTrue(supervisor.log_limit_reached)

    async def test_cleanup_owned_group_keeps_unrelated_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            supervisor=ProcessSupervisor()
            unrelated=await asyncio.create_subprocess_exec(sys.executable,"-c","import time; time.sleep(20)")
            try:
                process=await supervisor.spawn("worker",[sys.executable,"-c","import time; time.sleep(20)"],root/"log")
                self.assertTrue(supervisor.healthy())
                await supervisor.close()
                self.assertIsNotNone(process.returncode)
                self.assertIsNone(unrelated.returncode)
            finally:
                unrelated.terminate()
                await unrelated.wait()

    async def test_dead_child_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor=ProcessSupervisor()
            process=await supervisor.spawn("worker",[sys.executable,"-c","raise SystemExit(3)"],Path(directory)/"log")
            await process.wait()
            self.assertFalse(supervisor.healthy())
            await supervisor.close()
