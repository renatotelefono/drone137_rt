"""Temporarily replace the idle app model for bounded local evaluations.

Only one vision model resides in memory. The normal 2B app model is restored
after a 4B experiment, including exceptions. No production default is changed.
"""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
import signal
import time

import aiohttp
import psutil
from adapters.llama import LlamaBackend
from app.native import unused_port
from scripts.memory_watch import MemoryWatch
from scripts.tools import ROOT


@asynccontextmanager
async def experiment_model(size, folder):
    if size not in ('2b', '4b'):
        raise ValueError('Unsupported experiment model')
    async with aiohttp.ClientSession() as session:
        async def status():
            async with session.get('http://127.0.0.1:8137/api/status') as response:
                response.raise_for_status()
                return await response.json()
        state = await status()
        if state['model']['busy'] or state['state'] in ('exploring', 'observing', 'returning', 'paused'):
            raise RuntimeError('Finish the current app operation before testing')
        if not state['model']['ready']:
            raise RuntimeError('Start the normal app model before an experiment')
        qwen_pid=state['model'].get('model_pid')
        if not qwen_pid:
            owners=[json.loads(p.read_text()) for p in ROOT.glob('.local/owned-*.json')]
            qwen_pid=next((o['llama'] for o in owners if o.get('llama') and psutil.pid_exists(o['llama'])),None)
        if not qwen_pid:raise RuntimeError('App did not expose an owned model process; restart the updated app')
        process_info=psutil.Process(qwen_pid);app_pid=process_info.ppid()
        if state['model'].get('app_pid',app_pid)!=app_pid or 'llama-server' not in process_info.name():raise RuntimeError('Model process ownership does not match app')
        async with session.get('http://127.0.0.1:8137/api/fleet/status') as response:
            response.raise_for_status()
            if (await response.json())['busy']:raise RuntimeError('Finish the fleet mission before testing')
        directory = ROOT/('.local/data/models' if size == '2b' else '.local/data/qwen4b')
        manifest = json.loads((directory/'manifest.json').read_text())
        expected = f'Qwen/Qwen3-VL-{size.upper()}-Instruct-GGUF'
        if manifest['repository'] != expected:
            raise ValueError('Unexpected model manifest')
        for item in manifest['files']:
            path = directory/item['name']
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Invalid model path')
            def verified():
                with path.open('rb') as source:
                    return path.stat().st_size == item['size'] and hashlib.file_digest(source, 'sha256').hexdigest() == item['sha256']
            if not await asyncio.to_thread(verified):
                raise ValueError('Model checksum mismatch')
        backend = LlamaBackend(endpoint='http://127.0.0.1:'+('8081' if size == '2b' else '8082'), timeout=12)
        backend.identity = f'llama-server/Qwen3-VL-{size.upper()}-Instruct'
        process = log = startup_watch = None
        backend.startup_memory = None
        stopped = False
        async def operation(name, expected_state):
            async with session.post('http://127.0.0.1:8137/api/model/'+name, json={},
                                    headers={'X-Drone137-Control': 'local'}) as response:
                response.raise_for_status()
            async with asyncio.timeout(120):
                while True:
                    value = (await status())['model']
                    if value['error']:
                        raise RuntimeError(value['error'])
                    if not value['busy'] and value['state'] == expected_state:
                        return
                    await asyncio.sleep(.25)
        try:
            if size == '4b':
                unused_port(8082)
                await operation('stop', 'stopped')
                stopped = True
                startup_watch = MemoryWatch([app_pid]); startup_watch.start()
                log = (folder/'llama-4b.log').open('wb')
                process = await asyncio.create_subprocess_exec(
                    str(ROOT/'.local/build/llama.cpp/build/bin/llama-server'),
                    '-m', str(directory/manifest['files'][0]['name']),
                    '--mmproj', str(directory/manifest['files'][1]['name']),
                    '--host', '127.0.0.1', '--port', '8082', '-c', '2048', '-np', '1',
                    '--cache-ram', '0', '--no-cache-prompt', '-ngl', '99', '-t', '2',
                    stdout=log, stderr=log, start_new_session=True)
                (folder/'model-process.json').write_text(json.dumps({'pid': process.pid, 'model': manifest}))
                began = time.monotonic()
                while True:
                    startup_watch.check()
                    if process.returncode is not None or time.monotonic()-began > 90:
                        raise RuntimeError('Experimental model failed to start; inspect llama-4b.log')
                    try:
                        await backend.health()
                        break
                    except (aiohttp.ClientError, RuntimeError):
                        await asyncio.sleep(.5)
                startup_watch.stop()
                backend.startup_memory = startup_watch.report()
            yield backend, app_pid, manifest
        finally:
            if startup_watch:
                startup_watch.stop()
                (folder/'model-startup-memory.json').write_text(json.dumps(startup_watch.report(), indent=2))
            await backend.close()
            if process and process.returncode is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(process.wait(), 10)
                except TimeoutError:
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.wait()
            if log:
                log.close()
            if stopped:
                await operation('start', 'ready')
            elif backend.quarantined:
                # Cancelling HTTP does not prove server-side inference stopped.
                await operation('stop', 'stopped')
                await operation('start', 'ready')
