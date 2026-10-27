"""Shared airspace: every flight reports where it is in the place frame; separation and right of way are decided here.

Rules, in order:
1. A flight whose reports have stopped is lost: every other flight holds where it is until the reports return or the
   flight is declared landed. (The aircraft itself lands on its own command watchdog when its setpoints stop; this rule is
   the ground side.)
2. Two flights at similar heights keep MIN_SEPARATION_M apart, centre to centre, on the positions they report, plus
   ESTIMATE_MARGIN_M because a reported position is an estimate.
3. Right of way: the lower aircraft number proceeds; the other holds while the proceeding flight is within hold distance
   of the holding flight's next leg. Every flight plans its legs round the other flights as keep-out boxes, so the
   proceeding flight never has to pass through a holding one.
4. A flight with a corridor is only sent to goals inside it.
5. Give way: when the proceeding flight cannot plan past a holding aircraft (a doorway, a dead end), the holding one
   is told to back off from it by GIVE_WAY_M; the request lapses after GIVE_WAY_S unless renewed.
Nothing here commands an aircraft; a flight asks for advice before each leg and while flying it, holds on 'hold' and
backs off on 'give_way'.
"""
import copy
import math
import re

MIN_SEPARATION_M = 1.5
ESTIMATE_MARGIN_M = .3
VERTICAL_BAND_M = .8
HOLD_DISTANCE_M = 2.5
LINK_TIMEOUT_S = 1.0
PLAN_MARGIN_M = .58     # the route planner's own clearance from a box edge (app.mission_navigation.flight_path)
GIVE_WAY_M = 1.5
GIVE_WAY_S = 5.
EVENTS_KEPT = 200


def number(aircraft):
    """Right of way order: the lower number first; names without a number rank after every numbered one, alphabetically."""
    m = re.search(r'(\d+)', aircraft)
    return (0, int(m.group(1)), aircraft) if m else (1, 0, aircraft)


