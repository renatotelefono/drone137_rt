"""Mission wizard: propose the four mission clusters from place memory and
mission state, compose a reviewed brief from a chosen template, and launch the
one cluster that runs outside the console today, the exploration flight.

Proposals are suggestions only. Every launch still goes through the existing
reviewed plan or the existing exploration runner with its unchanged gates.
"""
import asyncio
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT/'config/mission-templates.json'
LAUNCH_PATHS = ('mission', 'explore', 'none')
FIELD_TYPES = ('text', 'integer', 'list', 'area', 'place', 'visit', 'dock', 'minutes')


def load_templates(path=TEMPLATES):
    data = json.loads(Path(path).read_text())
    clusters = data.get('clusters')
    if not isinstance(clusters, list) or not clusters:
        raise ValueError('Template catalogue has no clusters')
    seen = set()
    for c in clusters:
        for key in ('id', 'name', 'question', 'capability', 'starts_from', 'produces', 'gate', 'fields', 'launch'):
            if key not in c:
                raise ValueError(f'Template {c.get("id")} lacks {key}')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', c['id']) or c['id'] in seen:
            raise ValueError(f'Invalid or duplicate template id {c["id"]!r}')
        seen.add(c['id'])
        if not isinstance(c['gate'], dict) or not c['gate']:
            raise ValueError(f'Template {c["id"]} has no gate')
        if c['launch'].get('path') not in LAUNCH_PATHS or c['launch'].get('status') not in ('simulation', 'hardware', 'planned'):
            raise ValueError(f'Template {c["id"]} has an invalid launch definition')
        for f in c['fields']:
            if f.get('type') not in FIELD_TYPES or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', f.get('id', '')):
                raise ValueError(f'Template {c["id"]} field {f.get("id")!r} is invalid')
    return data


def template_ids(data):
    return [c['id'] for c in data['clusters']]


def validate_template(data, value):
    if value is None:
        return None
    if not isinstance(value, str) or value not in template_ids(data):
        raise ValueError('Unknown mission template')
    return value


def place_summary(memory):
    """Compact view of place memory: mapped places and their completed visits."""
    places = []
    with memory.connect() as db:
        rows = [dict(r) for r in db.execute('SELECT id,name,created FROM places ORDER BY created DESC')]
        for row in rows:
            visits = [dict(v) for v in db.execute(
                'SELECT v.id,v.started,v.state,(m.visit_id IS NOT NULL) AS has_map FROM visits v LEFT JOIN maps m ON m.visit_id=v.id '
                'WHERE v.place_id=? ORDER BY v.started DESC', (row['id'],))]
            completed = [v for v in visits if v['state'] in ('complete', 'partial') and v['has_map']]
            places.append({'id': row['id'], 'name': row['name'], 'visits': len(visits), 'mapped_visits': len(completed),
                           'latest_mapped_visit': completed[0]['id'] if completed else None,
                           'latest_state': visits[0]['state'] if visits else None})
    return places


def classify_brief(text):
    """Deterministic first guess at the cluster for a free-text brief.

    The model's intent step remains the authority for what is flown; this only
    chooses which template the console opens.
    """
    t = (text or '').casefold()
    if any(w in t for w in ('changed', 'since last', 'compare', 'difference', 'what is new')):
        return 'watch'
    if any(w in t for w in ('find', 'locate', 'where is', 'search for', 'look for')):
        return 'find' if any(w in t for w in ('unknown', 'unmapped', 'no map', 'first time', 'never seen')) else 'audit'
    if any(w in t for w in ('map the', 'map this', 'explore', 'survey the layout', 'unknown room', 'never seen')):
        return 'map'
    if any(w in t for w in ('check', 'verify', 'inspect', 'audit', 'inventory', 'present', 'missing')):
        return 'audit'
    return None


def suggest(data, places, *, model_ready, mission_busy, exploration_active, brief=None):
    """Order the clusters by what the current state makes sensible."""
    by_id = {c['id']: c for c in data['clusters']}
    mapped = [p for p in places if p['mapped_visits']]
    baseline = [p for p in mapped if p['mapped_visits'] >= 1]
    proposals = []

    def add(identity, reason, ready, prefill=None):
        c = by_id[identity]
        launch = c['launch']
        proposals.append({'id': identity, 'name': c['name'], 'question': c['question'], 'capability': c['capability'],
                          'status': launch['status'], 'launch_path': launch['path'], 'reason': reason,
                          'ready': bool(ready) and launch['path'] != 'none', 'note': launch['note'],
                          'gate': c['gate'], 'fields': c['fields'], 'prefill': prefill or {}})

    if not mapped:
        add('map', 'No saved map in place memory yet; map a space first.', not exploration_active and not mission_busy,
            {'place': 'workshop-first-visit', 'seed': 7301})
        add('audit', 'Audit runs on the operator floor plan of a test environment; it does not need a saved map.',
            model_ready and not mission_busy, {'targets': ['red fire extinguisher'], 'area': [0, 0, 12, 10]})
    else:
        latest = mapped[0]
        add('audit', f'{len(mapped)} mapped place(s) in memory, latest {latest["name"]}; the audit flies on the known floor plan.',
            model_ready and not mission_busy, {'targets': ['red fire extinguisher'], 'area': [0, 0, 12, 10]})
        add('map', 'Map a new layout; each mapped layout becomes a place in memory.', not exploration_active and not mission_busy,
            {'place': 'workshop-new-layout', 'seed': 7301})
    if baseline:
        p = baseline[0]
        add('watch', f'{p["name"]} has a completed mapped visit to use as the baseline.', False,
            {'place': p['id'], 'baseline': p['latest_mapped_visit']})
    else:
        add('watch', 'Needs a completed mapped visit as baseline; none yet.', False)
    add('find', 'Both capabilities in one flight; recorded as demand.', False)
    classified = classify_brief(brief) if brief else None
    if classified:
        proposals.sort(key=lambda p: 0 if p['id'] == classified else 1)
    return {'proposals': proposals, 'classified': classified, 'mapped_places': len(mapped),
            'model_ready': model_ready, 'mission_busy': mission_busy, 'exploration_active': exploration_active}


