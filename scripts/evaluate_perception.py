"""Score actual local image recognition separately from mission completion."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import random
import time

import aiohttp
from adapters.llama import LlamaBackend
from app.perception import inspect, choose_action, VERSION, DETAIL_VERSION
from scripts.tools import DATA


async def evaluate(args):
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:8137/api/status') as response:
            response.raise_for_status()
            state = await response.json()
    if state['state'] in ('exploring', 'observing', 'returning', 'paused') or state['model']['busy']:
        raise RuntimeError('End the active mission/model operation before perception evaluation')
    cases = [
        {'id': 'gate-open', 'path': 'sim/assets/fixture-01.jpg', 'expected': 'open_space', 'split': 'regression'},
        {'id': 'gate-closed', 'path': 'sim/assets/fixture-02.jpg', 'expected': 'solid_surface', 'split': 'regression'},
        {'id': 'passage-clear', 'path': 'sim/assets/perception/passage-clear.jpg', 'expected': 'open_space', 'split': 'regression'},
        {'id': 'passage-blocked', 'path': 'sim/assets/perception/passage-blocked.jpg', 'expected': 'solid_surface', 'split': 'regression'},
        {'id': 'native-gate-open', 'path': 'sim/assets/perception/native-gate-open.jpg', 'expected': 'open_space', 'split': 'regression'},
        {'id': 'native-gate-closed', 'path': 'sim/assets/perception/native-gate-closed.jpg', 'expected': 'solid_surface', 'split': 'regression'},
        {'id': 'workshop-clear', 'path': 'sim/assets/perception/workshop-clear.jpg', 'expected': 'open_space', 'split': 'regression', 'camera_profile': 'module3-720p'},
        {'id': 'workshop-blocked', 'path': 'sim/assets/perception/workshop-blocked.jpg', 'expected': 'solid_surface', 'split': 'regression', 'camera_profile': 'module3-720p'},
    ] + [{**case, 'split': 'regression'} for case in json.loads(args.manifest.read_text())]
    random.Random(args.order_seed).shuffle(cases)
    report = {'suite': 'local-vision-classification', 'version': VERSION, 'real_inference': True,
              'detail_version': DETAIL_VERSION,
              'model': json.loads((DATA/'models/manifest.json').read_text()),
              'order_seed': args.order_seed, 'results': [], 'passed': False,
              'scope': 'Synthetic center appearance only; not general object recognition or physical clearance'}
    backend = LlamaBackend()
    async def image(jpeg, prompt, schema):
        return await backend.image(jpeg, prompt, schema, time.monotonic()+6)
    async def text(prompt, schema):
        return await backend.text(prompt, schema, time.monotonic()+6)
    try:
        await backend.health()
        for case in cases:
            data = Path(case['path']).read_bytes()
            started = time.monotonic()
            result = {k: case[k] for k in ('id', 'path', 'expected', 'split')}
            result['camera_profile'] = case.get('camera_profile', 'lean')
            result['image_sha256'] = hashlib.sha256(data).hexdigest()
            try:
                # Only encoded image bytes and generic prompts enter these calls.
                result['inspection_task'] = case.get('inspection_task','center')
                visual = await inspect(image, data, detailed=result['camera_profile']=='module3-720p', task=result['inspection_task'])
                action = await choose_action(text, visual, ('continue','look_left','look_right','hold'))
                result.update(perception=visual, action=action, correct=visual['center']==case['expected'])
            except Exception as exc:
                result.update(error=str(exc), correct=False)
            result['latency_s'] = time.monotonic()-started
            report['results'].append(result)
            print(json.dumps(result), flush=True)
            if backend.quarantined:
                break
        report['correct'] = sum(r['correct'] for r in report['results'])
        report['total'] = len(cases)
        report['false_clear'] = sum(r['expected']=='solid_surface' and r.get('perception',{}).get('center')=='open_space' for r in report['results'])
        report['passed'] = report['correct'] == report['total']
    finally:
        await backend.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','model')}), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('.local/validation/vision-cases/manifest.json'))
    parser.add_argument('--output', type=Path, default=Path(f'.local/validation/perception-{time.time_ns()}.json'))
    parser.add_argument('--order-seed', type=int, default=137)
    raise SystemExit(0 if asyncio.run(evaluate(parser.parse_args())) else 1)
