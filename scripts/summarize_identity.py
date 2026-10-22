"""Review known-case improvement trials while retaining failed earlier attempts."""
import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import statistics

from scripts.evaluate_flight import report_html
from scripts.summarize_native import route_map


def summarize(inputs, output):
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    report = {'version': 'identity-review-v1', 'runs': [], 'memory': {}, 'attempts': [],
              'sources': [], 'summary': {},
              'scope': 'Known authored scenarios used during development. Independent flights, not a held-out qualification or controlled same-pixel mission comparison.'}
    latest = {}; source_memory = {}; full_batches = {}
    for source in inputs:
        source = source.resolve(); value = json.loads(source.read_text())
        if set(value['memory']) != {'qwen'} or any(r['arm'] != 'qwen' for r in value['runs']):
            raise ValueError('This review compares vision sizes with the Qwen supervisor only')
        model = value['model_size'].upper()
        relative = '../'+str(source.relative_to(output.parent))
        report['sources'].append({'path': relative, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                                  'errors': value['errors'], 'model': value.get('model')})
        for arm, memory in value['memory'].items():
            source_memory[relative] = {k: v for k, v in memory.items() if k != 'samples'}
        if len(value['runs']) == 4:
            full_batches[f'Qwen {model}'] = {'correct': sum(r['score']['correct'] for r in value['runs']),
                                            'cases': 4, 'source': relative}
        for item in value['runs']:
            run = copy.deepcopy(item); directory = source.parent/run['folder']
            run['folder'] = '../'+str(directory.relative_to(output.parent)); run['arm'] = f'Qwen {model}'
            run['source'] = relative
            run['route_svg'], _ = route_map(directory, run)
            report['attempts'].append({k: run[k] for k in ('case', 'arm', 'folder', 'outcome', 'landed', 'score', 'error', 'source')})
            latest[(model, run['case'])] = run
        interruption = source.parent/'interruption.json'
        if interruption.exists():
            report.setdefault('interruptions', []).append({'source': '../'+str(interruption.relative_to(output.parent)),
                                                            'record': json.loads(interruption.read_text())})
    report['runs'] = list(latest.values())
    report['full_batches'] = full_batches
    for run in report['runs']:
        memory = source_memory[run['source']]
        if memory['sampled_peak_rss_gib'] > report['memory'].get(run['arm'], {}).get('sampled_peak_rss_gib', 0):
            report['memory'][run['arm']] = memory
    for arm in report['memory']:
        runs = [r for r in report['runs'] if r['arm'] == arm]
        steps = [s for r in runs for s in r['steps']]
        report['summary'][arm] = {
            'correct': sum(r['score']['correct'] for r in runs), 'cases': len(runs),
            'false_claims': sum(r['score']['false_location_claim'] for r in runs),
            'landed': sum(r['landed'] for r in runs),
            'sampled_peak_rss_gib': report['memory'][arm]['sampled_peak_rss_gib'],
            'envelope_violations': sum(r['flight']['envelope_violations'] for r in runs),
            'mean_vision_s': statistics.mean(s['vision_latency_s'] for s in steps) if steps else None,
            'mean_crop_check_s': statistics.mean(s['identity']['latency_s'] for s in steps if s.get('identity')) if any(s.get('identity') for s in steps) else None,
            'wall_time_s': sum(r['wall_time_s'] for r in runs),
            'deterministic_actions': sum(s['decision'].get('source', '').startswith('deterministic') for s in steps),
            'total_actions': len(steps),
            'supported_parts_in_absent_scene': sum(s.get('identity', {}).get('supported', False) for r in runs if r['score']['truth_xy_m'] is None for s in r['steps'] if s.get('identity'))}
    page = report_html(report)
    page = page.replace('<h1>A denser world. Actual simulated flight.</h1>', '<h1>From candidates to supported locations</h1>')
    intro = '<section><h2>Complete batches and subsequent repeats</h2><p>Earlier 2B policy: 2/4 correct jobs and two false location claims. New policy: neutral crop checks, two supported viewpoints plus geometry, bounded detail views, and terminal completion. These four environments informed development; the results do not establish reliability in unfamiliar real rooms.</p>'
    intro += '<table><tr><th>Model</th><th>Complete four-case batch</th><th>Latest result per case</th><th>Latest false claims</th><th>Latest returned + landed</th><th>Peak summed RSS</th></tr>'
    for arm, summary in report['summary'].items():
        batch = full_batches.get(arm, {})
        intro += f'<tr><td>{arm}</td><td>{batch.get("correct", "—")}/{batch.get("cases", "—")}</td><td>{summary["correct"]}/{summary["cases"]}</td><td>{summary["false_claims"]}</td><td>{summary["landed"]}/{summary["cases"]}</td><td>{summary["sampled_peak_rss_gib"]:.2f} GiB</td></tr>'
    intro += '</table><p><b>Interpretation:</b> 2B completed 3/4 in its full batch. Its low-light repeat passed on the first two views, without using the new sightline planner. Latest-case 4/4 therefore does not mean 100% observed reliability or prove that planning change fixed the miss. Its no-target mission still contained two incorrectly supported crop observations; geometry prevented a location claim. Recognition remains inconsistent.</p><p>Summed RSS is conservative and may count shared pages more than once; macOS physical footprint can exclude mapped model memory. The guard uses the larger measure. Tested on a 16 GiB host; 8 GiB hardware remains unqualified. Only one vision model runs at a time. RAM is the maximum among source sessions contributing the latest-case cards.</p>'
    intro += '<p><a href="../identity-2b-v2/report.html">2B crop diagnostic</a> · <a href="../identity-4b-v3/report.html">4B crop diagnostic</a> · <a href="../dense-native-review/report.html">Earlier flight baseline</a></p></section>'
    page = page.replace('<table><tr><th>Case', intro+'<table><tr><th>Case', 1)
    for run in report['runs']:
        video = f'<video controls preload=metadata poster="{run["folder"]}/preview.png"'
        poster = run['steps'][-1]['image'] if run['steps'] else 'preview.png'
        page = page.replace(video, run['route_svg']+f'<video controls preload=metadata poster="{run["folder"]}/{poster}"')
        if (output/run['folder']/'onboard-indexed.webm').exists():
            page = page.replace(f'{run["folder"]}/onboard.webm', f'{run["folder"]}/onboard-indexed.webm')
    audit = '<section><h2>All attempts retained</h2><p>Main cards show the latest attempt per model and scenario. Earlier controller and video failures remain below. Recognition, flight completion and evidence recording all count toward a successful job. No inference outputs were repaired.</p><ul>'
    for attempt in report['attempts']:
        audit += f'<li><a href="{html.escape(attempt["folder"])}/result.json">{attempt["arm"]} · {attempt["case"]}</a>: {attempt["outcome"]}; correct={attempt["score"]["correct"]}; landed={attempt["landed"]}'+(' · '+html.escape(attempt['error']) if attempt['error'] else '')+'</li>'
    for item in report.get('interruptions', []):
        audit += f'<li><a href="{html.escape(item["source"])}">Interrupted development trial</a>: {html.escape(item["record"]["reason"])}</li>'
    audit += '</ul></section>'
    page = page.replace('</body>', audit+'</body>')
    (output/'results.json').write_text(json.dumps(report, indent=2))
    (output/'report.html').write_text(page)
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('inputs', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); summarize(args.inputs, args.output)
