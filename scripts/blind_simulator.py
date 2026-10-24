"""Privileged sensor simulator. The explorer only connects to its public API.

Run separately from the explorer: room geometry and evaluation truth are never
included in public responses or used by the onboard position controller.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import math
from pathlib import Path
import time

from aiohttp import web
from app.components import Components
from app.mission_camera import MissionCamera
from app.jsonl_writer import JsonlWriter
from sim.blind_world import scene

ROOT = Path(__file__).resolve().parents[1]


class Plant:
    def __init__(self, world, folder):
        self.scene, self.folder = world, folder
        self.latest = None
        self.goal = None
        self.lease = 0
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.error = None
        self.trace = []
        self.timing = JsonlWriter(folder/'control-timing.jsonl')
        self.last_command_ack = None

    async def call(self, op, **body):
        queued = time.monotonic()
        async with self.lock:
            sent = time.monotonic()
            self.process.stdin.write((json.dumps({'op': op, **body})+'\n').encode())
            await self.process.stdin.drain()
            result = json.loads(await asyncio.wait_for(self.process.stdout.readline(), 20 if op=='load-collision-mesh' else 3))
            acknowledged = time.monotonic()
            timing = {'operation': op, 'queued_at': queued, 'sent_at': sent,
                      'acknowledged_at': acknowledged, 'queue_wait_s': sent-queued,
                      'rpc_s': acknowledged-sent, 'error': result.get('error'),
                      'sensor_time_s': result.get('sensor',{}).get('time_s')}
            if op == 'command':
                timing['command_ack_interval_s'] = (acknowledged-self.last_command_ack
                    if self.last_command_ack is not None else None)
                if 'error' not in result:self.last_command_ack=acknowledged
            self.timing.write(timing)
            if 'error' in result:
                raise RuntimeError(result['error'])
            if op == 'imu':return result
            self.latest = result
            self.received = time.time()
            return result

    async def start(self, assembly, seed):
        path = self.folder/'plant-input.json'
        path.write_text(json.dumps({'scene': self.scene, 'assembly': assembly, 'seed': seed}))
        self.log = (self.folder/'plant.log').open('wb')
        self.process = await asyncio.create_subprocess_exec('node', 'scripts/blind-physics.mjs', str(path), cwd=ROOT,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.log, limit=2*1024*1024)
        await self.call('status')
        self.task = asyncio.create_task(self.pump())

    async def pump(self):
        recorder = JsonlWriter(self.folder/'evaluator-telemetry.jsonl')
        self.recorder = recorder
        try:
            while True:
                if self.goal and time.monotonic()-self.lease < 2:
                    await self.call('command', target=self.goal)
                else:
                    await self.call('status')
                self.trace.append(self.latest)
                recorder.write(self.latest)
                if len(self.trace) > 14000:
                    self.trace.pop(0)
                await asyncio.sleep(.05)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
        finally:
            await asyncio.to_thread(recorder.close)

    def snapshot(self):
        truth, s = self.latest['truth'], self.latest['sensor']
        return {'truth': {'position': truth['position'], 'quaternion': truth['quaternion'], 'sim_time': truth['time_s'], 'cart_position': truth['cart_position']},
                'estimated': {'position': s['position'], 'quaternion': s['quaternion'], 'time_s': s['time_s']},
                'wall_time': self.received, 'speed': math.hypot(*s['velocity']), 'angular_speed': 0,
                'phase': 'blind-exploration', 'message': 'Controller receives pixels and IMU-estimated pose only'}

    def public(self):
        if self.error:
            raise RuntimeError(self.error)
        self.sequence += 1
        return {'protocol': 'blind-sensor-v1', 'sequence': self.sequence, 'received_at': self.received,
                'sensor': self.latest['sensor']}

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        if self.process.returncode is None:
            await self.call('close')
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.log.close()
        # gather(return_exceptions=True) above must not conceal a writer error
        # that happened while the control task was being cancelled.
        if hasattr(self,'recorder'):
            await asyncio.to_thread(self.recorder.close)
        await asyncio.to_thread(self.timing.close)


async def serve(args):
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    world = scene(args.seed)
    (folder/'scene.json').write_text(json.dumps(world, indent=2))
    assembly = Components(ROOT/'.local/data/components.sqlite3').assemble('scout-110-bench-b@1')
    plant = Plant(world, folder)
    await plant.start(assembly, args.seed)
    camera = MissionCamera()
    await camera.open(plant, folder)
    collision=await camera.call(op='export-collision-mesh')
    collision_path=folder/collision['file']
    collision['sha256']=hashlib.sha256(collision_path.read_bytes()).hexdigest()
    await plant.call('load-collision-mesh',path=str(collision_path.resolve()))
    world['physics_collision_source']=collision
    (folder/'scene.json').write_text(json.dumps(world,indent=2))
    capture_lock = asyncio.Lock()
    audit = JsonlWriter(folder/'public-responses.jsonl')
    done = asyncio.Event()

    @web.middleware
    async def boundary(request, handler):
        try:
            value = await handler(request)
            audit.write({'path': request.path, 'result': {k: v for k, v in value.items() if k != 'jpeg'}})
            return web.json_response(value)
        except (ValueError, RuntimeError) as exc:
            return web.json_response({'error': str(exc)}, status=409)

    async def status(request):
        return plant.public()

    async def command(request):
        body = await request.json()
        if set(body) != {'target'}:
            raise ValueError('Command must contain only a bounded target')
        target = body['target']
        if (not isinstance(target, list) or len(target) != 4 or not all(type(x) in (int, float) and math.isfinite(x) for x in target)
                or math.hypot(*target[:2]) > 15 or not 0 <= target[2] <= 1.8):
            raise ValueError('Invalid local command')
        plant.goal, plant.lease = target, time.monotonic()
        return plant.public()

    async def frame(request):
        async with capture_lock:
            f = await camera.call(op='capture')
        data = (folder/f['image']).read_bytes()
        meta = f['metadata']
        # Explicit allowlist. Renderer truth and scene metadata stop here.
        return {'jpeg': base64.b64encode(data).decode(), 'sequence': meta['sequence'],
                'capture_time_s': meta['estimated']['time_s'], 'received_at': time.time(),
                'pose': meta['estimated'], 'image': f['image'],
                'calibration': {'width': world['camera']['width'], 'height': world['camera']['height'],
                                'vertical_fov_deg': world['camera']['vertical_fov'], 'mount': world['camera_mount'],
                                'optics': world['camera'].get('optics')}}

    async def imu(request):
        after=float(request.query.get('after','-1'))
        if not math.isfinite(after):raise ValueError('Invalid IMU cursor')
        return await plant.call('imu',after=after)

    async def correction(request):
        body = await request.json()
        if set(body) not in ({'time_s', 'position', 'velocity', 'inliers'}, {'time_s', 'position', 'velocity', 'inliers', 'quaternion'}):
            raise ValueError('Invalid visual correction fields')
        await plant.call('visual', **body)
        return plant.public()

    async def finish(request):
        done.set()
        return {'closing': True}

    app = web.Application(middlewares=[boundary], client_max_size=8192)
    app.router.add_get('/sensor', status)
    app.router.add_get('/frame', frame)
    app.router.add_get('/imu', imu)
    app.router.add_post('/command', command)
    app.router.add_post('/visual', correction)
    app.router.add_post('/finish', finish)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '127.0.0.1', args.port).start()
    print(json.dumps({'ready': True, 'port': args.port}), flush=True)
    try:
        await asyncio.wait_for(done.wait(), 750)
    finally:
        await runner.cleanup()
        errors=[]
        for close in (camera.close,plant.close):
            try:await close()
            except Exception as exc:errors.append(str(exc))
        try:await asyncio.to_thread(audit.close)
        except Exception as exc:errors.append(str(exc))
        if errors:
            (folder/'recording-error.json').write_text(json.dumps({'errors':errors}))
            raise RuntimeError('Simulator recording did not finalize: '+'; '.join(errors))
        (folder/'final.json').write_text(json.dumps(plant.latest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--port', type=int, default=8156)
    asyncio.run(serve(parser.parse_args()))
