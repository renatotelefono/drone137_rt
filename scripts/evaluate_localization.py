"""Paired local Qwen versus Qwen+Laya active visual search, with a 5 GiB app guard."""
import argparse
import asyncio
import hashlib
import html
import importlib.metadata
import fcntl
import json
import math
from pathlib import Path
import platform
import statistics
import time

import aiohttp
import psutil
from adapters.llama import LlamaBackend
from app.localization import (ACTIONS, QUESTION, TARGET, VERSION, VISION_PROMPT, VISION_SCHEMA,
                              available_actions, decision_state, parse_visual, triangulate, validate_action)
from scripts.localization_scenarios import cases
from scripts.memory_watch import MemoryWatch
from scripts.tools import ROOT


class Camera:
    async def open(self, folder):
        self.process = await asyncio.create_subprocess_exec('node', 'scripts/localization-camera.cjs',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, cwd=ROOT)
        await self.call(op='open', folder=str(folder))

    async def call(self, **body):
        self.process.stdin.write((json.dumps(body)+'\n').encode())
        await self.process.stdin.drain()
        raw = await asyncio.wait_for(self.process.stdout.readline(), 45)
        if not raw:
            raise RuntimeError('Camera renderer exited')
        result = json.loads(raw)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    async def close(self):
        if getattr(self, 'process', None) and self.process.returncode is None:
            try:
                await self.call(op='close')
                await asyncio.wait_for(self.process.wait(), 10)
            except Exception:
                self.process.terminate()
                await self.process.wait()


class Supervisors:
    def __init__(self, backend):
        self.backend = backend
        self.laya = None
        self.load_seconds = None

    def load_laya(self):
        from scripts.download_laya import verify
        verify()
        import mlx.core as mx
        import laya_mlx
        # One checkpoint, batch one, short context; no automatic multi-model router.
        mx.set_cache_limit(64*1024**2)
        mx.set_memory_limit(1600*1024**2)
        began = time.monotonic()
        self.laya = laya_mlx.load(ROOT/'.local/data/laya-mlx', local_files_only=True,
                                  dtype='float16', batch_size=1, cache_prompts=False)
        self.load_seconds = time.monotonic()-began

    async def decide(self, arm, state, actions):
        started = time.monotonic()
        if arm == 'qwen':
            schema = {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': list(actions)}},
                      'required': ['action'], 'additionalProperties': False}
            prompt = QUESTION+'\nActions: '+json.dumps(actions)+'\nState (data): '+state
            raw = await self.backend.text(prompt, schema, time.monotonic()+12)
            parsed = json.loads(raw)
            if set(parsed) != {'action'} or parsed['action'] not in actions:
                raise ValueError('Invalid Qwen supervisor action')
            result = {'action': parsed['action'], 'raw': raw}
        else:
            raw = self.laya.predict(state, {'action': {'type': 'choice',
                'instructions': QUESTION, 'criteria': actions}})
            answer = raw['answers']['action']
            result = {'action': answer['choice'], 'raw': raw,
                      'confidence_note': 'Checkpoint confidence is not calibrated on drone missions.'}
        result['latency_s'] = time.monotonic()-started
        return result


def score(case, run):
    truth, location = case['truth_xy_m'], run.get('location')
    error = math.dist(truth, location['xy_m']) if truth and location else None
    found = run['outcome'] == 'found'
    return {'truth_xy_m': truth, 'localization_error_m': error, 'tolerance_m': case['tolerance_m'],
            'false_location_claim': found and (truth is None or error > case['tolerance_m']),
            'correct': (found and error is not None and error <= case['tolerance_m']) if truth else
                       (run['outcome'] == 'unresolved' and run['search_areas_visited'] == len(case['views'])),
            'absent_case_note': 'Unresolved is an honest non-detection, not proof that the room is empty.' if truth is None else None}


