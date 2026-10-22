"""Candidate detail checks. Pixels and predicted boxes only; no scene labels.

These are correlated observations from one VLM, not calibrated probabilities.
The gate requires visible parts in two views in addition to ray geometry.
"""
import io
import json
import math

VERSION = 'visible-parts-v2'
PROMPT = (
    'Look at the central red object. First write evidence: one short sentence describing its visible shape '
    'and attachments without naming its purpose or guessing unseen parts. Then fill these JSON fields '
    'from the image: body = cylinder, box, other, or unknown. '
    'side = attached curved tube if a flexible curved tube visibly connects to this object; '
    'no attached curved tube visible if none is seen; unknown if obscured or too small to judge. '
    'top = projecting bar, flat round lid, other, or unknown. '
    'A straight shelf support behind the object is not an attached tube. '
    'Return JSON with evidence, body, side, top. Use the exact field values listed above.')
PARTS = {
    'body': ['cylinder', 'box', 'other', 'unknown'],
    'side': ['attached curved tube', 'no attached curved tube visible', 'unknown'],
    'top': ['projecting bar', 'flat round lid', 'other', 'unknown'],
}
SCHEMA = {'type': 'object', 'properties': {
    'evidence': {'type': 'string', 'maxLength': 160},
    **{k: {'type': 'string', 'enum': v} for k, v in PARTS.items()}},
    'required': ['evidence', *PARTS], 'additionalProperties': False}


def parse(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != set(SCHEMA['required']):
        raise ValueError('Invalid identity fields')
    if any(value[k] not in choices for k, choices in PARTS.items()):
        raise ValueError('Invalid identity feature')
    if not isinstance(value['evidence'], str) or len(value['evidence']) > 160:
        raise ValueError('Invalid identity evidence')
    return value


def supported(parts):
    return bool(parts and parts.get('body') == 'cylinder'
                and parts.get('side') == 'attached curved tube'
                and parts.get('top') == 'projecting bar')


def needs_detail(detail, bbox):
    """Acquisition cue only; never makes an identity check pass.

    Adequate for inference is not necessarily enough detail for identification.
    Use the model's predicted pixel extent and clipping, not evaluator boxes.
    """
    size=(detail or {}).get('crop',{}).get('source_box_pixels')
    return bool(bbox and (not size or size[0]<48 or size[1]<96
                         or min(bbox[:2])<=10 or max(bbox[2:])>=990))


def reinspection_needed(confirmations, location, first_supported, current_supported, detail, bbox):
    """Uncertain small candidates may earn another look, never a found claim."""
    if not (1<=confirmations<4) or not location or first_supported and current_supported:
        return False
    review=(detail or {}).get('independent_review',{})
    return bool(first_supported or current_supported or review.get('accepted') or needs_detail(detail,bbox))


def crop_candidate(jpeg, bbox):
    """Pad the model's box. Never use evaluator boxes; never invent image detail."""
    from PIL import Image  # Optional flight-evaluation dependency, not needed by policy-only users.
    if (not isinstance(bbox, list) or len(bbox) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 <= v <= 1000 for v in bbox)
            or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
        raise ValueError('Invalid candidate crop box')
    with Image.open(io.BytesIO(jpeg)) as source:
        image = source.convert('RGB')
    box = [bbox[i]*image.size[i % 2]/1000 for i in range(4)]
    width, height = box[2]-box[0], box[3]-box[1]
    bounds = [max(0, math.floor(box[0]-.25*width)), max(0, math.floor(box[1]-.15*height)),
              min(image.width, math.ceil(box[2]+.25*width)), min(image.height, math.ceil(box[3]+.15*height))]
    crop = image.crop(bounds)
    crop.thumbnail((512, 512), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    crop.save(output, format='JPEG', quality=90)
    return output.getvalue(), {'bounds_pixels': bounds, 'source_box_pixels': [width, height],
                               'output_size': list(crop.size), 'upscaled': False,
                               'adequate_pixels': width >= 24 and height >= 48}


def guarded_actions(*, remaining, confirmation_available, location, first_supported, current_supported):
    allowed = {}
    if location and first_supported and current_supported:
        # Completion is a terminal state. Do not offer another check that can
        # discard already sufficient evidence and restart the search.
        return {'found': 'Report the visually supported target and its triangulated position.'}
    if confirmation_available:
        allowed['confirm'] = 'Inspect the candidate from a second camera viewpoint.'
    if remaining:
        allowed['scan'] = 'Continue searching another area; a candidate is not a confirmed target.'
    else:
        allowed['unresolved'] = 'Report search incomplete without a supported target; absence is not proved.'
    return allowed


def guarded_state(visual, parts, remaining, confirmation_available, location, first_supported, current_supported=None):
    if current_supported is None:current_supported=supported(parts)
    return (f'Mission: locate a red fire extinguisher with a hose and handle. '
            f'Proposal (unverified): {json.dumps(visual)}. '
            f'Close crop observed parts: {json.dumps(parts)}. '
            f'Candidate rays intersect: {bool(location)}. '
            f'Required visual checks supported in both views: {bool(first_supported and current_supported)}. '
            f'Another viewpoint available: {confirmation_available}. Unvisited areas: {remaining}. '
            'Intersecting rays verify position only, never object identity. Missing details require more evidence.')
