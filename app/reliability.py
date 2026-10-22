"""Offline evidence accounting. No flight controls or model-generated truth labels."""
import hashlib
import html
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT/'config/reliability.json'
PIPELINE_FILES = ('app/perception.py', 'adapters/llama.py', 'app/reliability.py',
                  'app/model_manager.py', 'config/models.json', 'config/lean-8gb.json',
                  'scripts/evaluate_reliability.py', 'config/reliability.json', 'requirements.lock')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f'Duplicate JSON key: {key}')
            value[key] = item
        return value
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def load_manifest(path):
    path = Path(path).resolve()
    manifest = read_json(path)
    domains = read_json(PROFILE)['domains']
    if manifest.get('version') != 1 or not manifest.get('dataset_id'):
        raise ValueError('Expected a version 1 dataset with dataset_id')
    cases = manifest.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10000:
        raise ValueError('Expected 1..10000 cases')
    ids, hashes, sites, encounters = set(), set(), {}, {}
    for c in cases:
        for field in ('id', 'site_id', 'encounter_id', 'camera_id', 'provenance'):
            if not isinstance(c.get(field), str) or not c[field].strip():
                raise ValueError(f'Missing {field}')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', c['id']):
            raise ValueError('Case IDs must be safe filename stems')
        if c['id'] in ids:
            raise ValueError('Duplicate case ID')
        ids.add(c['id'])
        if c.get('domain') not in {*domains, 'indoor_proxy'}:
            raise ValueError('Unknown domain; proxy data must be labelled indoor_proxy')
        if c.get('source_kind') not in ('synthetic', 'public_real', 'target_camera'):
            raise ValueError('Unknown source_kind')
        if c.get('split') not in ('development', 'held_out'):
            raise ValueError('Unknown split')
        if c.get('inspection_task', 'center') not in ('center', 'passage'):
            raise ValueError('Unknown inspection task')
        if c.get('perception_profile') not in ('lean', 'detail'):
            raise ValueError('Unknown perception profile')
        if not isinstance(c.get('conditions'), list) or not c['conditions'] or any(
                not isinstance(t, str) or not t for t in c['conditions']):
            raise ValueError('Conditions required')
        if c['site_id'] in sites and sites[c['site_id']] != c['split']:
            raise ValueError('Site appears in both development and held-out splits')
        sites[c['site_id']] = c['split']
        encounter = (c['site_id'], c['encounter_id'])
        identity = (c['domain'], c['source_kind'], c['camera_id'], tuple(c['conditions']))
        if encounter in encounters and encounters[encounter] != identity:
            raise ValueError('One encounter cannot change domain, camera, source or conditions')
        encounters[encounter] = identity
        image_path = (path.parent/c['path']).resolve()
        if not image_path.is_relative_to(path.parent):
            raise ValueError('Images must stay within the dataset directory')
        jpeg = image_path.read_bytes()
        if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9') or len(jpeg) > 200000:
            raise ValueError('Expected a complete JPEG within the 200 kB inference bound')
        actual = hashlib.sha256(jpeg).hexdigest()
        if c.get('image_sha256') != actual:
            raise ValueError('Image checksum mismatch')
        if actual in hashes:
            raise ValueError('Duplicate image; repeated frames cannot increase the denominator')
        hashes.add(actual)
        a = c.get('annotation', {})
        if not isinstance(a.get('reviewer'), str) or not a['reviewer']:
            raise ValueError('A named annotation reviewer is required')
        if a.get('reviewer_kind') not in ('human', 'agent'):
            raise ValueError('Annotation reviewer_kind must be human or agent')
        if a.get('center') not in (None, 'open_space', 'solid_surface', 'uncertain'):
            raise ValueError('Invalid reference center class')
        groups = a.get('required_objects')
        if not isinstance(groups, list) or any(not isinstance(g, list) or not g or
                any(not isinstance(t, str) or not t.strip() for t in g) for g in groups):
            raise ValueError('Object labels must be lists of accepted phrases')
        if a.get('center') is None and not groups:
            raise ValueError('Each case needs at least one label')
        if not isinstance(a.get('notes'), str) or not a['notes']:
            raise ValueError('Annotation notes required')
    return manifest


def fingerprint(manifest_path, model_path):
    manifest = load_manifest(manifest_path)
    return {'manifest_sha256': digest(manifest_path), 'model_sha256': digest(model_path),
            'pipeline': {p: digest(ROOT/p) for p in PIPELINE_FILES},
            'images': {c['id']: c['image_sha256'] for c in manifest['cases']}}


