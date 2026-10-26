"""Perched-watch gate: staged events on a fixed camera, and quiet nights with none.

  python -m scripts.qualify_watch --seeds 12 --nights 2 [--model]

Detector gate: every staged event (object removed, added, moved; a figure walking; a light
change) raises an event of the right kind within 4 s, with its box overlapping the truth; a
quiet night of 8 h at 2.5 Hz raises at most one alert. With --model, each event's before-and-
after picture is also put to the local model and its category and "matters" are scored, which
is reported, not gated, because the pictures are synthetic.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.watch_detector import ChangeDetector, iou
from app.watch_events import EventStore, MATTERS, PerchedWatch
from sim.watch_scenes import CATEGORIES, RATE, jpeg, quiet, scenario

GATE = {'detection': .95, 'max_latency_s': 4., 'min_iou_change': .15, 'false_alerts_per_night': 1}


class Clock:
    t = 0.

    def __call__(self):
        return self.t


async def staged(category, seed, model, folder, store):
    frames, truth = scenario(category, seed)
    clock = Clock(); state = {'i': 0}
    def source():
        if state['i'] >= len(frames):
            return None
        t, frame = frames[state['i']]; state['i'] += 1; clock.t = t
        return jpeg(frame), state['i'], t
    watch = PerchedWatch(f'{category}-{seed}', source, store, folder/f'{category}-{seed}', model, clock=clock, cooldown_s=30)
    watch.state = 'watching'
    for _ in frames:
        await watch.step()
    events = [e for e in store.list(limit=200) if e['aircraft'] == f'{category}-{seed}']
    early = [e for e in events if e['at'] < truth['at'] - .5]
    hits = [e for e in events if e['at'] >= truth['at'] - .5 and e['kind'] == truth['kind']]
    hit = hits[-1] if hits else None   # the earliest in time; the list is newest first
    result = {'category': category, 'seed': seed, 'detected': hit is not None, 'early_events': len(early),
              'latency_s': None if hit is None else hit['at'] - truth['at'],
              'iou': None if hit is None else iou(tuple(hit['bbox']), truth['bbox']), 'events': len(events)}
    if hit is not None and model is not None:
        result['model'] = {'category': hit['category'], 'matters': hit['matters'], 'summary': hit['summary'], 'latency_s': hit['latency_s'],
                           'category_correct': hit['category'] == category, 'matters_correct': hit['matters'] == (category in MATTERS)}
    ok = result['detected'] and result['early_events'] == 0 and result['latency_s'] <= GATE['max_latency_s'] and (truth['kind'] != 'change' or result['iou'] >= GATE['min_iou_change'])
    result['passed'] = bool(ok)
    return result


async def played(folder, model, store, work):
    """A recorded or rendered sequence: frames NNNNN.jpg at truth['fps'] with the event at truth['at']."""
    truth = json.loads((folder/'truth.json').read_text())
    if truth.get('at') is None:
        return {'scenario': folder.name, 'skipped': 'no event mark'}
    frames = sorted(folder.glob('*.jpg')); fps = truth.get('fps', RATE)
    clock = Clock(); state = {'i': 0}
    def source():
        if state['i'] >= len(frames):
            return None
        data = frames[state['i']].read_bytes(); state['i'] += 1; clock.t = (state['i']-1)/fps
        return data, state['i'], clock.t
    name = folder.name
    watch = PerchedWatch(name, source, store, work/name, model, clock=clock, cooldown_s=30)
    watch.state = 'watching'
    for _ in frames:
        await watch.step()
    events = [e for e in store.list(limit=500) if e['aircraft'] == name]
    early = [e for e in events if e['at'] < truth['at'] - .5]
    hits = [e for e in events if e['at'] >= truth['at'] - .5 and e['kind'] == truth['kind']]
    hit = hits[-1] if hits else None
    result = {'scenario': name, 'category': truth['category'], 'kind': truth['kind'], 'detected': hit is not None, 'early_events': len(early),
              'latency_s': None if hit is None else hit['at'] - truth['at'], 'events': len(events), 'frames': len(frames),
              'object': truth.get('object'), 'perch_height_m': truth.get('perch_height_m')}
    if hit is not None and model is not None:
        result['model'] = {'category': hit['category'], 'matters': hit['matters'], 'summary': hit['summary'], 'latency_s': hit['latency_s'],
                           'category_correct': hit['category'] == truth['category'], 'matters_correct': hit['matters'] == (truth['category'] in MATTERS)}
    result['passed'] = bool(result['detected'] and result['early_events'] == 0 and result['latency_s'] <= GATE['max_latency_s'])
    return result


def night(seed, hours):
    detector = ChangeDetector(); alerts = 0; candidates = 0; frames = 0; cooldown_until = -1e9
    for t, frame in quiet(seed, hours):
        frames += 1
        for c in detector.update(frame):
            candidates += 1
            if c['kind'] in ('motion', 'change') and t >= cooldown_until:
                alerts += 1; cooldown_until = t + 30
            if c['kind'] == 'change':
                detector.absorb()
    return {'seed': seed, 'hours': hours, 'frames': frames, 'candidates': candidates, 'alerts': alerts, 'passed': alerts <= GATE['false_alerts_per_night']}


async def main(args):
    started = time.time()
    model = None
    if args.model:
        from adapters.llama import LlamaBackend
        class Model:
            name = 'local-qwen'
            def __init__(self):
                self.backend = LlamaBackend(timeout=20)
            async def image(self, jpeg, prompt, schema, timeout=12, max_tokens=120):
                return await self.backend.image(jpeg, prompt, schema, time.monotonic() + timeout, max_tokens=max_tokens)
        model = Model(); await model.backend.health()
    temp = tempfile.TemporaryDirectory(); folder = Path(temp.name)
    store = EventStore(folder/'watch.sqlite3')
    results = []
    for category in CATEGORIES:
        for seed in range(args.seeds):
            r = await staged(category, 100 + seed, model, folder/'events', store)
            results.append(r)
            print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k != 'model'} | ({'model': r['model']['category'], 'ok': r['model']['category_correct']} if 'model' in r else {})), flush=True)
    sets = {}
    for directory in args.set:
        folders = sorted(p for p in Path(directory).iterdir() if (p/'truth.json').is_file())
        rows = []
        for f in folders:
            r = await played(f, model, store, folder/'played')
            rows.append(r); print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k != 'model'} | ({'model': r['model']['category'], 'ok': r['model']['category_correct']} if 'model' in r else {})), flush=True)
        scored = [r for r in rows if 'skipped' not in r]
        sets[str(directory)] = {'scenarios': len(rows), 'skipped': len(rows) - len(scored), 'detected': sum(r['detected'] for r in scored), 'passed': sum(r['passed'] for r in scored),
                                'model_category_accuracy': (sum(r['model']['category_correct'] for r in scored if 'model' in r)/max(1, sum('model' in r for r in scored))) if model else None,
                                'model_matters_accuracy': (sum(r['model']['matters_correct'] for r in scored if 'model' in r)/max(1, sum('model' in r for r in scored))) if model else None,
                                'results': rows}
    nights = [night(500 + i, args.hours) for i in range(args.nights)]
    for n in nights:
        print(json.dumps(n), flush=True)
    detected = sum(r['detected'] for r in results); passed = sum(r['passed'] for r in results)
    report = {'date': time.strftime('%Y-%m-%d'), 'gate': GATE, 'staged_events': len(results), 'detected': detected, 'passed': passed,
              'detection_rate': detected/len(results), 'max_latency_s': max((r['latency_s'] or 0) for r in results),
              'nights': nights, 'false_alerts_total': sum(n['alerts'] for n in nights), 'night_hours': args.hours,
              'accepted': passed == len(results) and detected/len(results) >= GATE['detection'] and all(n['passed'] for n in nights)
                          and all(v['passed'] == v['scenarios'] - v['skipped'] for v in sets.values()),
              'per_category': {c: {'detected': sum(r['detected'] for r in results if r['category'] == c), 'of': args.seeds,
                                   'median_latency_s': sorted((99. if r['latency_s'] is None else r['latency_s']) for r in results if r['category'] == c)[args.seeds//2]} for c in CATEGORIES},
              'results': results, 'sets': sets, 'wall_time_s': time.time() - started, 'frame_rate_hz': RATE,
              'scope': 'Synthetic staged events drawn on a real photo with sensor noise and lamp flicker; the detector gate is deterministic. Model scores are reported, not gated.'}
    if model is not None:
        scored = [r['model'] for r in results if 'model' in r]
        report['model'] = {'name': 'local Qwen 2B', 'events_scored': len(scored),
                           'category_accuracy': sum(m['category_correct'] for m in scored)/max(1, len(scored)),
                           'matters_accuracy': sum(m['matters_correct'] for m in scored)/max(1, len(scored)),
                           'mean_latency_s': sum(m['latency_s'] or 0 for m in scored)/max(1, len(scored)),
                           'per_category': {c: {'correct': sum(r['model']['category_correct'] for r in results if r['category'] == c and 'model' in r),
                                                'answers': [r['model']['category'] for r in results if r['category'] == c and 'model' in r]} for c in CATEGORIES}}
    Path(args.output).write_text(json.dumps(report, indent=1, default=float) + '\n')
    print(json.dumps({k: report[k] for k in ('accepted', 'detection_rate', 'passed', 'staged_events', 'false_alerts_total', 'max_latency_s')} | ({'model': report['model']['category_accuracy']} if 'model' in report else {})
                     | {'sets': {k: {kk: v[kk] for kk in ('scenarios', 'detected', 'passed', 'model_category_accuracy', 'model_matters_accuracy')} for k, v in sets.items()}}, default=float), flush=True)
    temp.cleanup()
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, default=12)
    parser.add_argument('--nights', type=int, default=2)
    parser.add_argument('--hours', type=float, default=8.)
    parser.add_argument('--model', action='store_true')
    parser.add_argument('--set', action='append', default=[], help='folder of rendered or recorded scenarios, each with frames and truth.json; repeatable')
    parser.add_argument('--output', default=str(ROOT/'docs/watch-validation.json'))
    sys.exit(asyncio.run(main(parser.parse_args())))
