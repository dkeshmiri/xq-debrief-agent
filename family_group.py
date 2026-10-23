"""Bounded, deterministic family comparisons. Assessment values are never adjusted."""
from itertools import combinations

from comparison_engine import ComparisonEngine

MAX_GROUP_MEMBERS = 4


def validate_member_ids(person_ids):
    if (not isinstance(person_ids, list) or not 2 <= len(person_ids) <= MAX_GROUP_MEMBERS
            or any(not isinstance(value, str) or not value.strip() for value in person_ids)):
        raise ValueError('Choose between two and four family members.')
    if len(set(person_ids)) != len(person_ids):
        raise ValueError('Choose distinct family members.')
    return list(person_ids)


class FamilyGroupEngine:
    def compare(self, personas):
        personas = list(personas)
        ids = validate_member_ids([persona['person']['person_id'] for persona in personas])
        engine = ComparisonEngine()
        pairs = [
            {'member_ids': [a['person']['person_id'], b['person']['person_id']],
             'comparison': engine.create_detached_packet(a, b)}
            for a, b in combinations(personas, 2)
        ]
        members = [{key: persona['person'][key] for key in ('person_id', 'display_name', 'family_role')}
                   for persona in personas]
        sections = {
            'disc_natural': [p['disc']['natural'] for p in personas],
            'disc_adapted': [p['disc']['adapted'] for p in personas],
            'driving_forces': [p['driving_forces']['scores'] for p in personas],
            'eq_dimensions': [p['eq']['scores'] for p in personas],
            'eq_composites': [{'SELF': p['eq']['self_composite'], 'OTHERS': p['eq']['others_composite'],
                               'TOTAL_EQ': p['eq']['total_eq']} for p in personas],
        }
        return {
            'members': members,
            'assessments': {name: {metric: {pid: values[metric] for pid, values in zip(ids, scores)}
                                   for metric in scores[0]} for name, scores in sections.items()},
            'pairs': pairs,
        }