def normalized(text):
    return ' '.join(re.findall(r'[a-z0-9]+', text.lower()))


def score_case(case, output):
    a = case['annotation']
    survey = output.get('survey', {})
    description = ' '+normalized(' '.join([survey.get('summary', ''), *survey.get('objects', [])]))+' '
    objects = [any(' '+normalized(term)+' ' in description for term in group)
               for group in a['required_objects']]
    observed = output.get('perception', {}).get('center')
    expected = a['center']
    error = bool(output.get('error'))
    center_correct = None if expected is None else not error and observed == expected
    uncertain_action = (not error and output.get('action') in ('look_left', 'look_right', 'hold')) if expected == 'uncertain' else None
    return {'center_correct': center_correct,
            'false_clear': expected == 'solid_surface' and observed == 'open_space',
            'required_objects_found': sum(objects), 'required_objects_total': len(objects),
            'object_matches': objects, 'uncertainty_action_correct': uncertain_action,
            'passed': not error and center_correct is not False and all(objects) and uncertain_action is not False}


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values)*p)-1)] if values else None


def zero_failure_upper(failures, total):
    """Exact one-sided 95% binomial upper bound ONLY when zero failures were observed.

    Assumes independent representative encounters; adjacent frames are not trials.
    Nonzero failures already fail the zero-false-clear requirement; no bound claimed.
    """
    return 1-math.pow(.05, 1/total) if total and failures == 0 else None


def summarize(cases, results):
    by_id = {r['id']: r for r in results}
    groups = {}
    for c in cases:
        r = by_id.get(c['id'], {'id': c['id'], 'error': 'not evaluated'})
        s = score_case(c, r)
        groups.setdefault((c['site_id'], c['encounter_id']), []).append((c, r, s))
    def group_count(predicate):
        return sum(any(predicate(*row) for row in rows) for rows in groups.values())
    blocked = group_count(lambda c,r,s: c['annotation']['center'] == 'solid_surface')
    false_clear = group_count(lambda c,r,s: s['false_clear'])
    labeled = [score_case(c, by_id.get(c['id'], {'error':'missing'})) for c in cases]
    centers = [s['center_correct'] for s in labeled if s['center_correct'] is not None]
    uncertain = [s['uncertainty_action_correct'] for s in labeled if s['uncertainty_action_correct'] is not None]
    total_objects = sum(s['required_objects_total'] for s in labeled)
    group_centers = [all(s['center_correct'] for c,r,s in rows if s['center_correct'] is not None)
                     for rows in groups.values() if any(s['center_correct'] is not None for c,r,s in rows)]
    group_uncertain = [all(s['uncertainty_action_correct'] for c,r,s in rows if s['uncertainty_action_correct'] is not None)
                       for rows in groups.values() if any(s['uncertainty_action_correct'] is not None for c,r,s in rows)]
    group_objects = [sum(s['required_objects_found'] for c,r,s in rows)/sum(s['required_objects_total'] for c,r,s in rows)
                     for rows in groups.values() if sum(s['required_objects_total'] for c,r,s in rows)]
    return {'cases': len(cases), 'evaluated': sum(c['id'] in by_id for c in cases),
            'sites': len({c['site_id'] for c in cases}), 'encounters': len(groups),
            'case_checks_passed': sum(s['passed'] for s in labeled),
            'encounters_all_checks_passed': sum(all(s['passed'] for c,r,s in rows) for rows in groups.values()),
            'errors_or_missing': sum(bool(by_id.get(c['id'], {'error':'missing'}).get('error')) for c in cases),
            'center_labeled_cases': len(centers),
            'center_accuracy': sum(centers)/len(centers) if centers else None,
            'center_encounter_accuracy': sum(group_centers)/len(group_centers) if group_centers else None,
            'blocked_encounters': blocked, 'false_clear_encounters': false_clear,
            'false_clear_upper_95_if_independent': (zero_failure_upper(false_clear, blocked)
                if not any(c['annotation']['center'] == 'solid_surface' and
                           by_id.get(c['id'], {'error':'missing'}).get('error') for c in cases) else None),
            'clear_encounters': group_count(lambda c,r,s: c['annotation']['center'] == 'open_space'),
            'uncertain_encounters': group_count(lambda c,r,s: c['annotation']['center'] == 'uncertain'),
            'uncertainty_action_rate': sum(uncertain)/len(uncertain) if uncertain else None,
            'uncertainty_encounter_action_rate': sum(group_uncertain)/len(group_uncertain) if group_uncertain else None,
            'required_objects_found': sum(s['required_objects_found'] for s in labeled),
            'required_objects_total': total_objects,
            'required_object_recall': sum(s['required_objects_found'] for s in labeled)/total_objects if total_objects else None,
            'required_object_encounter_recall': sum(group_objects)/len(group_objects) if group_objects else None,
            'inspection_p95_s': percentile([r['latency_s'] for r in results if r['id'] in {c['id'] for c in cases} and 'latency_s' in r], .95),
            'condition_encounters': {tag: group_count(lambda c,r,s: tag in c['conditions'])
                                     for tag in sorted({t for c in cases for t in c['conditions']})},
            'caption_precision': None}


