"""Versioned comparative-choice scoring; independent of frequency and persona scores."""
import json
from fractions import Fraction
from pathlib import Path

VERSION = 'xq-disc-scenario-v2'
CONTEXTS = {'natural': 'Natural', 'adapted': 'Adapted'}
WEIGHTS = (3, 1, -1, -3)
DIMENSIONS = {
    'D': {'name': 'Direction', 'color': '#c73449',
          'focus': 'taking initiative, making decisions, and moving toward results',
          'question': 'Where could a clear decision help you move forward?'},
    'I': {'name': 'Interaction', 'color': '#967000',
          'focus': 'engaging people, sharing enthusiasm, and building support',
          'question': 'Who could you bring into your next conversation or idea?'},
    'S': {'name': 'Steadiness', 'color': '#23805b',
          'focus': 'offering steady support, maintaining continuity, and allowing time to adjust',
          'question': 'Where would a steady rhythm help you and the people around you?'},
    'C': {'name': 'Precision', 'color': '#326cb5',
          'focus': 'examining information, clarifying expectations, and checking details',
          'question': 'Which details would help you approach your next decision with clarity?'},
}
_SOURCE = json.loads((Path(__file__).resolve().parent / 'content/disc_scenarios_v2.json').read_text())
ITEMS = tuple(_SOURCE['items'])
ITEM_IDS = frozenset(item['id'] for item in ITEMS)


def questionnaire():
    return {'version': VERSION, 'contexts': CONTEXTS, 'dimensions': DIMENSIONS,
            'dimension_order': list(DIMENSIONS), 'items': ITEMS,
            'rank_labels': ['Most like me', 'Second', 'Third', 'Least like me'],
            'source': _SOURCE['source']}


def validate_submission(payload):
    if not isinstance(payload, dict) or set(payload) != {'version', 'responses'}:
        raise ValueError('Submit the assessment version and both sets of rankings.')
    if payload['version'] != VERSION:
        raise ValueError('This version needs a fresh Scenario ranking assessment. Return to the pilot menu to begin.')
    responses = payload['responses']
    if not isinstance(responses, dict) or set(responses) != set(CONTEXTS):
        raise ValueError('Complete both Natural and Adapted rankings.')
    for context, answers in responses.items():
        if not isinstance(answers, dict) or set(answers) != ITEM_IDS:
            raise ValueError(f'Rank all four alternatives in every {CONTEXTS[context]} scenario.')
        for ranking in answers.values():
            if (not isinstance(ranking, list) or len(ranking) != 4
                    or any(not isinstance(value, str) for value in ranking)
                    or set(ranking) != set(DIMENSIONS)):
                raise ValueError('Rank each of the four alternatives exactly once, from most to least like you.')
    return responses


def score_assessment(payload):
    responses = validate_submission(payload)
    count = len(ITEMS)
    profiles = {}
    summaries = {}
    for context in CONTEXTS:
        rows = {dimension: {'raw_total': 0, 'firsts': 0, 'lasts': 0, 'count': count}
                for dimension in DIMENSIONS}
        for ranking in responses[context].values():
            for position, dimension in enumerate(ranking):
                rows[dimension]['raw_total'] += WEIGHTS[position]
                rows[dimension]['firsts'] += position == 0
                rows[dimension]['lasts'] += position == 3
        for row in rows.values():
            index = 50 + Fraction(row['raw_total'] * 50, 3 * count)
            row['score'] = (2 * index.numerator + index.denominator) // (2 * index.denominator)
            row['description'] = f'Ranked first in {row["firsts"]} of {count} situations.'
        profiles[context] = rows
        highest = max(row['raw_total'] for row in rows.values())
        leaders = [DIMENSIONS[d]['name'].lower() for d, row in rows.items() if row['raw_total'] == highest]
        summaries[context] = ('Your rankings distribute equal emphasis across all four approaches.' if len(leaders) == 4 else
                              f'Your greatest relative emphasis went to {" and ".join(leaders)}.')

    sections = [{'id': 'welcome', 'title': 'Your scenario choices', 'text': (
        'Thank you for exploring how you approach different situations. '
        'You ranked four alternatives in each scenario, first for your Natural preferences and then for your Adapted work behavior. '
        'Each score summarizes the relative emphasis you gave an approach across your choices. '
        'A higher score means you placed that approach nearer the top of your rankings. '
        f'For your Natural preferences, {summaries["natural"][0].lower() + summaries["natural"][1:]} '
        f'For your Adapted work behavior, {summaries["adapted"][0].lower() + summaries["adapted"][1:]}')}]
    for dimension, info in DIMENSIONS.items():
        natural, adapted = (profiles[context][dimension] for context in CONTEXTS)
        delta = adapted['raw_total'] - natural['raw_total']
        comparison = ('This approach received equal relative emphasis in both contexts.' if delta == 0 else
                      f'This approach received greater relative emphasis in your {"Adapted work choices" if delta > 0 else "Natural preferences"}.')
        sections.append({'id': dimension, 'title': f'{dimension} · {info["name"]}', 'text': (
            f'{info["name"]} brings together {info["focus"]}. '
            f'Your Natural preference score is {natural["score"]} out of 100. '
            f'You ranked this approach first in {natural["firsts"]} of {count} situations. '
            f'Your Adapted preference score is {adapted["score"]} out of 100. '
            f'You ranked this approach first in {adapted["firsts"]} of {count} situations. '
            f'{comparison} {info["question"]}')})
    sections.append({'id': 'close', 'title': 'Bring your preferences into practice', 'text': (
        'Think of an upcoming situation and the approach you would naturally choose. '
        'Consider how another approach might contribute to the outcome you want. '
        'You can replay any section, download your report, or choose Start again to explore a fresh set of choices. '
        'Thank you for reflecting with XQ.')})
    return {'version': VERSION, 'score_kind': 'relative_preference_index',
            'scale': {'min': 0, 'max': 100, 'label': 'Relative preference',
                      'anchors': {0: 'Ranked last throughout', 100: 'Ranked first throughout'}},
            'scoring': {'rank_weights': WEIGHTS, 'groups_per_context': count, 'unrounded_profile_total': 200},
            'profiles': profiles, 'summaries': summaries, 'sections': sections, 'responses': responses}
