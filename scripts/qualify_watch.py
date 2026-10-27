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

GATE = {'detection': .95, 'max_latency_s': 4., 'min_iou_change': .15, 'false_alerts_per_night': 1, 'category_accuracy': .9}


class Clock:
    t = 0.

    def __call__(self):
        return self.t


async def staged(category, seed, model, folder, store, lock=None):
    frames, truth = scenario(category, seed)
    clock = Clock(); state = {'i': 0}
    def source():
        if state['i'] >= len(frames):
            return None
        t, frame = frames[state['i']]; state['i'] += 1; clock.t = t
        return jpeg(frame), state['i'], t
    watch = PerchedWatch(f'{category}-{seed}', source, store, folder/f'{category}-{seed}', model, clock=clock, cooldown_s=30, model_lock=lock)
    watch.state = 'watching'
    for _ in frames:
        await watch.step()
    events = [e for e in store.list(limit=200) if e['aircraft'] == f'{category}-{seed}']
    early = [e for e in events if e['at'] < truth['at'] - .5]
    hits = [e for e in events if e['at'] >= truth['at'] - .5 and e['kind'] == truth['kind']]
    hit = hits[-1] if hits else None   # the earliest in time; the list is newest first
    result = {'scenario': category, 'category': truth['category'], 'seed': seed, 'detected': hit is not None, 'early_events': len(early),
              'latency_s': None if hit is None else hit['at'] - truth['at'],
              'iou': None if hit is None else iou(tuple(hit['bbox']), truth['bbox']), 'events': len(events)}
    if hit is not None and model is not None:
        result['model'] = scored_answer(hit, truth['category']); result['person_seen'] = result['model']['person_seen']
    ok = result['detected'] and result['early_events'] == 0 and result['latency_s'] <= GATE['max_latency_s'] and (truth['kind'] != 'change' or result['iou'] >= GATE['min_iou_change'])
    result['passed'] = bool(ok)
    return result


def scored_answer(hit, truth_category):
    """The event's category (pixels decide the kind of object change, the model names it and says person) and the model's own label."""
    evidence = hit.get('evidence', {})
    return {'category': hit['category'], 'matters': hit['matters'], 'summary': hit['summary'], 'latency_s': hit['latency_s'],
            'detector_category': evidence.get('detector_category'), 'model_category': evidence.get('model_category'),
            'person_seen': bool(evidence.get('person_detector', {}).get('seen')), 'wait_s': evidence.get('model_wait_s'),
            'category_correct': hit['category'] == truth_category, 'model_label_correct': evidence.get('model_category') == truth_category,
            'matters_correct': hit['matters'] == (truth_category in MATTERS)}