def domain_gates(manifest, results):
    profile = read_json(PROFILE)
    thresholds = profile['perception_gate']
    output = {}
    for domain, definition in profile['domains'].items():
        # Public benchmark photos and agent-labelled smoke tests cannot qualify a deployment domain.
        cases = [c for c in manifest['cases'] if c['domain'] == domain and c['source_kind'] == 'target_camera'
                 and c['split'] == 'held_out' and c['annotation']['reviewer_kind'] == 'human']
        stats = summarize(cases, results)
        reasons = []
        for metric in ('sites', 'encounters', 'blocked_encounters', 'clear_encounters', 'uncertain_encounters'):
            if stats[metric] < thresholds['min_'+metric]:
                reasons.append(f'{metric}: {stats[metric]} / {thresholds["min_"+metric]} required')
        for metric, threshold in (('center_encounter_accuracy','min_center_accuracy'),
                                  ('required_object_encounter_recall','min_required_object_recall'),
                                  ('uncertainty_encounter_action_rate','min_uncertainty_action_rate')):
            if stats[metric] is None or stats[metric] < thresholds[threshold]:
                reasons.append(f'{metric}: insufficient or below target')
        if stats['errors_or_missing']:
            reasons.append('Missing observations or inference errors')
        if stats['false_clear_encounters'] or stats['false_clear_upper_95_if_independent'] is None or stats['false_clear_upper_95_if_independent'] > thresholds['max_false_clear_upper_95']:
            reasons.append('False-clear evidence does not meet the proposed bound')
        if stats['inspection_p95_s'] is None or stats['inspection_p95_s'] > thresholds['max_inspection_p95_s']:
            reasons.append('Inspection latency not established or exceeds target')
        missing = [t for t in definition['conditions'] if stats['condition_encounters'].get(t, 0) < thresholds['min_encounters_per_condition']]
        if missing:
            reasons.append('Missing condition coverage: '+', '.join(missing))
        output[domain] = {'label': definition['label'], 'metrics': stats,
                          'perception_check_status': 'insufficient_or_failed' if reasons else 'numeric_targets_met_review_required',
                          'reasons': reasons,
                          'real_world_qualified': False,
                          'remaining_reviews': ['Independent full-caption factual audit', 'Sampling independence and site separation',
                                                'Camera-visible mission coverage and report usefulness', 'Repeated PX4 dynamics and recovery tests',
                                                'Supervised physical evidence with the intended aircraft and sensors', *definition['flight_gaps']]}
    return output


