"""Serializable practice rules shared by the server and the static UI builder.

Keep this module standard-library only so building the UI needs no backend environment.
"""
import json
from pathlib import Path

DURATION_QUESTIONS = {5: 2, 10: 3, 15: 4}


def role_metadata():
    path = Path(__file__).resolve().parents[2] / 'data' / 'roles.json'
    roles = json.loads(path.read_text(encoding='utf-8'))
    for key, value in roles.items():
        if not key or not all(isinstance(value.get(field), str) and value[field].strip()
                              for field in ('name', 'group', 'summary', 'focus')):
            raise ValueError('Invalid role metadata')
    return roles


def practice_configuration(questions, *, theme_limit=3, names=None):
    metadata = role_metadata()
    positions = {}
    for question in questions:
        key = question['position']
        if key not in positions:
            details = metadata.get(key, {'name': (names or {}).get(key, key),
                                        'group': '其他方向', 'summary': '', 'focus': ''})
            positions[key] = {**details, 'count': 0, 'themes': []}
        entry = positions[key]
        entry['count'] += 1
        if not question.get('is_coding') and question['theme'] not in entry['themes']:
            entry['themes'].append(question['theme'])
    # Display order is a product choice in roles.json, independent of filenames or seed order.
    order = [*metadata, *sorted(set(positions) - metadata.keys())]
    positions = {key: positions[key] for key in order if key in positions}
    return {
        'positions': positions,
        'durations': [{'minutes': minutes, 'question_count': count}
                      for minutes, count in DURATION_QUESTIONS.items()],
        'theme_limit': theme_limit,
        'question_count': sum(entry['count'] for entry in positions.values()),
    }
