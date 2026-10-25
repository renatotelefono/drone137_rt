"""Spoken or typed requests to the console, turned into one of a fixed set of
service actions.

The model chooses an action and names an aircraft; the service resolves the
name against the registry, applies the same checks as the buttons, and runs the
action. Reads, connections and anything that stops motion run at once; anything
that starts motion is proposed and waits for a click; a mission launch is never
offered here, it always goes through the reviewed plan. The model sees no
credential, address or link.
"""
import asyncio
import json
import re

ACTIONS = ('connect', 'disconnect', 'show_camera', 'list_aircraft', 'status', 'start_model',
           'suggest_mission', 'compose_audit', 'start_exploration', 'stop_mission', 'return_home',
           'land_aircraft', 'cut_motors', 'unknown')
IMMEDIATE = {'connect', 'disconnect', 'show_camera', 'list_aircraft', 'status', 'start_model',
             'suggest_mission', 'compose_audit', 'stop_mission', 'return_home', 'land_aircraft', 'cut_motors'}
CONFIRM = {'start_exploration'}
NEEDS_AIRCRAFT = {'connect', 'disconnect', 'show_camera', 'land_aircraft', 'cut_motors'}
SCHEMA = {'type': 'object', 'properties': {
    'action': {'type': 'string', 'enum': list(ACTIONS)},
    'aircraft': {'type': 'string', 'maxLength': 80},
    'targets': {'type': 'string', 'maxLength': 200},
    'place': {'type': 'string', 'maxLength': 64},
    'seed': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647},
    'reply': {'type': 'string', 'maxLength': 160}},
    'required': ['action', 'aircraft', 'targets', 'place', 'seed', 'reply'], 'additionalProperties': False}
PROMPT = (
    'You are the request interpreter for a local drone console. Map the operator request to exactly one action:\n'
    '- connect / disconnect: open or close the sensor connection to a paired aircraft (no flight).\n'
    '- show_camera: show a connected aircraft camera.\n'
    '- list_aircraft: which aircraft are paired and what type they are.\n'
    '- status: what the console and the current mission are doing.\n'
    '- start_model: start the local vision model.\n'
    '- suggest_mission: which mission types are possible now.\n'
    '- compose_audit: write a brief to find listed items on the known floor plan; put the items in targets.\n'
    '- start_exploration: map an unknown layout in the simulator; put a place name in place and a seed in seed.\n'
    '- stop_mission / return_home: stop the active mission or bring the aircraft home.\n'
    '- land_aircraft / cut_motors: emergency reduce thrust / cut motors on a connected aircraft.\n'
    '- unknown: anything else, or when the aircraft or intent is unclear; say in reply what you need.\n'
    'Copy the aircraft name as the operator said it into aircraft, or leave it empty. Never invent names or '
    'capabilities. Launching a mission is not an action here. Keep reply under 25 words.\n'
    'Paired aircraft: {aircraft}\nOperator request: ')


def parse(raw):
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != set(SCHEMA['required']) or value['action'] not in ACTIONS
            or any(not isinstance(value[k], str) for k in ('aircraft', 'targets', 'place', 'reply'))
            or type(value['seed']) is not int):
        raise ValueError('Model returned an invalid request interpretation')
    return value


def tokens(text):
    return set(re.findall(r'[a-z0-9]+', (text or '').casefold()))


def resolve_aircraft(name, aircraft):
    """One registry record for a spoken name, or None with a reason."""
    if not aircraft:
        return None, 'No aircraft is paired on this computer'
    if not name.strip():
        if len(aircraft) == 1:
            return aircraft[0], None
        return None, 'Which aircraft? Paired: ' + ', '.join(a['name'] for a in aircraft)
    wanted = tokens(name)
    exact = [a for a in aircraft if a['name'].casefold() == name.strip().casefold()]
    if len(exact) == 1:
        return exact[0], None
    scored = sorted(((len(wanted & tokens(a['name'])), a) for a in aircraft), key=lambda s: -s[0])
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1], None
    return None, f'No single paired aircraft matches "{name.strip()}". Paired: ' + ', '.join(a['name'] for a in aircraft)