def render_html(report):
    esc = lambda v: html.escape(str(v), quote=True)
    stats = report['summary']
    metrics = [
        ('Images passing checks', f"{stats['case_checks_passed']} / {stats['cases']}"),
        ('Labelled object names found', f"{stats['required_objects_found']} / {stats['required_objects_total']}"),
        ('Inspection p95', f"{stats['inspection_p95_s']:.2f} s" if stats['inspection_p95_s'] is not None else 'Unmeasured'),
        ('Real-world qualification', 'Not established')]
    cards = ''.join(f'<div class="metric"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label,value in metrics)
    rows = []
    for c in report['cases']:
        r = next((r for r in report['results'] if r['id'] == c['id']), {'error':'not evaluated'})
        checks = score_case(c, r)
        survey = r.get('survey', {})
        expected = c['annotation']['required_objects']
        found = [g[0] for g,match in zip(expected,checks['object_matches']) if match]
        missed = [g[0] for g,match in zip(expected,checks['object_matches']) if not match]
        center = c['annotation']['center']
        status = 'Checks passed' if checks['passed'] else 'Review needed'
        description = survey.get('summary', r.get('error', 'No description returned'))
        objects = ', '.join(survey.get('objects', [])) or 'None returned'
        uncertainty = survey.get('uncertainty', '') or 'None stated by model'
        rows.append(f'<article><div class="case-title"><h3>{esc(c["id"].replace("_"," "))}</h3><b class="{("pass" if checks["passed"] else "miss")}">{status}</b></div>'
                    f'<div class="case-grid"><img src="images/{esc(c["id"])}.jpg" alt="Evaluated camera input"><div>'
                    f'<h4>Model description</h4><p>{esc(description)}</p><p><b>Objects listed:</b> {esc(objects)}</p>'
                    f'<p><b>Model uncertainty:</b> {esc(uncertainty)}</p><h4>Reference check</h4>'
                    f'<p><b>Found:</b> {esc(", ".join(found) or "None")}</p>'
                    f'<p class="{("miss" if missed else "")}"><b>Missed:</b> {esc(", ".join(missed) or "None among the labelled objects")}</p>'
                    f'<p><b>Center appearance:</b> {esc(center or "Unlabelled; not scored")}</p>'
                    f'<p class="muted">{esc(c["source_kind"].replace("_"," "))} · {esc(c["split"].replace("_"," "))} · reference reviewer: {esc(c["annotation"]["reviewer_kind"])}</p>'
                    '</div></div><details><summary>Reference, provenance and raw model output</summary>'
                    f'<pre>{esc(json.dumps({"input":c,"output":r},indent=2))}</pre></details></article>')
    domain_rows = ''.join(f'<tr><td>{esc(d["label"])}</td><td><b>Not qualified</b></td>'
                         f'<td>Target-camera data, independent review and mission/recovery evidence required.'
                         f'<details><summary>Evidence gaps</summary><ul>'+''.join(f'<li>{esc(reason)}</li>' for reason in d['reasons']+d['remaining_reviews'])+'</ul></details></td></tr>'
                         for d in report['domains'].values())
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Reliability evidence</title><style>body{font:16px/1.5 system-ui;max-width:1180px;margin:36px auto;padding:20px;background:#eef3f0;color:#17352d}'
            'h1{font-size:36px;margin-bottom:8px}h2{margin-top:36px}h3{margin:0}h4{margin:0 0 10px}p{margin:10px 0 18px}'
            '.notice{border-left:4px solid #b76924;padding:12px 18px;background:#fff6e8}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}'
            '.metric{padding:18px;background:white;border-radius:10px}.metric span{display:block;font-size:13px;color:#527065}.metric strong{display:block;font-size:26px}'
            'table{border-collapse:collapse;width:100%;background:white}td,th{padding:14px;border:1px solid #c8d7ce;text-align:left;vertical-align:top}'
            'article{background:white;padding:24px;margin:24px 0;border-radius:12px}.case-title{display:flex;justify-content:space-between;gap:20px;margin-bottom:18px}'
            '.case-grid{display:grid;grid-template-columns:1.1fr 1fr;gap:24px}.case-grid img{width:100%;height:auto;align-self:start;border-radius:6px}'
            '.pass{color:#287353}.miss{color:#a13b26}.muted{color:#587268;font-size:14px}summary{cursor:pointer;color:#355f4f;padding:8px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}'
            '@media(max-width:800px){.metrics{grid-template-columns:1fr 1fr}.case-grid{grid-template-columns:1fr}.case-title{display:block}body{padding:12px}}</style>'
            '<h1>Reliability evidence</h1><p class="notice"><strong>Real-world reliability is not established.</strong> '
            'Object-name checks do not measure full-caption accuracy or flight clearance.</p>'
            f'<p>{esc(report["scope"])}</p><div class="metrics">{cards}</div>'
            '<p>Failed checks are retained below. Repeated runs do not increase the sample size. '
            'Unlabelled measurements remain unmeasured.</p><h2>Images and observations</h2>'+''.join(rows)+
            '<h2>Deployment domains</h2><table><tr><th>Domain</th><th>Status</th><th>Next evidence</th></tr>'+domain_rows+'</table>'
            '<details><summary>All evaluation measurements</summary><pre>'+esc(json.dumps(stats,indent=2))+'</pre></details></html>')