async def played(folder, model, store, work, lock=None):
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
    watch = PerchedWatch(name, source, store, work/name, model, clock=clock, cooldown_s=30, model_lock=lock)
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
        result['model'] = scored_answer(hit, truth['category'])
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
                self.backend = LlamaBackend(timeout=20); self.in_flight = 0; self.max_in_flight = 0
            async def image(self, jpeg, prompt, schema, timeout=12, max_tokens=120):
                self.in_flight += 1; self.max_in_flight = max(self.max_in_flight, self.in_flight)
                try:
                    return await self.backend.image(jpeg, prompt, schema, time.monotonic() + timeout, max_tokens=max_tokens)
                finally:
                    self.in_flight -= 1
        model = Model(); await model.backend.health()
    temp = tempfile.TemporaryDirectory(); folder = Path(temp.name)
    store = EventStore(folder/'watch.sqlite3'); lock = asyncio.Lock()
    results = []
    for category in ([] if args.only_sets else CATEGORIES):
        for seed in range(args.seeds):
            r = await staged(category, 100 + seed, model, folder/'events', store, lock)
            results.append(r)
            print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k != 'model'} | ({'model': r['model']['category'], 'ok': r['model']['category_correct']} if 'model' in r else {})), flush=True)
    sets = {}
    for directory in args.set:
        folders = sorted(p for p in Path(directory).iterdir() if (p/'truth.json').is_file())
        gate_keeper = asyncio.Semaphore(max(1, args.parallel))   # N watches at once, one shared model
        async def one(f):
            async with gate_keeper:
                return await played(f, model, store, folder/'played', lock)
        rows = list(await asyncio.gather(*[one(f) for f in folders]))
        for r in rows:
            print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k != 'model'} | ({'model': r['model']['category'], 'ok': r['model']['category_correct']} if 'model' in r else {})), flush=True)
        scored = [r for r in rows if 'skipped' not in r]
        with_model = [r for r in scored if 'model' in r]
        asked = [r['model']['latency_s'] for r in with_model if r['model']['latency_s'] is not None]
        waited = [r['model']['wait_s'] for r in with_model if r['model'].get('wait_s') is not None]
        sets[str(directory)] = {'scenarios': len(rows), 'skipped': len(rows) - len(scored), 'detected': sum(r['detected'] for r in scored), 'passed': sum(r['passed'] for r in scored),
                                'category_accuracy': (sum(r['model']['category_correct'] for r in with_model)/max(1, len(with_model))) if model else None,
                                'model_label_accuracy': (sum(r['model']['model_label_correct'] for r in with_model)/max(1, len(with_model))) if model else None,
                                'matters_accuracy': (sum(r['model']['matters_correct'] for r in with_model)/max(1, len(with_model))) if model else None,
                                'per_category': {c: {'correct': sum(r['model']['category_correct'] for r in with_model if r['category'] == c),
                                                     'of': sum(1 for r in with_model if r['category'] == c)} for c in sorted({r['category'] for r in with_model})},
                                'max_event_latency_s': max((r['latency_s'] for r in scored if r['latency_s'] is not None), default=None),
                                'mean_model_latency_s': (sum(asked)/len(asked)) if asked else None, 'max_model_latency_s': max(asked, default=None),
                                'max_model_wait_s': max(waited, default=None), 'model_failures': sum(1 for r in with_model if r['model']['model_category'] is None and r['kind'] != 'lighting' and not r['model'].get('person_seen')),
                                'results': rows}
    if args.only_sets:
        report = {'date': time.strftime('%Y-%m-%d'), 'gate': GATE, 'parallel': args.parallel, 'sets': sets, 'wall_time_s': time.time() - started,
                  'max_concurrent_model_calls': model.max_in_flight if model is not None else None,
                  'accepted': all(v['passed'] == v['scenarios'] - v['skipped'] and (model is None or v['category_accuracy'] >= GATE['category_accuracy']) for v in sets.values()),
                  'scope': 'Sets only, played N scenarios at a time as N perched watches sharing one local model; no synthetic events and no quiet nights in this run.'}
        Path(args.output).write_text(json.dumps(report, indent=1, default=float) + '\n')
        print(json.dumps({'accepted': report['accepted'], 'parallel': args.parallel, 'max_concurrent_model_calls': report['max_concurrent_model_calls'],
                          'sets': {k: {kk: v[kk] for kk in ('scenarios', 'detected', 'passed', 'category_accuracy', 'matters_accuracy', 'max_event_latency_s', 'mean_model_latency_s', 'max_model_latency_s', 'max_model_wait_s', 'model_failures')} for k, v in sets.items()}}, default=float), flush=True)
        temp.cleanup()
        return 0 if report['accepted'] else 1
    nights = [night(500 + i, args.hours) for i in range(args.nights)]
    for n in nights:
        print(json.dumps(n), flush=True)
    detected = sum(r['detected'] for r in results); passed = sum(r['passed'] for r in results)
    report = {'date': time.strftime('%Y-%m-%d'), 'gate': GATE, 'staged_events': len(results), 'detected': detected, 'passed': passed,
              'detection_rate': detected/len(results), 'max_latency_s': max((r['latency_s'] or 0) for r in results),
              'nights': nights, 'false_alerts_total': sum(n['alerts'] for n in nights), 'night_hours': args.hours,
              'accepted': passed == len(results) and detected/len(results) >= GATE['detection'] and all(n['passed'] for n in nights)
                          and all(v['passed'] == v['scenarios'] - v['skipped'] for v in sets.values())
                          and (model is None or all(v['category_accuracy'] >= GATE['category_accuracy'] for v in sets.values())),
              'per_category': {c: {'detected': sum(r['detected'] for r in results if r['category'] == c), 'of': sum(1 for r in results if r['category'] == c),
                                   'median_latency_s': sorted((99. if r['latency_s'] is None else r['latency_s']) for r in results if r['category'] == c)[sum(1 for r in results if r['category'] == c)//2]}
                               for c in sorted({r['category'] for r in results})},
              'results': results, 'sets': sets, 'wall_time_s': time.time() - started, 'frame_rate_hz': RATE,
              'scope': 'Synthetic staged events drawn on a real photo with sensor noise and lamp flicker, plus rendered or recorded sets; the detector gate is deterministic. With the model, the event category is gated at 90 % on every set.'}
    if model is not None:
        scored = [r['model'] for r in results if 'model' in r]
        report['model'] = {'name': 'local Qwen 2B', 'events_scored': len(scored),
                           'category_accuracy': sum(m['category_correct'] for m in scored)/max(1, len(scored)),
                           'model_label_accuracy': sum(m['model_label_correct'] for m in scored)/max(1, len(scored)),
                           'matters_accuracy': sum(m['matters_correct'] for m in scored)/max(1, len(scored)),
                           'mean_latency_s': sum(m['latency_s'] or 0 for m in scored)/max(1, len(scored)),
                           'per_category': {c: {'correct': sum(r['model']['category_correct'] for r in results if r['category'] == c and 'model' in r),
                                                'answers': [r['model']['category'] for r in results if r['category'] == c and 'model' in r],
                                                'model_labels': [r['model']['model_category'] for r in results if r['category'] == c and 'model' in r],
                                                'person_detector_sightings': sum(1 for r in results if r['category'] == c and r.get('person_seen'))}
                                            for c in sorted({r['category'] for r in results})}}
        report['accepted'] = report['accepted'] and report['model']['category_accuracy'] >= GATE['category_accuracy']
    Path(args.output).write_text(json.dumps(report, indent=1, default=float) + '\n')
    print(json.dumps({k: report[k] for k in ('accepted', 'detection_rate', 'passed', 'staged_events', 'false_alerts_total', 'max_latency_s')}
                     | ({'category_accuracy': report['model']['category_accuracy'], 'model_label_accuracy': report['model']['model_label_accuracy']} if 'model' in report else {})
                     | {'sets': {k: {kk: v[kk] for kk in ('scenarios', 'detected', 'passed', 'category_accuracy', 'model_label_accuracy', 'matters_accuracy')} for k, v in sets.items()}}, default=float), flush=True)
    temp.cleanup()
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, default=12)
    parser.add_argument('--nights', type=int, default=2)
    parser.add_argument('--hours', type=float, default=8.)
    parser.add_argument('--model', action='store_true')
    parser.add_argument('--set', action='append', default=[], help='folder of rendered or recorded scenarios, each with frames and truth.json; repeatable')
    parser.add_argument('--parallel', type=int, default=1, help='play this many set scenarios at once, as that many watches sharing the model')
    parser.add_argument('--only-sets', action='store_true', help='skip the synthetic events and the quiet nights; report the sets alone')
    parser.add_argument('--output', default=str(ROOT/'docs/watch-validation.json'))
    sys.exit(asyncio.run(main(parser.parse_args())))
