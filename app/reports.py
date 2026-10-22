"""Evidence-first run history and HTML reports; model text is always escaped."""
import html
import json
import math
import re


def evidence_image(root, episode, name):
    if not re.fullmatch('[a-f0-9]{32}', episode) or not re.fullmatch(r'[a-f0-9]{32}\.jpg', name):
        raise ValueError('Invalid evidence reference')
    path = root/episode/name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 200_000:
        raise ValueError('Evidence image unavailable')
    return path


def list_runs(root, limit=100):
    if not root.exists():
        return []
    paths = sorted(root.glob('*/summary.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = []
    for path in paths:
        if len(runs) >= limit:
            break
        if not re.fullmatch('[a-f0-9]{32}', path.parent.name) or path.is_symlink() or path.stat().st_size > 512_000:
            continue
        try:
            value = json.loads(path.read_text())
            if value.get('mode') != 'browser-kinematic-recon':
                continue
            runs.append({**value, 'episode': path.parent.name,
                         'report_page': f'/reports/{path.parent.name}/report.html'})
        except (OSError, ValueError):
            continue
    return runs


def render_report(episode, summary):
    esc = lambda value: html.escape(str(value), quote=True)
    observations = summary.get('observations', [])
    video = summary.get('video', {})
    extension = 'mp4' if video.get('mime') == 'video/mp4' else 'webm'
    media = (f'<video id="video" controls preload="metadata" src="onboard.{extension}"></video>'
             if video.get('chunks') else '<p>No video was received.</p>')
    cards = []
    for index, observation in enumerate(observations):
        name = observation.get('image', '')
        if not re.fullmatch(r'[a-f0-9]{32}\.jpg', name):
            continue
        seconds = observation.get('video_time_s')
        seek = ''
        if isinstance(seconds, (int, float)) and math.isfinite(seconds) and 0 <= seconds <= 200 and video.get('chunks'):
            seek = f'<button data-time="{seconds:.3f}">Play at {seconds:.1f}s</button>'
        comparison = observation.get('comparison') or {}
        visual = observation.get('perception') or {}
        center = {'solid_surface': 'solid surface', 'open_space': 'open space',
                  'uncertain': 'uncertain'}.get(visual.get('center'))
        classification = f'<p class="muted">Camera center: {center}.</p>' if center else ''
        if visual.get('inspection_task') == 'passage':
            doorway = {'solid_surface':'blocked', 'open_space':'opening visible', 'uncertain':'uncertain'}.get(visual.get('center'), 'uncertain')
            classification = f'<p class="muted">Doorway inspection: {doorway}. This is a visual assessment, not measured flight clearance.</p>'
        survey = observation.get('survey') or {}
        details = ''
        if survey:
            details = f'<p>{esc(survey.get("summary", ""))}</p><ul class="object-list">'
            details += ''.join(f'<li>{esc(item)}</li>' for item in survey.get('objects', []))+'</ul>'
            if survey.get('uncertainty'):
                details += f'<p class="muted">Uncertain: {esc(survey["uncertainty"])}</p>'
        change_text = {
            'new_obstruction': 'New obstruction in the camera center compared with the previous patrol.',
            'opening_visible': 'An opening is now visible where the previous patrol saw a solid surface.',
            'same_center_class': 'Center appearance has the same classification. Other changes are not assessed.',
            'uncertain': 'The change in the camera center is uncertain.',
        }.get((observation.get('change') or {}).get('status'))
        if visual.get('inspection_task') == 'passage' and change_text:
            change_text = change_text.replace('camera center', 'inspected doorway').replace('Center appearance', 'Doorway appearance')
        finding = f'<p class="finding">{change_text}</p>' if change_text else ''
        if observation.get('comparison_note'):
            finding += f'<p class="muted">{esc(observation["comparison_note"])}</p>'
        previous = ''
        if re.fullmatch('[a-f0-9]{32}', comparison.get('episode', '')) and re.fullmatch(r'[a-f0-9]{32}\.jpg', comparison.get('image', '')):
            previous = f'<a href="../{comparison["episode"]}/{comparison["image"]}">Previous patrol image</a>'
        cards.append(f'''<article><a href="{name}"><img src="{name}" alt="Observation {index+1}"></a>
          <div><h3>{index+1}. {esc(observation.get('view') or 'Exploration view')}</h3>
          {details or f'<p>{esc(observation.get("observation", ""))}</p>'}{classification}{finding}
          <p class="muted">Requested action: {esc(observation.get('action'))} ·
          Inference: {observation.get('latency_s', 0):.2f}s</p>{seek} {previous}</div></article>''')
    trail = ' '.join(f'{x*40:.1f},{y*40:.1f}' for x, y in summary.get('trail', [])[:2000])
    map_cells = []
    for i, cell in enumerate(summary.get('grid', [])[:480]):
        color = ['#344044', '#b6c3ba', '#c99a64'][cell] if cell in (0,1,2) else '#344044'
        map_cells.append(f'<rect x="{i%24*20}" y="{i//24*20}" width="19" height="19" fill="{color}"/>')
    unseen = ', '.join(summary.get('unreached', [])) or 'None listed'
    policy = 'Local Qwen vision' if summary.get('policy') == 'qwen' else 'Scripted run — no model perception'
    coverage = summary.get('observed_fraction', 0)*100
    camera = summary.get('camera') or {}
    optics_note = (f'Synthetic {esc(camera.get("condition", "nominal"))} camera stress; '
                   f'{esc(json.dumps(camera["effects"], sort_keys=True))}. Uncalibrated to hardware.'
                   if camera.get('effects') else 'Rendered ideal optics; physical camera fidelity is unmeasured.')
    camera_note = (f'<p class="muted">Camera: {esc(camera.get("width"))} × {esc(camera.get("height"))} video; '
                   f'{esc(camera.get("snapshot_width"))} × {esc(camera.get("snapshot_height"))} model snapshots. '
                   f'{optics_note}</p>') if camera else ''
    context = summary.get('task_context') or {}
    mission_note = (f'<p class="finding">{esc(context.get("drone_id"))} · {esc(context.get("instruction"))}</p>'
                    if context else '')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>drone137 · Patrol report</title>
    <link rel="stylesheet" href="/assets/recon.css"></head><body><main>
    <a href="/control">← Mission control</a> · <a href="/">Recon lab</a><p class="eyebrow">PATROL EVIDENCE</p>
    <h1>{esc(summary.get('scenario', 'room'))} · {esc(summary.get('state', 'unknown'))}</h1>
    {mission_note}<p>{esc(summary.get('reason', ''))}</p><p>{policy} · Seed {esc(summary.get('seed'))} ·
    {esc(summary.get('variant', 'baseline'))} · {summary.get('distance_m', 0):.1f} m travelled</p>{camera_note}
    <div class="layout"><section class="panel">{media}
    <p class="muted">Recording: {'finalized' if video.get('complete') else 'incomplete'}.
    Clip positions use browser elapsed time and are approximate.</p></section>
    <section class="panel"><h2>Observed map and route</h2><svg viewBox="0 0 480 400" role="img"
    aria-label="Observed range map and travelled route">{''.join(map_cells)}
    <polyline points="{trail}" fill="none" stroke="#1a5942" stroke-width="4"/></svg>
    <p>{coverage:.1f}% range map observed. Camera-visible coverage is unmeasured.</p>
    <p>Unreached inspection points: {esc(unseen)}.</p></section></div>
    <section class="panel"><h2>{len(observations)} recorded observations</h2>
    <p>Descriptions are model observations, not independently verified facts. Open each image to review the evidence.</p>
    {''.join(cards) or '<p>No observations were completed.</p>'}</section>
    <p><a href="summary.json">Download JSON report</a> · <a href="events.jsonl">Event log</a> ·
    <a href="world.json">Reproduce scene</a></p>
    <footer>Virtual kinematic simulation. Aircraft dynamics and physical operation remain unvalidated.</footer>
    </main><script src="/assets/report.js"></script></body></html>'''


def render_fleet_report(episode, summary):
    esc = lambda value: html.escape(str(value), quote=True)
    plan = summary.get('plan') or {}
    rows = []
    for job in summary.get('jobs', []):
        child = job.get('episode')
        link = (f'<a href="/reports/{child}/report.html">Video and observations →</a>'
                if isinstance(child, str) and re.fullmatch('[a-f0-9]{32}', child) else 'No flight evidence')
        rows.append(f'<div class="panel"><h2>{esc(job.get("drone_id"))} · {esc(job.get("state"))}</h2>'
                    f'<p>Assigned views: {esc(", ".join(job.get("points", [])))}</p>'
                    f'<p>{esc(job.get("reason", ""))}</p>{link}</div>')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>drone137 · Fleet report</title>
    <link rel="stylesheet" href="/assets/recon.css"></head><body><main>
    <a href="/control">← Mission control</a><p class="eyebrow">FLEET MISSION EVIDENCE</p>
    <h1>{esc(summary.get('state'))}</h1><p>{esc(plan.get('instruction'))}</p>
    <p>{esc(summary.get('reason'))}</p><p>Inspection rectangle: {esc(plan.get('area'))} metres.</p>
    {''.join(rows)}<p><a href="summary.json">Download mission JSON</a></p>
    <footer>Recorded state; this page is not live telemetry. Each aircraft has its own video and model observations.
    Sequential flights in a virtual kinematic site. Transit can leave the inspection rectangle.
    Physical operation and simultaneous multi-aircraft flight are not enabled.</footer></main></body></html>'''
