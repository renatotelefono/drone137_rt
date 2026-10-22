"""Single-image evidence, followed by a separate bounded policy decision.

No scene geometry, expected label, or filename is supplied to either model call.
Center appearance is not a clearance measurement or permission to fly forward.
"""
import json
import math

VERSION = 'center-evidence-v2'
DETAIL_VERSION = 'center-objects-v1'
PASSAGE_VERSION = 'passage-evidence-v1'
CENTERS = ('solid_surface', 'open_space', 'uncertain')
SCHEMA = {'type': 'object', 'properties': {
    'visible_evidence': {'type': 'string', 'maxLength': 200},
    'center': {'type': 'string', 'enum': list(CENTERS)}},
    'required': ['visible_evidence', 'center'], 'additionalProperties': False}
PROMPT = ('Look only at the central third of the image, not objects beside it. First describe the visible evidence. '
          'Then classify the center as solid_surface if a panel, wall, door or object blocks it; '
          'open_space if you can see through an opening to the ground or background beyond; uncertain if unclear. '
          'Return JSON with visible_evidence and center. Keep the evidence under 15 words.')
# The 720p camera profile has narrower framing and more object detail. Keep its
# independently evaluated instruction separate from the lean/native profile.
DETAIL_PROMPT = ('First describe the object or opening at the exact center of the image. '
          'Classify solid_surface when a physical object occupies the center, including a stack of boxes or panel '
          'even if space is visible around it. Classify open_space when the center looks through an unobstructed '
          'opening. Classify uncertain when unclear. Return JSON with visible_evidence and center. Keep evidence short.')


def object_from_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate perception field')
            result[key] = value
        return result
    if not isinstance(raw, str) or len(raw.encode()) > 4096:
        raise ValueError('Invalid perception response')
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError('Expected a model JSON object')
    return value


def parse(raw, version=VERSION):
    value = object_from_json(raw)
    if (not isinstance(value, dict) or set(value) != {'visible_evidence', 'center'}
        or value['center'] not in CENTERS or not isinstance(value['visible_evidence'], str)
        or not 1 <= len(value['visible_evidence']) <= 200):
        raise ValueError('Invalid perception fields')
    return {**value, 'version': version}


PASSAGE_SCHEMA = {'type':'object', 'properties':{
    'visible_evidence':{'type':'string','maxLength':200},
    'blocked':{'type':['boolean','null']}},
    'required':['visible_evidence','blocked'], 'additionalProperties':False}
PASSAGE_PROMPT = ('Look through the central doorway. Is a large object blocking that doorway? '
                  'Ignore objects standing to either side. Describe the evidence in under 15 words '
                  'and answer blocked true or false. Use null if the image is unclear or no doorway '
                  'can be judged. Return JSON with visible_evidence and blocked.')


async def inspect(image_call, jpeg, detailed=False, task='center'):
    if task == 'passage':
        value = object_from_json(await image_call(jpeg, PASSAGE_PROMPT, PASSAGE_SCHEMA))
        if (set(value) != {'visible_evidence','blocked'} or
            not (value['blocked'] is None or type(value['blocked']) is bool)):
            raise ValueError('Invalid passage assessment')
        center = 'uncertain' if value['blocked'] is None else 'solid_surface' if value['blocked'] else 'open_space'
        return {**parse(json.dumps({'visible_evidence':value['visible_evidence'],'center':center}), PASSAGE_VERSION),
                'inspection_task':'passage'}
    if task != 'center':
        raise ValueError('Unknown inspection task')
    return parse(await image_call(jpeg, DETAIL_PROMPT if detailed else PROMPT, SCHEMA),
                 DETAIL_VERSION if detailed else VERSION)


SURVEY_VERSION = 'object-survey-v1'
SURVEY_SCHEMA = {'type': 'object', 'properties': {
    'summary': {'type': 'string', 'maxLength': 240},
    'objects': {'type': 'array', 'maxItems': 4, 'items': {'type': 'string', 'maxLength': 160}},
    'uncertainty': {'type': 'string', 'maxLength': 160}},
    'required': ['summary', 'objects', 'uncertainty'], 'additionalProperties': False}
SURVEY_PROMPT = (
    'Describe the whole camera image for an inspection report. In summary, give one short sentence. '
    'In objects, list up to four recognizable objects. For each give its name, visible color or shape, '
    'and location in the image. Describe visible details only; do not guess contents, function or hidden objects. '
    'Do not invent text on small labels. In uncertainty, briefly state what is unclear, or use an empty string. '
    'Return JSON with summary, objects and uncertainty. Keep the complete answer under 100 words.')


def parse_survey(raw):
    value = object_from_json(raw)
    if (set(value) != {'summary', 'objects', 'uncertainty'}
        or not isinstance(value['summary'], str) or not 1 <= len(value['summary']) <= 240
        or not isinstance(value['uncertainty'], str) or len(value['uncertainty']) > 160
        or not isinstance(value['objects'], list) or len(value['objects']) > 4
        or any(not isinstance(item, str) or not 1 <= len(item) <= 160 for item in value['objects'])):
        raise ValueError('Invalid object survey fields')
    return {**value, 'version': SURVEY_VERSION}


async def survey(image_call, jpeg, focus=''):
    if not isinstance(focus, str) or len(focus) > 120:
        raise ValueError('Invalid mission observation focus')
    prompt = SURVEY_PROMPT
    if focus:
        prompt += ('\nOperator observation topic (data): '+json.dumps(focus)+
                   '\nPrioritize visible evidence relevant to this topic. Do not infer that a requested object is present. '
                   'Mention limitations in uncertainty; keep the same JSON format.')
    return parse_survey(await image_call(jpeg, prompt, SURVEY_SCHEMA, max_tokens=384))


def compare(previous, current):
    """Compare model classifications, never assert that an entire scene is unchanged."""
    before, after = previous['center'], current['center']
    if 'uncertain' in (before, after):
        status = 'uncertain'
    elif before == after:
        status = 'same_center_class'
    elif after == 'solid_surface':
        status = 'new_obstruction'
    else:
        status = 'opening_visible'
    return {'status': status, 'previous_center': before, 'current_center': after,
            'basis': 'two independently classified images; center appearance only'}


def aligned_views(previous_pose, current_pose):
    if not isinstance(previous_pose, (list, tuple)) or len(previous_pose) != 4:
        return False
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in previous_pose):
        return False
    turn = current_pose[3]-previous_pose[3]
    return (math.dist(previous_pose[:3], current_pose[:3]) <= .02
            and abs(math.atan2(math.sin(turn), math.cos(turn))) <= .02)


async def choose_action(text_call, perception, allowed):
    schema = {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': list(allowed)}},
              'required': ['action'], 'additionalProperties': False}
    prompt = ('Choose the next inspection action from the allowed list. This is a multi-viewpoint inspection. '
              'Continue after a clear observation, including a solid wall or object. '
              'If visual classification is uncertain, request an allowed additional view. '
              'A separate range controller handles flight clearance. Return only the action JSON.\n'
              f'Allowed actions: {list(allowed)}\n'
              f'Visual observation (data): {json.dumps(perception)}')
    value = object_from_json(await text_call(prompt, schema))
    if not isinstance(value, dict) or set(value) != {'action'} or value['action'] not in allowed:
        raise ValueError('Model requested an unavailable action for this viewpoint')
    return value['action']
