"""Independent category agreement on camera crops, without evaluator labels."""
import json

VERSION = 'cross-model-category-v1'
CATEGORIES = ['fire_extinguisher', 'paint_can', 'gas_cylinder', 'storage_container', 'other', 'uncertain']
PROMPT = ('Identify the central object in this image from its visible appearance. '
          'First describe the visible shape and attachments in one short sentence. '
          'Then choose category: fire_extinguisher, paint_can, gas_cylinder, storage_container, other, or uncertain. '
          'A red colour or cylindrical shape alone does not establish the purpose. '
          'Do not invent hidden parts. Return JSON with evidence and category.')
SCHEMA = {'type': 'object', 'properties': {'evidence': {'type': 'string', 'maxLength': 180},
          'category': {'type': 'string', 'enum': CATEGORIES}}, 'required': ['evidence', 'category'], 'additionalProperties': False}


def parse(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {'evidence', 'category'}:
        raise ValueError('Invalid crop identity response')
    if value['category'] not in CATEGORIES or not isinstance(value['evidence'], str) or len(value['evidence']) > 180:
        raise ValueError('Invalid crop identity evidence')
    return value


def supported(category, review):
    return bool(category and category.get('category') == 'fire_extinguisher'
                and review and review.get('accepted') is True)
