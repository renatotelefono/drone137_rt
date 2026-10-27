"""What differs by platform is answered in app.portability and behaves the same on this host: process trees, stop handlers,
the launcher's control channel, the runtime plan, the browser candidates and the person detector's backend choice."""
import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from app import portability
from app.person_detector import available_backend
from scripts import launch
from scripts.tools import ROOT, runtime_plan


class ProcessTrees(unittest.IsolatedAsyncioTestCase):
    async def test_an_owned_process_and_its_child_are_stopped_together(self):
        script = "import subprocess, sys, time; c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)"
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', script, **portability.spawn_kwargs())
        await asyncio.sleep(.8)
        import psutil
        children = psutil.Process(process.pid).children(recursive=True)
        self.assertGreaterEqual(len(children), 1)
        portability.terminate_tree(process.pid)
        await asyncio.wait_for(process.wait(), 5)
        await asyncio.sleep(.3)
        self.assertTrue(all(not c.is_running() or c.status() == psutil.STATUS_ZOMBIE for c in children))
        portability.kill_tree(process.pid)   # harmless on a gone process

    def test_stop_handlers_fall_back_to_signal_signal_where_the_loop_has_none(self):
        class Loop:
            def add_signal_handler(self, sig, cb):
                raise NotImplementedError
            def call_soon_threadsafe(self, cb):
                cb()
        calls = []
        with mock.patch('signal.signal') as installed:
            portability.install_stop_handlers(Loop(), lambda: calls.append(1))
            self.assertGreaterEqual(installed.call_count, 2)
            installed.call_args_list[0].args[1](None, None)
        self.assertEqual(calls, [1])


class ControlChannel(unittest.IsolatedAsyncioTestCase):
    async def test_the_windows_loopback_channel_carries_a_stop(self):
        got = asyncio.Event()
        async def handler(reader, writer):
            if await reader.read(16) == b'stop':
                got.set()
            writer.close(); await writer.wait_closed()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(launch, 'IS_WINDOWS', True), mock.patch.object(launch, 'PORT_FILE', Path(d)/'control.port'):
            server = await launch.control_server(handler)
            try:
                self.assertTrue(launch.control_present())
                await launch.stop()
                await asyncio.wait_for(got.wait(), 3)
            finally:
                server.close(); await server.wait_closed(); launch.control_remove()
            self.assertFalse(launch.control_present())


class RuntimePlan(unittest.TestCase):
    def test_each_platform_has_a_plan_and_windows_assets_are_pinned_by_digest(self):
        self.assertEqual(runtime_plan('Darwin', 'arm64')['backend'], 'metal')
        self.assertEqual(runtime_plan('Linux', 'x86_64'), {'method': 'build', 'backend': 'cpu', 'gpu_layers': 0, 'needs': ['git', 'cmake']})
        for backend in ('cpu', 'vulkan', 'cuda'):
            plan = runtime_plan('Windows', 'AMD64', backend)
            self.assertEqual((plan['method'], plan['binary']), ('release', 'llama-server.exe'))
            for asset in plan['assets']:
                self.assertRegex(asset['sha256'], '^[0-9a-f]{64}$'); self.assertGreater(asset['size'], 10**6)
                self.assertIn(plan['release'], asset['name'] + plan['release'])
        self.assertEqual(runtime_plan('Windows', 'AMD64')['backend'], 'vulkan')
        with self.assertRaises(RuntimeError):
            runtime_plan('Windows', 'AMD64', 'opencl')
        with self.assertRaises(RuntimeError):
            runtime_plan('Darwin', 'x86_64')

    def test_the_runtime_binary_path_and_python_follow_the_platform(self):
        with mock.patch.object(portability, 'IS_WINDOWS', True):
            self.assertTrue(str(portability.runtime_binary('/b')).endswith('llama-server.exe'))
            self.assertIn('Scripts', str(portability.python_in_venv('/r')))
        with mock.patch.object(portability, 'IS_WINDOWS', False):
            self.assertTrue(str(portability.runtime_binary('/b')).endswith('build/bin/llama-server'))

    def test_a_pinned_download_is_refused_when_the_digest_differs(self):
        from scripts.tools import fetch_verified
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'asset.zip'; source.write_bytes(b'not the pinned bytes')
            with self.assertRaises(RuntimeError):
                fetch_verified(source.as_uri(), Path(d)/'out.zip', '0'*64)
            self.assertFalse((Path(d)/'out.zip').exists())
            good = hashlib.sha256(source.read_bytes()).hexdigest()
            fetch_verified(source.as_uri(), Path(d)/'out.zip', good, source.stat().st_size)
            self.assertTrue((Path(d)/'out.zip').is_file())


class Browser(unittest.TestCase):
    def test_candidates_per_platform(self):
        self.assertTrue(any('Program Files' in c and c.endswith('chrome.exe') for c in portability.browser_candidates('Windows')))
        self.assertTrue(any(c.endswith('msedge.exe') for c in portability.browser_candidates('Windows')))
        self.assertIn('/usr/bin/chromium', portability.browser_candidates('Linux'))
        self.assertTrue(portability.browser_candidates('Darwin')[0].endswith('Google Chrome'))
        with mock.patch.dict('os.environ', {'CHROMIUM_PATH': '/x/y/chrome'}):
            self.assertEqual(portability.browser_executable(), '/x/y/chrome')

    def test_the_node_helper_agrees(self):
        out = subprocess.run(['node', '-e', "Object.defineProperty(process,'platform',{value:'win32'});console.log(JSON.stringify(require('./scripts/browser-path.cjs').candidates()))"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        self.assertTrue(any('chrome.exe' in c for c in json.loads(out)))


class PersonBackend(unittest.TestCase):
    def test_backend_choice_follows_the_platform_and_the_files(self):
        self.assertEqual(available_backend('Windows', ssd_present=True), 'opencv-ssd')
        self.assertIsNone(available_backend('Windows', ssd_present=False))
        self.assertEqual(available_backend('Linux', ssd_present=True), 'opencv-ssd')
        config = json.loads((ROOT/'config/person-detector.json').read_text())
        for f in config['files']:
            self.assertRegex(f['git_blob_sha1'], '^[0-9a-f]{40}$'); self.assertGreater(f['size'], 1000)

    def test_git_blob_sha1_matches_git(self):
        from scripts.fetch_person_model import git_blob_sha1
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'f.txt'; path.write_bytes(b'hello\n')
            self.assertEqual(git_blob_sha1(path), 'ce013625030ba8dba906f756967f9e9ca394464a')


if __name__ == '__main__':
    unittest.main()