def horizontal(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def segment_distance(p, a, b):
    """Horizontal distance from point p to the segment a-b."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay; l2 = dx*dx + dy*dy
    t = 0. if l2 == 0 else max(0., min(1., ((p[0] - ax)*dx + (p[1] - ay)*dy)/l2))
    return math.hypot(p[0] - (ax + t*dx), p[1] - (ay + t*dy))


class Airspace:
    def __init__(self, *, min_separation_m=MIN_SEPARATION_M, estimate_margin_m=ESTIMATE_MARGIN_M, vertical_band_m=VERTICAL_BAND_M,
                 hold_distance_m=HOLD_DISTANCE_M, link_timeout_s=LINK_TIMEOUT_S):
        self.min_separation, self.estimate_margin, self.vertical_band = float(min_separation_m), float(estimate_margin_m), float(vertical_band_m)
        self.hold_distance, self.link_timeout = float(hold_distance_m), float(link_timeout_s)
        self.flights = {}
        self.events = []

    # --- what flights tell the airspace
    def flight(self, aircraft):
        return self.flights.setdefault(aircraft, {'position': None, 'yaw': 0., 'reported': None, 'state': 'assigned', 'corridor': None,
                                                  'holding': None, 'give_way': None})

    def assign(self, aircraft, corridor=None):
        """A corridor {x0, y0, x1, y1} in the place frame, or None for the whole place."""
        if corridor is not None and not (corridor['x0'] < corridor['x1'] and corridor['y0'] < corridor['y1']):
            raise ValueError('Corridor needs x0 < x1 and y0 < y1')
        self.flight(aircraft)['corridor'] = copy.deepcopy(corridor)

    def report(self, aircraft, position, yaw, t, state='flying'):
        f = self.flight(aircraft)
        f['position'] = [float(v) for v in position[:3]]; f['yaw'] = float(yaw); f['reported'] = float(t); f['state'] = state

    def landed(self, aircraft, t):
        f = self.flight(aircraft); f['state'] = 'landed'; f['holding'] = None
        self.note(t, aircraft, 'landed')

    def note(self, t, aircraft, text):
        self.events.append({'t': float(t), 'aircraft': aircraft, 'text': text})
        del self.events[:-EVENTS_KEPT]

    # --- what the airspace knows
    def active(self):
        return {k: f for k, f in self.flights.items() if f['state'] == 'flying' and f['position'] is not None}

    def lost(self, now):
        return sorted(k for k, f in self.active().items() if now - f['reported'] > self.link_timeout)

    def inside(self, aircraft, point):
        c = self.flight(aircraft)['corridor']
        return c is None or (c['x0'] <= point[0] <= c['x1'] and c['y0'] <= point[1] <= c['y1'])

    def conflicts_vertically(self, a, b):
        return abs(a[2] - b[2]) <= self.vertical_band

    def separation(self, aircraft):
        """Reported horizontal distance to the nearest other flying aircraft at a similar height, or None when alone."""
        me = self.flight(aircraft)['position']
        if me is None:
            return None
        others = [horizontal(me, g['position']) for k, g in self.active().items() if k != aircraft and self.conflicts_vertically(me, g['position'])]
        return min(others) if others else None

    # --- what a flight may do
    def blocked(self, aircraft, by, now):
        """The proceeding flight cannot plan past `by`: ask it to back off from the blocked flight's position."""
        me = self.flight(aircraft)['position']
        if me is None or number(by) < number(aircraft):
            return
        holder = self.flight(by)
        if holder['give_way'] is None or holder['give_way']['for'] != aircraft:
            holder['give_way'] = {'from': list(me), 'for': aircraft, 't': float(now), 'at': list(holder['position'] or me)}
        else:
            holder['give_way'].update(**{'from': list(me), 't': float(now)})
        self.note(now, by, f'asked to give way to {aircraft}')

    def advice(self, aircraft, goal, now):
        """{'action': 'proceed' | 'hold' | 'give_way' | 'refuse', 'reason', 'other', 'away_from'} for the leg from the reported position to goal."""
        f = self.flight(aircraft); me = f['position']
        if goal is not None and not self.inside(aircraft, goal):
            return self.decide(f, now, 'refuse', 'goal outside the corridor', None)
        lost = [k for k in self.lost(now) if k != aircraft]
        if lost:
            return self.decide(f, now, 'hold', f'link lost on {lost[0]}', lost[0])
        if me is None:
            return self.decide(f, now, 'proceed', 'no position yet', None)
        gw = f['give_way']
        if gw is not None:
            if now - gw['t'] > GIVE_WAY_S or gw['for'] not in self.active() or horizontal(me, gw['at']) >= GIVE_WAY_M - .1:
                f['give_way'] = None   # lapsed, the asker is gone, or we have backed off the asked distance
            else:
                return {**self.decide(f, now, 'give_way', f'giving way to {gw["for"]}', gw['for']), 'away_from': gw['from']}
        for other, g in sorted(self.active().items(), key=lambda kv: number(kv[0])):
            if other == aircraft or not self.conflicts_vertically(me, g['position']):
                continue
            has_right_of_way = number(other) < number(aircraft)
            if horizontal(me, g['position']) < self.min_separation + self.estimate_margin:
                if has_right_of_way:
                    return self.decide(f, now, 'hold', f'{other} has right of way and is within separation', other)
                continue   # the other one holds for us
            if has_right_of_way and goal is not None and segment_distance(g['position'], me, goal) < self.hold_distance:
                return self.decide(f, now, 'hold', f'{other} has right of way across this leg', other)
        return self.decide(f, now, 'proceed', 'clear', None)

    def decide(self, f, now, action, reason, other):
        holding = reason if action in ('hold', 'give_way') else None
        if holding != f['holding']:
            self.note(now, next(k for k, v in self.flights.items() if v is f), 'holding: ' + reason if holding else 'proceeding')
        f['holding'] = holding
        return {'action': action, 'reason': reason, 'other': other}

    def keep_out(self, aircraft):
        """The other flying aircraft as boxes the route planner keeps its margin from: separation plus the estimate margin."""
        me = self.flight(aircraft)['position']
        side = 2*max(.1, self.min_separation + self.estimate_margin - PLAN_MARGIN_M)
        return [{'x': g['position'][0], 'y': g['position'][1], 'sx': side, 'sy': side, 'height': 3., 'bottom': 0., 'keep_out_for': k}
                for k, g in self.active().items() if k != aircraft and (me is None or self.conflicts_vertically(me, g['position']))]

    def map_for(self, aircraft, scene_map):
        """The operator map with the other aircraft added as obstacles, for planning this aircraft's next leg."""
        out = copy.deepcopy(scene_map)
        out['obstacles'] = list(out.get('obstacles', [])) + self.keep_out(aircraft)
        return out

    def status(self, now):
        flights = []
        for k, f in sorted(self.flights.items(), key=lambda kv: number(kv[0])):
            flights.append({'aircraft': k, 'state': f['state'], 'position': f['position'], 'yaw': f['yaw'], 'corridor': f['corridor'],
                            'holding': f['holding'], 'separation_m': self.separation(k),
                            'reported_age_s': None if f['reported'] is None else round(now - f['reported'], 3),
                            'lost': k in self.lost(now)})
        return {'rules': {'min_separation_m': self.min_separation, 'estimate_margin_m': self.estimate_margin, 'vertical_band_m': self.vertical_band,
                          'hold_distance_m': self.hold_distance, 'link_timeout_s': self.link_timeout, 'right_of_way': 'lower aircraft number'},
                'flights': flights, 'in_the_air': len(self.active()), 'events': self.events[-20:]}