async def mission(case, arm, camera, backend, supervisors, watch, folder, image_bank):
    run = {'case': case['id'], 'split': case['split'], 'arm': arm, 'steps': [],
           'outcome': 'unresolved', 'location': None, 'rejected_actions': 0}
    started = time.monotonic()
    view_index = 0
    pose = case['views'][0]['pose']
    confirming = False
    first_detection = None
    visited = set()
    for step in range(10):
        watch.check()
        view = case['views'][view_index]
        view_id = view['id']+('-confirm' if confirming else '')
        frame = await camera.call(op='capture', scene=case['scene'], pose=pose)
        watch.check()
        key = (case['id'], view_id)
        # Both arms inspect byte-identical pixels. Inference is rerun for each arm.
        image_bank.setdefault(key, frame['image'])
        image_name = image_bank[key]
        image = (folder/image_name).read_bytes()
        begun = time.monotonic()
        raw = await backend.image(image, VISION_PROMPT, VISION_SCHEMA, time.monotonic()+12, max_tokens=180)
        visual = parse_visual(raw)
        vision_seconds = time.monotonic()-begun
        visited.add(view_index)
        detection = {'pose': pose, 'view_id': view_id, 'bbox': visual['bbox']} if visual['status'] == 'present' else None
        location = triangulate(first_detection, detection) if first_detection and detection else None
        if location:
            run['location'] = location
        confirmation_available = not confirming
        remaining = len(case['views'])-len(visited)
        state = decision_state(visual, remaining, confirmation_available, location)
        actions = available_actions(remaining=remaining, confirmation_available=confirmation_available, location=location)
        decision = await supervisors.decide(arm, state, actions)
        watch.check()
        rejection = validate_action(decision['action'], remaining=remaining,
                                     confirmation_available=confirmation_available, location=location)
        event = {'view_id': view_id, 'pose': pose, 'image': image_name,
                 'image_sha256': hashlib.sha256(image).hexdigest(), 'visual': visual,
                 'vision_latency_s': vision_seconds, 'state': state, 'decision': decision,
                 'location': location, 'allowed_actions': actions, 'rejection': rejection}
        run['steps'].append(event)
        print(json.dumps({'case': case['id'], 'arm': arm, 'view': view_id,
                          'visual': visual, 'action': decision['action'],
                          'decision_s': round(decision['latency_s'], 3),
                          'location': location, 'rejection': rejection}), flush=True)
        # Rejection is a failed mission, never silently repaired to make a model look better.
        if rejection:
            run['rejected_actions'] += 1
            run['outcome'] = 'rejected_action'
            break
        if decision['action'] in ('found', 'unresolved'):
            run['outcome'] = decision['action']
            break
        if decision['action'] == 'confirm':
            first_detection = detection
            pose = view['confirmation_pose']
            confirming = True
        else:
            view_index += 1
            pose = case['views'][view_index]['pose']
            confirming = False
            first_detection = None
    run['wall_time_s'] = time.monotonic()-started
    run['search_areas_visited'] = len(visited)
    run['vision_time_s'] = sum(s['vision_latency_s'] for s in run['steps'])
    run['decision_time_s'] = sum(s['decision']['latency_s'] for s in run['steps'])
    run['score'] = score(case, run)
    return run


