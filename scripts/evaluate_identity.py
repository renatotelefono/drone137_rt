"""Frozen-frame identity diagnostic. This is not a held-out mission benchmark."""
import argparse
import asyncio
import fcntl
import hashlib
import html
import json
from pathlib import Path
import statistics
import time

from app.identity import VERSION, PROMPT, SCHEMA, crop_candidate, parse, supported
from scripts.experiment_model import experiment_model
from scripts.memory_watch import MemoryWatch
from scripts.tools import ROOT


async def evaluate(args):
    lock = (ROOT/'.local/localization.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    report = {'version': VERSION, 'model_size': args.model_size, 'prompt': PROMPT, 'schema': SCHEMA,
              'scope': 'Known synthetic failure-analysis images, correlated views. Not held-out accuracy or job completion.',
              'runs': []}
    cases = [('dense-present', 'v2', True), ('dense-absent', 'v2', False),
             ('dense-low-light', 'v3', True), ('dense-east', 'v3', False)]
    # Identity labels describe the originally claimed object, not room-level target presence.
    async with experiment_model(args.model_size, folder) as (backend, app_pid, manifest):
        report['model'] = manifest
        report['startup_memory'] = backend.startup_memory
        watch = MemoryWatch([app_pid]); watch.start()
        try:
            for case, version, expected in cases:
                for arm in ('qwen', 'qwen-laya'):
                    source = ROOT/f'.local/validation/dense-native-evaluation-{version}/{case}-{arm}'
                    run = json.loads((source/'result.json').read_text())
                    for step in run['steps'][-2:]:
                        watch.check()
                        original = (source/step['image']).read_bytes()
                        jpeg, metadata = crop_candidate(original, step['visual']['bbox'])
                        name = f'{case}-{arm}-{step["image"]}'
                        (folder/name).write_bytes(jpeg)
                        began = time.monotonic()
                        raw = await backend.image(jpeg, PROMPT, SCHEMA, time.monotonic()+12, max_tokens=200)
                        parts = parse(raw)
                        accepted = metadata['adequate_pixels'] and supported(parts)
                        record = {'case': case, 'source_arm': arm, 'image': name,
                                  'source': str((source/step['image']).relative_to(ROOT)),
                                  'source_sha256': hashlib.sha256(original).hexdigest(),
                                  'crop_sha256': hashlib.sha256(jpeg).hexdigest(), 'crop': metadata,
                                  'predicted_bbox': step['visual']['bbox'], 'parts': parts,
                                  'latency_s': time.monotonic()-began, 'expected_target': expected,
                                  'accepted': accepted, 'correct': accepted == expected}
                        report['runs'].append(record)
                        (folder/'partial.json').write_text(json.dumps(report, indent=2))
                        print(json.dumps(record), flush=True)
                        watch.check()
        finally:
            watch.stop(); report['memory'] = watch.report()
    runs = report['runs']
    report['summary'] = {'correct': sum(r['correct'] for r in runs), 'images': len(runs),
                         'false_accepts': sum(r['accepted'] and not r['expected_target'] for r in runs),
                         'false_rejections': sum(not r['accepted'] and r['expected_target'] for r in runs),
                         'mean_latency_s': statistics.mean(r['latency_s'] for r in runs)}
    report['source_hashes'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                             for name in ('app/identity.py', 'scripts/evaluate_identity.py', 'scripts/experiment_model.py')}
    (folder/'results.json').write_text(json.dumps(report, indent=2))
    cards = ''.join(f'<article><h2>{html.escape(r["case"])} · {r["source_arm"]}</h2>'
                    f'<img src="{r["image"]}"><p>{"PASS" if r["correct"] else "FAIL"} · accepted: {r["accepted"]}</p>'
                    f'<pre>{html.escape(json.dumps(r["parts"], indent=2))}</pre></article>' for r in runs)
    (folder/'report.html').write_text('<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
        '<title>Candidate identity diagnostic</title><style>body{margin:30px;background:#14232b;color:#d9e8ed;font:16px system-ui}'
        'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}article{padding:16px;background:#263944}'
        'img{max-width:100%;max-height:280px}pre{white-space:pre-wrap}h2{font-size:18px}a{color:#b3e4f7}</style>'
        f'<h1>Qwen {args.model_size}: candidate identity</h1><p>{report["scope"]}</p><p>{html.escape(str(report["summary"]))}</p>'
        '<p><a href=results.json>Full protocol and measurements</a></p><main>'+cards+'</main></html>')
    print(json.dumps({'summary': report['summary'], 'memory_gib': report['memory']['sampled_peak_gib'], 'report': str(folder/'report.html')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-size', choices=['2b', '4b'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(evaluate(parser.parse_args()))