class Assistant:
    def __init__(self, model, runtime, aircraft, launcher, templates):
        self.model, self.runtime, self.launcher, self.templates = model, runtime, launcher, templates
        self.store, self.connections = aircraft
        self.lock = asyncio.Lock()

    def registry(self):
        rows = []
        for r in self.store.list():
            live = self.connections.get(r['id'])
            rows.append({'id': r['id'], 'name': r['name'], 'kind': r.get('kind'), 'assembly': r.get('assembly'),
                         'connection': live.state if live else 'disconnected'})
        return rows

    async def interpret(self, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 300:
            raise ValueError('Say or type a request of 1–300 characters')
        aircraft = self.registry()
        listed = ', '.join(f"{a['name']} ({a['kind'] or 'aircraft'}, {a['connection']})" for a in aircraft) or 'none'
        intent = parse(await self.model.text(PROMPT.format(aircraft=listed) + json.dumps(text.strip()), SCHEMA))
        result = {'request': text.strip(), 'action': intent['action'], 'reply': intent['reply'], 'aircraft': None,
                  'executed': False, 'needs_confirmation': False, 'result': None}
        if intent['action'] in NEEDS_AIRCRAFT:
            record, why = resolve_aircraft(intent['aircraft'], aircraft)
            if record is None:
                result.update(action='unknown', reply=why)
                return result
            result['aircraft'] = {'id': record['id'], 'name': record['name'], 'kind': record['kind']}
        if intent['action'] == 'start_exploration':
            from app import mission_wizard
            fields = {'place': intent['place'] or 'console-asked-layout', 'seed': intent['seed'] or 7301}
            try:
                plan = mission_wizard.compose(self.templates, 'map', fields)
            except ValueError as exc:
                result.update(action='unknown', reply=str(exc))
                return result
            result.update(needs_confirmation=True, proposal={'place': plan['place'], 'seed': plan['seed'], 'name': plan['name']},
                          reply=f"Ready to map layout {plan['seed']} as {plan['place']} in the simulator. Confirm to start.")
            return result
        if intent['action'] == 'compose_audit':
            from app import mission_wizard
            try:
                out = mission_wizard.compose(self.templates, 'audit', {'targets': intent['targets'] or 'red fire extinguisher'})
            except ValueError as exc:
                result.update(action='unknown', reply=str(exc))
                return result
            result.update(executed=True, result={'instruction': out['instruction'], 'warnings': out['warnings'], 'template': 'audit'},
                          reply='Brief written: ' + out['instruction'] + (' ' + ' '.join(out['warnings']) if out['warnings'] else '') + ' Generate the plan and review it before launch.')
            return result
        return result

    async def execute(self, interpretation):
        """Run an immediate action; the caller has already resolved the aircraft."""
        action = interpretation['action']
        aircraft = interpretation.get('aircraft')
        if action == 'list_aircraft':
            rows = self.registry()
            reply = 'No aircraft paired.' if not rows else '; '.join(
                f"{a['name']}: {'protocol emulator' if a['kind'] == 'protocol-emulator' else 'physical aircraft'}, assembly {a['assembly']}, {a['connection']}" for a in rows)
            return {'aircraft': rows}, reply
        if action == 'status':
            s = self.runtime.snapshot()
            run = s.get('mission') or {}
            model = s.get('model') or {}
            reply = (f"Model {model.get('state', 'unknown')}. " + (f"Mission {run.get('state')}: {run.get('plan', {}).get('instruction', '')[:80]}" if run else 'No mission running.')
                     + (' Exploration flight running.' if self.launcher.active else ''))
            return {'busy': s.get('busy'), 'model': model, 'mission_state': run.get('state'), 'exploration': self.launcher.status()}, reply
        if action == 'start_model':
            if hasattr(self.model, 'start'):
                await self.model.start()
                return {'started': True}, 'Starting the local model.'
            return {'started': False}, 'The model runs as an external service here; it is ' + str((self.model.status() or {}).get('state'))
        if action == 'suggest_mission':
            from app import mission_wizard
            from app.place_memory import PlaceMemory
            places = mission_wizard.place_summary(self.places) if getattr(self, 'places', None) else []
            s = mission_wizard.suggest(self.templates, places, model_ready=bool((self.model.status() or {}).get('ready')),
                                       mission_busy=bool(self.runtime.busy), exploration_active=self.launcher.active)
            ready = [p['name'] for p in s['proposals'] if p['ready']]
            return s, ('Possible now: ' + ', '.join(ready) + '.' if ready else 'Nothing can launch right now; see the Start-here panel.')
        if action in ('stop_mission', 'return_home'):
            s = await self.runtime.stop(return_home=action == 'return_home')
            return {'mission_state': (s.get('mission') or {}).get('state')}, ('Returning home.' if action == 'return_home' else 'Stopping the mission.')
        if action in ('connect', 'disconnect', 'show_camera', 'land_aircraft', 'cut_motors'):
            from hardware.esp32.connection import AircraftConnection
            record = self.store.get(aircraft['id'], private=True)
            if action == 'show_camera':
                live = self.connections.get(aircraft['id'])
                if not live or live.state != 'connected':
                    raise RuntimeError(f"{aircraft['name']} is not connected; ask to connect it first")
                return {'camera': aircraft['id']}, f"Showing {aircraft['name']}'s camera."
            if action in ('land_aircraft', 'cut_motors'):
                connection = self.connections.get(aircraft['id']) or AircraftConnection(record)
                return await connection.stop('land' if action == 'land_aircraft' else 'disarm'), (
                    f"Sent {'reduce thrust' if action == 'land_aircraft' else 'cut motors'} to {aircraft['name']}.")
            if action == 'connect':
                connection = self.connections.setdefault(aircraft['id'], AircraftConnection(record))
                snapshot = await connection.connect()
                return snapshot, f"Connected to {aircraft['name']} ({'protocol emulator' if aircraft['kind'] == 'protocol-emulator' else 'physical aircraft'})."
            live = self.connections.get(aircraft['id'])
            if live:
                await live.close()
            return {'connection': 'disconnected'}, f"Disconnected {aircraft['name']}."
        raise ValueError('That action is not executed by the assistant')

    async def handle(self, text):
        async with self.lock:
            interpretation = await self.interpret(text)
            if interpretation['action'] in IMMEDIATE and not interpretation['needs_confirmation'] and not interpretation['executed']:
                try:
                    result, reply = await self.execute(interpretation)
                    interpretation.update(executed=True, result=result, reply=reply)
                except Exception as exc:
                    interpretation.update(executed=False, error=f'{exc}'[:200], reply=f'{exc}'[:160])
            return interpretation

    async def confirm(self, proposal):
        async with self.lock:
            if not isinstance(proposal, dict) or proposal.get('kind') != 'start_exploration':
                raise ValueError('Nothing to confirm')
            self.runtime.available()
            if self.runtime.busy:
                raise RuntimeError('Finish the active mission first')
            from app import mission_wizard
            plan = mission_wizard.compose(self.templates, 'map', {'place': proposal.get('place'), 'seed': proposal.get('seed')})
            return await self.launcher.start(plan['place'], plan['seed'], plan['name'])


def install(app, assistant):
    from aiohttp import web

    async def ask(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        return web.json_response(await assistant.handle(body.get('text')), headers={'Cache-Control': 'no-store'})

    async def confirm(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        return web.json_response(await assistant.confirm(body.get('proposal')), headers={'Cache-Control': 'no-store'})

    app.router.add_post('/api/assistant/ask', ask)
    app.router.add_post('/api/assistant/confirm', confirm)
    return assistant
