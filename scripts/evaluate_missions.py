"""Frozen full-mission evaluation through the production HTTP API, with no UI."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import time

import aiohttp
from scripts.memory_watch import MemoryWatch
from sim.hard_flight import cases
from adapters.rapier_drone import ROOT
from app.model_store import ModelStore


async def evaluate(args):
    if args.repeats < 1:
        raise ValueError('At least one repeat is required')
    store = ModelStore(ROOT/'.local/data/models')
    model_path, _ = await asyncio.to_thread(store.verify)
    ffprobe = shutil.which('ffprobe') or str(ROOT/'.local/build/PX4-Autopilot/Tools/setup/macos/.pixi/envs/default/bin/ffprobe')
    if not Path(ffprobe).is_file():
        raise RuntimeError('Install ffprobe before qualification; recorded video must be decoded')
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    chosen = [c for c in cases() if not args.cases or c['id'] in args.cases]
    if not chosen or args.cases and len(chosen) != len(args.cases):
        raise ValueError('Unknown/duplicate case selection')
    selected = [{'case': c, 'repeat': i} for i in range(args.repeats) for c in chosen]
    protocol = {'cases': selected, 'assembly': args.assembly, 'deadline_s': 300, 'tolerance_m': .75,
        'required_rate': .95, 'false_confirmations_allowed': 0,
        'launch_client': 'HTTP evaluator; no operator dashboard required', 'unexecuted_cases_count_as_failures': True,
        'scene': 'unchanged native-hard-v1 with existing Poly Haven assets',
        'navigation': 'Height-aware routes; 0.58 m 3D planning clearance, 0.35 m monitored envelope. Earlier attempts used 2D footprint distance.',
        'backend_change': 'Rapier microquad / ideal external reference replaces PX4 generic quad. Not an isolated comparison of perception.'}
    (folder/'protocol.json').write_text(json.dumps(protocol, indent=2))
    pids = set()
    for port in (args.port, 8081):
        pids.update(int(s) for s in subprocess.check_output(['lsof', '-tiTCP:'+str(port), '-sTCP:LISTEN'], text=True).split())
    watch = MemoryWatch(pids)
    watch.start()
    result = {'protocol': protocol, 'protocol_sha256': hashlib.sha256((folder/'protocol.json').read_bytes()).hexdigest(),
        'verified_model_manifest': store.manifest(), 'runs': [], 'errors': []}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as client:
        base = f'http://127.0.0.1:{args.port}'
        async def get(path):
            async with client.get(base+path) as r:
                r.raise_for_status()
                return await r.json()
        async def post(op, body):
            async with client.post(base+'/api/mission/'+op, json=body, headers={'X-Drone137-Control': 'local'}) as r:
                data = await r.json()
                if not r.ok:
                    raise RuntimeError(str(data))
                return data
        try:
            if (await get('/api/mission/status'))['busy']:
                raise RuntimeError('Mission service is busy')
            for item in selected:
                watch.check()
                async with client.get('http://127.0.0.1:8081/props') as response:
                    props = await response.json()
                    if Path(props.get('model_path', '')).resolve() != model_path.resolve():
                        raise RuntimeError('Inference server is not using the verified model')
                case = item['case']
                draft = await post('plan', {'instruction': 'Find the red fire extinguisher in the workshop, verify its location with images, then return and land.',
                    'case': case['id'], 'assembly': args.assembly, 'area': [0, 0, 12, 10]})
                await post('launch', {'draft_id': draft['id']})
                previous = None
                started = time.monotonic()
                while True:
                    state = await get('/api/mission/status')
                    m = state['mission']
                    progress = (m['state'], len(m['steps']))
                    if progress != previous:
                        print(json.dumps({'case': case['id'], 'state': m['state'], 'steps': len(m['steps']), 'latest': m['steps'][-1]['visual'] if m['steps'] else None}), flush=True)
                        previous = progress
                    if not state['busy']:
                        break
                    watch.check()
                    if time.monotonic()-started > 350:
                        await post('stop', {})
                        raise TimeoutError('API mission exceeded evaluator deadline')
                    await asyncio.sleep(1)
                record = await get(f"/api/mission/runs/{m['id']}/summary.json")
                provenance = {'sources': record['source_hashes'], 'assembly': record['plan']['assembly']['sha256'],
                              'reviewer': record['reviewer'], 'vision_policy': record['plan']['vision_policy']}
                if 'frozen_software' not in result:
                    result['frozen_software'] = provenance
                elif result['frozen_software'] != provenance:
                    raise RuntimeError('Software/model/aircraft changed during the frozen evaluation')
                video_check = {'decoded': False}
                try:
                    process = await asyncio.create_subprocess_exec(ffprobe, '-v', 'error', '-count_frames',
                        '-show_entries', 'stream=codec_name,width,height,nb_read_frames', '-of', 'json',
                        str(ROOT/'.local/data/mission-runs'/m['id']/'onboard.webm'),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    output, errors = await asyncio.wait_for(process.communicate(), 30)
                    video_check = json.loads(output)
                    video_check['decoded'] = process.returncode == 0 and not errors and any(
                        s.get('width') == 960 and s.get('height') == 540 and int(s.get('nb_read_frames', 0)) > 0
                        for s in video_check.get('streams', []))
                except Exception as exc:
                    video_check['error'] = str(exc)
                import math
                location = record['location']
                error = math.dist(location['xy_m'], case['target_xy']) if location and case['target'] else None
                false_claim = bool(location) and (error is None or error > .75)
                task_correct = (bool(location) and error is not None and error <= .75) if case['target'] else (not location and len(record['visited']) == len(draft['views']))
                p = record['flight']['telemetry']
                gates = {'task': bool(task_correct), 'no_false_claim': not false_claim,
                    'completed': record['state'] == 'complete' and not record['error'], 'landed': record['landed'],
                    'no_collision': p.get('contacts') == 0 and record['flight']['envelope_violations'] == 0,
                    'attitude': p.get('max_tilt_deg', 100) < 35, 'battery': not p.get('tripped', True),
                    'landing_speed': p.get('landing_speed_m_s', 100) < .5,
                    'deadline': record['wall_time_s'] <= 300,
                    'video': bool(record.get('camera')) and not record['camera']['video']['error']
                        and record['camera']['stats']['frames'] > 0 and video_check['decoded']}
                entry = {'case': case['id'], 'repeat': item['repeat'], 'mission': record['id'], 'gates': gates,
                    'passed': all(gates.values()), 'false_confirmation': false_claim, 'error_m': error,
                    'target_present': case['target'], 'missed_target': case['target'] and not task_correct,
                    'wall_time_s': record['wall_time_s'], 'outcome': record['outcome'], 'error': record['error'],
                    'report': base+record['report'], 'observations': len(record['steps']), 'video_validation': video_check}
                result['runs'].append(entry)
                (folder/(record['id']+'.json')).write_text(json.dumps(record, indent=2))
                (folder/'results.json').write_text(json.dumps(result, indent=2))
                print(json.dumps(entry), flush=True)
        except Exception as exc:
            result['errors'].append(f'{type(exc).__name__}: {exc}')
            try:
                if (await get('/api/mission/status'))['busy']:
                    await post('stop', {})
            except Exception:
                pass
        finally:
            watch.stop()
            result['memory'] = watch.report()
            (folder/'memory.json').write_text(json.dumps(result['memory']))
            result['memory'].pop('samples', None)
            passed = sum(r['passed'] for r in result['runs'])
            memory_ok = not watch.exceeded and not watch.error
            result['summary'] = {'planned': len(selected), 'completed': len(result['runs']), 'passed': passed,
                'rate': passed/len(selected), 'false_confirmations': sum(r['false_confirmation'] for r in result['runs']),
                'missed_targets': sum(r['missed_target'] for r in result['runs']),
                'memory_passed': memory_ok, 'accepted': passed/len(selected) >= .95 and memory_ok and not result['errors'] and not any(r['false_confirmation'] for r in result['runs'])}
            (folder/'results.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8153)
    parser.add_argument('--assembly', default='scout-110-power-v2')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--output', required=True)
    asyncio.run(evaluate(parser.parse_args()))
