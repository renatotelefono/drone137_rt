"""Bounded visual object search. Ground truth is deliberately absent from this module."""
import json
import math

TARGET = 'red fire extinguisher with a black hose and operating handle'
VERSION = 'object-localization-v1'
VISION_SCHEMA = {'type': 'object', 'properties': {
    'status': {'type': 'string', 'enum': ['present', 'absent', 'uncertain']},
    'evidence': {'type': 'string', 'maxLength': 180},
    'bbox': {'type': ['array', 'null'], 'items': {'type': 'number'}, 'minItems': 4, 'maxItems': 4},
}, 'required': ['status', 'evidence', 'bbox'], 'additionalProperties': False}
VISION_PROMPT = (
    'Find the red fire extinguisher with a black hose and operating handle in this camera image. '
    'A red toolbox, cabinet, bottle, drum or traffic cone is not the target. '
    'Use present only when the object identity is visually supported, absent if not visible, '
    'or uncertain if it cannot be judged. For present give its tight bounding box [left,top,right,bottom] '
    'in coordinates normalized from 0 to 1000. Otherwise bbox must be null. '
    'Describe only visible evidence in under 25 words. Return JSON with status, evidence and bbox.')
ACTIONS = {
    'scan': 'Target not clearly identified here. Search another area.',
    'confirm': 'Target appears visible. Verify it from a second viewpoint.',
    'found': 'Two viewpoints verified the target location. Report it.',
    'unresolved': 'Search exhausted without a verified target. Report incomplete.',
}
QUESTION = ('Choose the best next step for the evidence. A visible fire extinguisher needs a second '
            'viewpoint to verify its location. A toolbox, cabinet or other object is not the target. '
            'Search elsewhere when the target is not identified. Report a verified target when available.')


def parse_visual(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != set(VISION_SCHEMA['required']):
        raise ValueError('Invalid localization observation fields')
    if value['status'] not in ('present', 'absent', 'uncertain'):
        raise ValueError('Invalid target status')
    if not isinstance(value['evidence'], str) or len(value['evidence']) > 180:
        raise ValueError('Invalid target evidence')
    b = value['bbox']
    if value['status'] == 'present':
        if (not isinstance(b, list) or len(b) != 4
                or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1000 for x in b)
                or b[2]-b[0] < 4 or b[3]-b[1] < 4):
            raise ValueError('Invalid visible target box')
    elif b is not None:
        raise ValueError('An uncertain/absent target cannot have a location box')
    return value


def bearing(pose, bbox, vfov=41, aspect=16/9, pitch=-10):
    """Ideal calibrated camera ray, using predicted pixels and measured camera pose only."""
    u, v = (bbox[0]+bbox[2])/2000, (bbox[1]+bbox[3])/2000
    t = math.tan(math.radians(vfov)/2)
    xn, yn = (2*u-1)*t*aspect, (1-2*v)*t
    p = math.radians(pitch)
    angle = pose[3]+math.atan2(xn, math.cos(p)-yn*math.sin(p))
    return (math.cos(angle), math.sin(angle))


def triangulate(first, second, width=12, depth=10):
    """Reject duplicate poses, nearly parallel rays and backward/out-of-room intersections."""
    p, q = first['pose'][:2], second['pose'][:2]
    if first['view_id'] == second['view_id'] or math.dist(p, q) < .45:
        return None
    a, b = bearing(first['pose'], first['bbox']), bearing(second['pose'], second['bbox'])
    cross = lambda u, v: u[0]*v[1]-u[1]*v[0]
    det = cross(a, b)
    if abs(det) < math.sin(math.radians(5)):
        return None
    delta = [q[0]-p[0], q[1]-p[1]]
    ta, tb = cross(delta, b)/det, cross(delta, a)/det
    if not (.3 <= ta <= 8 and .3 <= tb <= 8):
        return None
    point = [p[i]+ta*a[i] for i in range(2)]
    if not (0 <= point[0] <= width and 0 <= point[1] <= depth):
        return None
    return {'xy_m': point, 'baseline_m': math.dist(p, q),
            'intersection_angle_degrees': math.degrees(math.asin(min(1, abs(det)))),
            'source_views': [first['view_id'], second['view_id']],
            'method': 'two model-predicted image boxes and ideal camera poses; no object depth or scene geometry'}


def decision_state(visual, remaining, confirmation_available, location):
    # Compact text is identical for both supervisors. Do not include scenario names or labels.
    return (f'Mission: locate a {TARGET}. '
            f'Current visual assessment: {visual["status"]}. Evidence: {visual["evidence"]} '
            f'Location verified from two distinct camera viewpoints: {"yes" if location else "no"}. '
            f'Another confirmation viewpoint available: {"yes" if confirmation_available else "no"}. '
            f'Unvisited search areas remaining: {remaining}.')


def available_actions(*, remaining, confirmation_available, location):
    # Eligibility is the same deterministic contract for both models; no evaluator truth.
    allowed = {}
    if location:
        allowed['found'] = ACTIONS['found']
    if confirmation_available:
        allowed['confirm'] = ACTIONS['confirm']
    if remaining:
        allowed['scan'] = ACTIONS['scan']
    if not remaining:
        allowed['unresolved'] = ACTIONS['unresolved']
    return allowed


def validate_action(action, *, remaining, confirmation_available, location):
    if action not in ACTIONS:
        return 'Unknown action'
    if action == 'found' and location is None:
        return 'No geometrically verified location'
    if action == 'confirm' and not confirmation_available:
        return 'Confirmation viewpoint unavailable'
    if action == 'scan' and remaining == 0:
        return 'No unvisited search area'
    return None
