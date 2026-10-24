"""Run the predeclared unknown-layout suite without changing its denominator."""
import argparse
import asyncio
import hashlib
import json
import shutil
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sources():
    files = []
    for directory in ('app', 'adapters', 'scripts', 'sim', 'native', 'config'):
        files.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and p.suffix in ('.py', '.js', '.mjs', '.cjs', '.cpp', '.json', '.yaml')
                     and 'vendor' not in p.parts and '__pycache__' not in p.parts)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


async def run(args):
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT / 'config/blind-exploration-v1.json').read_text())
    seeds = args.seeds or protocol['qualification_seeds']
    if len(set(seeds)) != len(seeds):
        raise ValueError('Qualification seeds must be distinct')
    frozen = sources()
    report = {'started_at': time.time(), 'protocol': protocol, 'source_sha256': frozen,
              'scope': 'Reserved synthetic layouts; not real-world or actual 8 GB qualification',
              'accepted': False, 'planned': len(seeds), 'planned_seeds': seeds,
              'results': [{'seed': seed, 'state': 'not_run', 'accepted': False}
                          for seed in seeds]}

    def save():
        report['executed'] = sum(r['state'] in ('passed', 'failed') for r in report['results'])
        report['passed'] = sum(r['accepted'] for r in report['results'])
        report['accepted'] = report['passed'] == report['planned']
        tmp = folder / 'results.tmp'
        tmp.write_text(json.dumps(report, indent=2, allow_nan=False))
        tmp.replace(folder / 'results.json')

    save()
    for entry in report['results']:
        if sources() != frozen:
            report['error'] = 'Source changed during qualification; remaining layouts not run'
            save()
            break
        if shutil.disk_usage(folder).free < 3*1024**3:
            report['error'] = 'Insufficient recording storage; remaining layouts not run'
            save()
            break
        seed = entry['seed']
        entry['state'] = 'running'
        save()
        print(json.dumps({'seed': seed, 'state': 'running'}), flush=True)
        trial = folder / f'seed-{seed}'
        command = [sys.executable, '-m', 'scripts.run_blind_test', '--seed', str(seed),
                   '--output', str(trial), '--place', f'workshop-blind-{seed}',
                   '--name', f'Unknown workshop {seed}']
        for pid in args.memory_pid:
            command.extend(['--memory-pid', str(pid)])
        with (folder / f'seed-{seed}.log').open('wb') as log:
            process = await asyncio.create_subprocess_exec(*command, cwd=ROOT, stdout=log, stderr=log)
            try:
                code = await process.wait()
            finally:
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
        score = trial / 'score.json'
        entry['exit_code'] = code
        entry['report'] = f'seed-{seed}/report.html'
        if score.exists():
            entry.update(json.loads(score.read_text()))
        entry['accepted'] = entry['accepted'] and code == 0
        entry['state'] = 'passed' if entry['accepted'] else 'failed'
        save()
        print(json.dumps({'seed': seed, 'state': entry['state'],
                          'metrics': entry.get('metrics'), 'gates': entry.get('gates')}), flush=True)
    report['finished_at'] = time.time()
    save()
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--memory-pid', type=int, action='append', default=[])
    parser.add_argument('--seeds', type=int, nargs='+', help='Predeclare fresh layouts after original layouts become development data')
    sys.exit(asyncio.run(run(parser.parse_args())))
