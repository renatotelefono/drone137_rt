"""Render full denominators, failures and evidence; never choose a best retry."""
import argparse
import html
import json
from pathlib import Path


def render(paths, mission_url="http://127.0.0.1:8137"):
    sections = []
    for path in paths:
        r = json.loads(path.read_text())
        summary = r.get('summary', {})
        rows = []
        for run in r['runs']:
            gates = run['gates']
            failed = ', '.join(k for k, v in gates.items() if not v)
            rows.append('<tr><td>'+html.escape(run['case'])+'</td><td>'+str(run['repeat']+1)+'</td><td class="'+('pass' if run['passed'] else 'fail')+'">'+('PASS' if run['passed'] else 'FAIL')+'</td><td>'+html.escape(run['outcome'])+'</td><td>'+('—' if run['error_m'] is None else f"{run['error_m']:.3f} m")+'</td><td>'+f"{run['wall_time_s']:.1f} s"+'</td><td>'+html.escape(failed or 'All mission gates passed')+'</td><td><a href="'+html.escape(mission_url.rstrip('/')+'/api/mission/runs/'+run['mission']+'/report.html', quote=True)+'">Images & video</a></td></tr>')
        planned = len(r['protocol']['cases'])
        for pending in r['protocol']['cases'][len(r['runs']):]:
            rows.append('<tr><td>'+html.escape(pending['case']['id'])+'</td><td>'+str(pending['repeat']+1)+'</td><td class=fail>NOT RUN</td><td colspan=5>Not executed; remains in the acceptance denominator</td></tr>')
        memory = r.get('memory', {})
        passed = sum(x['passed'] for x in r['runs'])
        peak = f"{memory['sampled_peak_guard_gib']:.2f} GiB peak application memory" if 'sampled_peak_guard_gib' in memory else 'Memory result unavailable'
        navigation = html.escape(r['protocol'].get('navigation', 'Earlier attempt: 2D footprint routing and clearance metric.'))
        sections.append('<section><h2>'+html.escape(path.parent.name)+f'</h2><p class="score">{passed}/{planned} planned missions passed · {passed/planned:.1%}</p><p>'+html.escape(r['protocol']['assembly'])+f" · Executed: {len(r['runs'])}/{planned}; failed during execution: {len(r['runs'])-passed}; not run: {planned-len(r['runs'])}"+'</p><p>'+str(summary.get('false_confirmations', sum(x['false_confirmation'] for x in r['runs'])))+' false confirmations · '+peak+'</p><p>'+navigation+'</p><p>Acceptance: '+('PASS' if summary.get('accepted') else 'NOT MET')+'</p><p>'+html.escape('; '.join(r.get('errors', [])))+'</p><div class=scroll><table><thead><tr><th>Environment</th><th>Run</th><th>Full mission</th><th>Finding</th><th>Position error</th><th>Duration</th><th>Gate details</th><th>Evidence</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>')
    return '<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Drone137 · Complete mission qualification</title><style>body{background:#101c22;color:#dfede8;font:16px system-ui;margin:35px auto;max-width:1400px;padding:20px}h1{font-size:36px}p{line-height:1.55;color:#acc4cb}.score{font-size:25px;color:#e5f1eb}section{border-top:1px solid #36515a;margin-top:35px;padding-top:15px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #30454f;text-align:left}.scroll{overflow:auto}.pass{color:#8ed8ad}.fail{color:#ffa18b}a{color:#9cd9ea}</style><small>DRONE137 / FULL MISSION EVIDENCE</small><h1>Flight. Recognition. Location. Return.</h1><p>Every case uses the mission API and a service-owned camera. Closing the dashboard does not own or stop flight. Success requires the correct visual result, localization within 0.75 m for present targets, full planned coverage for absent controls, landing, no collision/envelope violation, valid battery, controlled attitude, video and the 300-second deadline.</p><p>Existing difficult workshop layouts, lookalikes, occlusion, light and camera degradation are retained. Aircraft dynamics now come from the SQLite microquad and Rapier. Ideal external positioning and a known floor plan remain assumptions; these are synthetic development cases, not proof of real-world reliability. Peak memory is measured on a 16 GiB computer against a 5 GiB application budget; actual 8 GB hardware remains untested.</p>'+''.join(sections)+'</html>'


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('results', nargs='+', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mission-url', default='http://127.0.0.1:8137')
    a = p.parse_args()
    a.output.write_text(render(a.results, a.mission_url))
