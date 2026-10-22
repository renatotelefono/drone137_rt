"""Freeze, run and preserve a labelled real/synthetic image evaluation.

Run against the already-started owned local model. This never starts a flight.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import random
import shutil
import time

import aiohttp
from adapters.llama import LlamaBackend
from app.perception import inspect, choose_action, survey
from app.reliability import (ROOT, digest, load_manifest, fingerprint, read_json, score_case,
                             summarize, domain_gates, render_html)
from scripts.tools import DATA


def write_new(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')


async def idle(session):
    async with session.get('http://127.0.0.1:8137/api/status', timeout=aiohttp.ClientTimeout(total=3)) as r:
        r.raise_for_status()
        state = await r.json()
    if state['state'] in ('exploring', 'observing', 'returning', 'paused') or state['model']['busy']:
        raise RuntimeError('End the mission/model operation before offline evaluation')
    if not state['model']['ready']:
        raise RuntimeError('Start the owned local model first')


def freeze(args):
    value = fingerprint(args.manifest, DATA/'models/manifest.json')
    write_new(args.lock, {'version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                          'fingerprint': value})
    print(f'Frozen dataset, model, prompts and scoring: {args.lock}')


def exposure_conflicts(cases, history):
    hashes = {r['image_sha256'] for r in history}
    sites = {r['site_id'] for r in history}
    return [c['id'] for c in cases if c['split'] == 'held_out' and
            (c['image_sha256'] in hashes or c['site_id'] in sites)]


async def evaluate(args):
    manifest = load_manifest(args.manifest)
    locked = read_json(args.lock)
    current = fingerprint(args.manifest, DATA/'models/manifest.json')
    if locked.get('fingerprint') != current:
        raise ValueError('Frozen dataset/model/pipeline changed; preserve the old result and freeze a new version')
    state_dir = DATA/'reliability'
    state_dir.mkdir(exist_ok=True)
    # Serializes these evaluators, not arbitrary external clients of llama-server.
    with (state_dir/'evaluation.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = state_dir/'exposures.jsonl'
        history = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
        conflicts = exposure_conflicts(manifest['cases'], history)
        if conflicts and not args.replay:
            raise ValueError('Held-out sites/images already evaluated; use new sites or --replay (excluded from qualification)')
        async with aiohttp.ClientSession() as session:
            await idle(session)
            args.output.mkdir(parents=True, exist_ok=False)
            (args.output/'images').mkdir()
            report = {'version': 1, 'dataset_id': manifest['dataset_id'],
                      'created_utc': datetime.now(timezone.utc).isoformat(),
                      'scope': manifest.get('scope', 'Labelled visual inspection; no flight acceptance'),
                      'real_inference': True, 'physical_transport': False, 'flight_tested': False,
                      'real_world_qualified': False, 'replay': args.replay,
                      'previously_exposed_held_out_cases': conflicts,
                      'fingerprint': current, 'model': read_json(DATA/'models/manifest.json'),
                      'order_seed': args.order_seed, 'cases': manifest['cases'], 'results': []}
            shutil.copyfile(args.manifest, args.output/'input-manifest.json')
            shutil.copyfile(args.lock, args.output/'input-lock.json')
            for name, checksum in current['pipeline'].items():
                saved = args.output/'pipeline'/name
                saved.parent.mkdir(exist_ok=True, parents=True)
                shutil.copyfile(ROOT/name, saved)
                if digest(saved) != checksum:
                    raise ValueError('Pipeline changed during setup')
            for c in manifest['cases']:
                shutil.copyfile(args.manifest.resolve().parent/c['path'], args.output/'images'/f'{c["id"]}.jpg')
                if digest(args.output/'images'/f'{c["id"]}.jpg') != c['image_sha256']:
                    raise ValueError('Image changed during setup')
            cases = list(manifest['cases'])
            random.Random(args.order_seed).shuffle(cases)
            backend = LlamaBackend()
            async def image(jpeg, prompt, schema, **kwargs):
                return await backend.image(jpeg, prompt, schema, time.monotonic()+6, **kwargs)
            async def text(prompt, schema):
                return await backend.text(prompt, schema, time.monotonic()+6)
            try:
                await backend.health()
                # Claim the entire site set before inference, so interruption cannot reopen a holdout.
                with ledger.open('a') as stream:
                    for c in cases:
                        stream.write(json.dumps({'image_sha256': c['image_sha256'], 'site_id': c['site_id'],
                                                 'run': str(args.output.resolve()), 'created_utc': report['created_utc']})+'\n')
                    stream.flush()
                for c in cases:
                    await idle(session)
                    # Evaluate the frozen copy; the live source cannot change the image mid-run.
                    jpeg = (args.output/'images'/f'{c["id"]}.jpg').read_bytes()
                    started = time.monotonic()
                    r = {'id': c['id'], 'image_sha256': c['image_sha256']}
                    try:
                        async with asyncio.timeout(18):
                            r['perception'] = await inspect(image, jpeg, detailed=c['perception_profile']=='detail', task=c.get('inspection_task','center'))
                            r['action'] = await choose_action(text, r['perception'], ('continue','look_left','look_right','hold'))
                            r['survey'] = await survey(image, jpeg)
                    except Exception as exc:
                        r['error'] = f'{type(exc).__name__}: {exc}'
                    r['latency_s'] = time.monotonic()-started
                    r['checks'] = score_case(c, r)
                    report['results'].append(r)
                    with (args.output/'results.jsonl').open('a') as stream:
                        stream.write(json.dumps(r)+'\n'); stream.flush()
                    print(json.dumps({'id': c['id'], 'checks': r['checks'], 'latency_s': r['latency_s'], 'error':r.get('error')}), flush=True)
                    if backend.quarantined:
                        report['interrupted'] = 'Model client quarantined; remaining cases count as missing'
                        break
            except BaseException as exc:
                report['interrupted'] = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                await backend.close()
                report['summary'] = summarize(cases, report['results'])
                # Replays remain useful regressions; they cannot qualify held-out performance.
                qualified_manifest = {**manifest, 'cases': []} if args.replay else manifest
                report['domains'] = domain_gates(qualified_manifest, report['results'])
                report['checks_passed'] = report['summary']['case_checks_passed'] == len(cases)
                write_new(args.output/'report.json', report)
                (args.output/'report.html').write_text(render_html(report))
            print(json.dumps({'checks_passed':report['checks_passed'], 'real_world_qualified':False,
                              'report':str(args.output/'report.html'), 'summary':report['summary']}), flush=True)
            return report['checks_passed']


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='operation', required=True)
    for operation in ('freeze', 'run'):
        cmd = sub.add_parser(operation)
        cmd.add_argument('--manifest', type=Path, required=True)
        cmd.add_argument('--lock', type=Path, required=True)
        if operation == 'run':
            cmd.add_argument('--output', type=Path, required=True, help='New directory; existing evidence is never overwritten')
            cmd.add_argument('--order-seed', type=int, default=20261020)
            cmd.add_argument('--replay', action='store_true', help='Explicit diagnostic replay; excluded from qualification')
    args = p.parse_args()
    if args.operation == 'freeze':
        freeze(args)
    else:
        raise SystemExit(0 if asyncio.run(evaluate(args)) else 1)