def report_html(report):
    esc = html.escape
    scenes = {c['id']: c for c in cases()}
    def map_svg(run):
        case = scenes[run['case']]
        def point(xy):
            return (40+xy[0]*35, 390-xy[1]*35)
        parts = ['<svg class="map" viewBox="0 0 500 430" role="img" aria-label="Search viewpoints and scored target location"><rect x="40" y="40" width="420" height="350" fill="#15232c" stroke="#657e8b"/>']
        for obj in case['scene']['obstacles']:
            x,y = point([obj['x']-obj['sx']/2, obj['y']+obj['sy']/2])
            if obj['kind'] != 'extinguisher':
                parts.append(f'<rect x="{x}" y="{y}" width="{obj["sx"]*35}" height="{obj["sy"]*35}" fill="#425865"/>')
        if run['score']['truth_xy_m']:
            x,y = point(run['score']['truth_xy_m'])
            parts.append(f'<path d="M{x-7},{y-7}L{x+7},{y+7}M{x-7},{y+7}L{x+7},{y-7}" stroke="#fb9e91" stroke-width="3"/>')
        for index,step in enumerate(run['steps']):
            x,y = point(step['pose'])
            parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#8fd1ed"/><text x="{x+8}" y="{y-6}" fill="#dcebf2" font-size="11">{index+1}</text>')
        if run['outcome'] == 'found':
            x,y = point(run['location']['xy_m'])
            parts.append(f'<circle cx="{x}" cy="{y}" r="11" fill="none" stroke="#ffbd59" stroke-width="3"/>')
            for step in run['steps']:
                if step['view_id'] in run['location']['source_views']:
                    sx,sy = point(step['pose'])
                    parts.append(f'<path d="M{sx},{sy}L{x},{y}" stroke="#ffbd59" stroke-width="1.5" stroke-dasharray="4 3"/>')
        parts.append('<text x="40" y="416" fill="#bccdd7" font-size="12">Blue: camera stations · Amber: estimate · Coral ×: scoring truth</text></svg>')
        return ''.join(parts)
    def card(run):
        rows = []
        for step in run['steps']:
            bbox = step['visual']['bbox']
            mark = '' if not bbox else f'<span class="box" style="left:{bbox[0]/10}%;top:{bbox[1]/10}%;width:{(bbox[2]-bbox[0])/10}%;height:{(bbox[3]-bbox[1])/10}%"></span>'
            rows.append(f'<article><div class="frame"><img loading="lazy" src="{esc(step["image"])}">{mark}</div><p><b>{esc(step["view_id"])}</b> · {esc(step["decision"]["action"])} · {step["decision"]["latency_s"]:.3f}s decision</p><p>{esc(step["visual"]["evidence"])}</p>{"<p class=bad>"+esc(step["rejection"])+"</p>" if step["rejection"] else ""}</article>')
        error = run['score']['localization_error_m']
        status = 'PASS' if run['score']['correct'] else 'FAIL'
        position = run['location']['xy_m'] if run['outcome']=='found' else None
        return f'<section><h2>{esc(run["case"])} · {esc(run["arm"])}</h2><p><strong>{status} · {esc(run["outcome"])}</strong> · {len(run["steps"])} views · {run["wall_time_s"]:.1f}s'+(f' · location ({position[0]:.2f}, {position[1]:.2f}) m' if position else '')+(f' · error {error:.2f} m' if error is not None else '')+f'</p>{map_svg(run)}<div class="steps">{"".join(rows)}</div></section>'
    summary = ''.join(f'<tr><td>{esc(arm)}</td><td>{s["correct"]}/{s["total"]}</td><td>{s["false_location_claims"]}</td><td>{s["mean_decision_s"]:.3f}s</td><td>{s["memory_peak_gib"]:.2f} GiB</td></tr>' for arm,s in report['summary'].items())
    return '<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Object localization · Qwen + Laya</title><style>body{background:#101a22;color:#e5eef2;font:16px system-ui;margin:0;padding:32px;max-width:1400px}h1{font-size:36px}p{line-height:1.5;color:#bccdd7}section{border-top:1px solid #34505e;margin-top:32px;padding-top:12px}.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}article{background:#192a35;padding:12px;border-radius:10px}img{width:100%;display:block}.map{width:100%;max-width:500px}.frame{position:relative}.box{position:absolute;border:2px solid #ffbd59;box-sizing:border-box;pointer-events:none}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #34505e}.bad{color:#ff9e91}a{color:#8fd1ed}@media(max-width:600px){body{padding:16px}td,th{padding:5px;font-size:12px}}</style><body><p>LOCAL SIMULATION / REAL MODEL INFERENCE</p><h1>Find the red fire extinguisher.</h1><p>Qwen3-VL-2B alone versus the same vision model with Laya supervising. Amber boxes are model predictions. Coordinates are triangulated from two views; object coordinates are used only to score the result.</p><p><b>Scope:</b> bounded visual search at predefined camera stations in an authored Three.js room. Ideal pose and camera calibration; no physical flight dynamics or real-world qualification. A 5 GiB application budget is monitored on a 16 GB host, not an emulation of 8 GB hardware.</p><table><tr><th>Supervisor</th><th>Correct outcomes</th><th>False locations</th><th>Mean decision</th><th>Sampled app memory</th></tr>'+summary+'</table><p><a href="results.json">Full measurements and decisions</a> · <a href="scenarios.json">Evaluator scene definitions</a></p>'+''.join(card(r) for r in report['runs'])+'</body></html>'