def compose(data, template, fields):
    """Turn a chosen template and its fields into what the planner accepts."""
    c = next((c for c in data['clusters'] if c['id'] == template), None)
    if c is None:
        raise ValueError('Unknown mission template')
    fields = fields if isinstance(fields, dict) else {}
    warnings = []
    if template == 'audit':
        targets = fields.get('targets')
        if isinstance(targets, str):
            targets = [t.strip() for t in re.split(r'[,\n;]', targets) if t.strip()]
        if not isinstance(targets, list) or not targets or any(not isinstance(t, str) or not 1 <= len(t.strip()) <= 80 for t in targets):
            raise ValueError('List at least one item to find, each under 80 characters')
        supported = [s.casefold() for s in next(f for f in c['fields'] if f['id'] == 'targets')['supported']]
        flyable = [t for t in targets if t.strip().casefold() in supported]
        others = [t for t in targets if t.strip().casefold() not in supported]
        if others:
            warnings.append('Not yet a qualified target, recorded as unsupported: '+', '.join(others))
        if not flyable:
            raise ValueError('None of the listed items is a qualified target yet; the qualified target is the red fire extinguisher')
        area = fields.get('area', [0, 0, 12, 10])
        instruction = f'Find the {flyable[0].strip()} in this workshop. Verify its location with images, then return and land.'
        return {'template': template, 'instruction': instruction, 'area': area, 'targets': targets,
                'flyable_targets': flyable, 'warnings': warnings, 'gate': c['gate'], 'launch': c['launch']}
    if template == 'map':
        place = fields.get('place')
        seed = fields.get('seed')
        if not isinstance(place, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', place):
            raise ValueError('Place name: lowercase letters, digits and dashes, up to 64 characters')
        if type(seed) is not int or not 0 <= seed <= 2**31-1:
            raise ValueError('Seed must be an integer')
        return {'template': template, 'place': place, 'seed': seed, 'name': f'Unknown workshop {seed}',
                'warnings': warnings, 'gate': c['gate'], 'launch': c['launch']}
    return {'template': template, 'fields': fields, 'warnings': warnings + [c['launch']['note']],
            'gate': c['gate'], 'launch': c['launch']}


class ExplorationLauncher:
    """Owns at most one simulated exploration flight started from the console."""
    def __init__(self, root=ROOT, output=None):
        self.root = Path(root)
        self.output = Path(output) if output else self.root/'.local/validation/blind-mapping'
        self.process = self.folder = self.log = None
        self.started = None
        self.command = None

    @property
    def active(self):
        return bool(self.process and self.process.returncode is None)

    def prerequisites(self):
        missing = [str(p) for p in (self.root/'.local/laya-env/bin/python', self.root/'scripts/run_blind_test.py') if not p.exists()]
        if missing:
            raise RuntimeError('Exploration runner prerequisites missing: '+', '.join(missing))
        if shutil.disk_usage(self.output.parent if self.output.exists() else self.root).free < 3*1024**3:
            raise RuntimeError('Need at least 3 GiB free before starting a recorded flight')

    async def start(self, place, seed, name):
        if self.active:
            raise RuntimeError('An exploration flight is already running')
        self.prerequisites()
        stamp = time.strftime('%Y%m%d-%H%M%S')
        self.folder = self.output/f'console-{stamp}-{seed}'
        if self.folder.exists():
            raise RuntimeError('Output folder already exists')
        self.output.mkdir(parents=True, exist_ok=True)
        self.log = self.output/f'console-{stamp}-{seed}.log'
        command = self.command or [sys.executable, '-m', 'scripts.run_blind_test', '--seed', str(seed),
                                   '--output', str(self.folder), '--place', place, '--name', name]
        with self.log.open('wb') as log:
            self.process = await asyncio.create_subprocess_exec(*command, cwd=self.root, stdout=log, stderr=log)
        self.started = time.time()
        return self.status()

    def status(self):
        if not self.process:
            return None
        result = {'active': self.active, 'folder': str(self.folder), 'log': str(self.log), 'started_at': self.started,
                  'exit_code': self.process.returncode, 'state': None, 'observations': None, 'elapsed_s': None, 'score': None}
        summary = self.folder/'explorer/summary.json'
        if summary.exists():
            try:
                s = json.loads(summary.read_text())
                result.update(state=s.get('state'), observations=len(s.get('steps') or []), elapsed_s=s.get('wall_time_s'))
            except Exception:
                pass
        score = self.folder/'score.json'
        if score.exists():
            try:
                d = json.loads(score.read_text())
                result['score'] = {'accepted': d.get('accepted'), 'metrics': d.get('metrics'),
                                   'failed_gates': [k for k, v in (d.get('gates') or {}).items() if not v]}
            except Exception:
                pass
        termination = self.folder/'termination.json'
        if termination.exists():
            try:
                result['error'] = json.loads(termination.read_text()).get('error')
            except Exception:
                pass
        try:
            lines = self.log.read_text().strip().splitlines() if self.log and self.log.exists() else []
            result['last_line'] = lines[-1][:300] if lines else ''
        except Exception:
            result['last_line'] = ''
        return result

    async def close(self):
        if self.active:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 20)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