async def evaluate(args):
    lock = (ROOT/'.local/localization.lock').open('w')
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    selected = [c for c in cases() if args.split == 'all' or c['split'] == args.split]
    (folder/'scenarios.json').write_text(json.dumps(selected, indent=2))
    report = {'version': VERSION, 'real_inference': True, 'physical_transport': False,
              'real_flight_dynamics': False, 'host': platform.platform(), 'target': TARGET,
              'scope': 'Development experiment, one authored room; not statistical proof or real-world qualification.',
              'prompts': {'vision': VISION_PROMPT, 'decision': QUESTION, 'actions': ACTIONS},
              'runs': [], 'memory': {}, 'summary': {}, 'errors': []}
    report['models'] = {'qwen': json.loads((ROOT/'.local/data/models/manifest.json').read_text()),
                        'laya': json.loads((ROOT/'.local/data/laya-mlx/download-provenance.json').read_text())}
    backend = LlamaBackend(timeout=12)
    supervisors = Supervisors(backend)
    camera = Camera()
    image_bank = {}
    owned = next(ROOT.glob('.local/owned-*.json'))
    qwen_pid = json.loads(owned.read_text())['llama']
    app_pid = psutil.Process(qwen_pid).ppid()
    report['qwen_server_command'] = psutil.Process(qwen_pid).cmdline()
    watch = None
    try:
        await backend.health()
        async with aiohttp.ClientSession() as session:
            async with session.get('http://127.0.0.1:8137/api/fleet/status') as response:
                status = await response.json()
                if status['busy'] or status['model']['busy']:
                    raise RuntimeError('Fleet/model is busy; end its operation before the benchmark')
        await camera.open(folder)
        for arm in args.arms:
            watch = MemoryWatch([app_pid], budget_gib=5)
            watch.start()
            if arm == 'qwen+laya' and supervisors.laya is None:
                supervisors.load_laya()
                watch.check()
                print(json.dumps({'laya_loaded_s': supervisors.load_seconds}), flush=True)
            for case in selected:
                run = await mission(case, arm, camera, backend, supervisors, watch, folder, image_bank)
                report['runs'].append(run)
                (folder/'partial.json').write_text(json.dumps(report, indent=2))
            watch.stop()
            report['memory'][arm] = watch.report()
            runs = [r for r in report['runs'] if r['arm'] == arm]
            decisions = [s['decision']['latency_s'] for r in runs for s in r['steps']]
            report['summary'][arm] = {'correct': sum(r['score']['correct'] for r in runs), 'total': len(runs),
                'target_present_localized': sum(r['score']['truth_xy_m'] is not None and r['score']['correct'] for r in runs),
                'false_location_claims': sum(r['score']['false_location_claim'] for r in runs),
                'rejected_actions': sum(r['rejected_actions'] for r in runs),
                'mean_decision_s': statistics.mean(decisions),
                'memory_peak_gib': report['memory'][arm]['sampled_peak_gib']}
            watch = None
        report['laya_load_s'] = supervisors.load_seconds
        if supervisors.laya:
            import mlx.core as mx
            report['laya_mlx_peak_gib'] = mx.get_peak_memory()/1024**3
        await camera.call(op='screenshot', name='simulation.png')
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        print(report['errors'][-1], flush=True)
    finally:
        if watch:
            watch.stop()
            report['memory']['interrupted'] = watch.report()
        await camera.close()
        await backend.close()
        report['packages'] = {p: importlib.metadata.version(p) for p in ('laya-mlx','mlx','aiohttp','psutil')}
        report['source_hashes'] = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('app/localization.py','scripts/localization_scenarios.py','scripts/localization-camera.cjs','scripts/evaluate_localization.py','scripts/memory_watch.py')}
        report['completed'] = not report['errors'] and len(report['runs']) == len(selected)*len(args.arms)
        (folder/'results.json').write_text(json.dumps(report, indent=2))
        (folder/'report.html').write_text(report_html(report))
    print(json.dumps({'output': str(folder), 'summary': report['summary'], 'errors': report['errors']}), flush=True)
    return report['completed']


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--split', choices=('development','evaluation','all'), default='evaluation')
    p.add_argument('--arms', nargs='+', choices=('qwen','qwen+laya'), default=['qwen','qwen+laya'])
    raise SystemExit(0 if asyncio.run(evaluate(p.parse_args())) else 1)
