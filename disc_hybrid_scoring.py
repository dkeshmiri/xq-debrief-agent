"""Hybrid pilot: independent behavior frequencies plus first-approach choices.

Choices add context to the report; they never raise or lower frequency scores.
"""
import json
from fractions import Fraction
from pathlib import Path

VERSION = 'xq-disc-hybrid-v1'
CONTEXTS = {'natural': 'Natural', 'adapted': 'Adapted'}
SCALE = ['Never', 'Rarely', 'Sometimes', 'Often', 'Very often']
_SOURCE = json.loads((Path(__file__).resolve().parent / 'content/disc_hybrid_v1.json').read_text())
DIMENSIONS = _SOURCE['dimensions']
ITEMS = tuple(_SOURCE['items'])
ITEM_IDS = frozenset(item['id'] for item in ITEMS)


def questionnaire():
    return {'version': VERSION, 'contexts': CONTEXTS, 'scale': SCALE,
            'dimensions': DIMENSIONS, 'dimension_order': list(DIMENSIONS),
            'items': ITEMS, 'source': _SOURCE['source'],
            'source_version': _SOURCE['source_version']}


def validate_submission(payload):
    if not isinstance(payload, dict) or set(payload) != {'version', 'responses'}:
        raise ValueError('Submit the assessment version and both sets of answers.')
    if payload['version'] != VERSION:
        raise ValueError('This version needs a fresh Hybrid assessment. Return to the pilot menu to begin.')
    responses = payload['responses']
    if not isinstance(responses, dict) or set(responses) != set(CONTEXTS):
        raise ValueError('Complete both Natural and Adapted answers.')
    for context, answers in responses.items():
        if not isinstance(answers, dict) or set(answers) != ITEM_IDS:
            raise ValueError(f'Complete every situation in {CONTEXTS[context]}.')
        for answer in answers.values():
            if not isinstance(answer, dict) or set(answer) != {'ratings', 'first'}:
                raise ValueError('Rate all four behaviors and choose a first approach in every situation.')
            ratings = answer['ratings']
            if (not isinstance(ratings, dict) or set(ratings) != set(DIMENSIONS)
                    or any(type(value) is not int or not 0 <= value <= 4 for value in ratings.values())):
                raise ValueError('Rate each behavior from Never through Very often.')
            if not isinstance(answer['first'], str) or answer['first'] not in DIMENSIONS:
                raise ValueError('Choose the approach you would start with in every situation.')
    return responses


def _frequency(total, count):
    average = Fraction(total, count)
    lower = average.numerator // average.denominator
    if average.denominator == 1:
        return SCALE[lower].lower()
    return f'between {SCALE[lower].lower()} and {SCALE[lower + 1].lower()}'


def score_assessment(payload):
    responses = validate_submission(payload)
    count = len(ITEMS)
    profiles, summaries = {}, {}
    for context, answers in responses.items():
        rows = {}
        for dimension in DIMENSIONS:
            total = sum(answer['ratings'][dimension] for answer in answers.values())
            index = Fraction(total * 25, count)
            rows[dimension] = {
                'total': total, 'count': count,
                'score': (2 * index.numerator + index.denominator) // (2 * index.denominator),
                'frequency': _frequency(total, count),
                'firsts': sum(answer['first'] == dimension for answer in answers.values()),
            }
        profiles[context] = rows
        most = max(row['firsts'] for row in rows.values())
        leaders = [DIMENSIONS[d]['name'].lower() for d, row in rows.items() if row['firsts'] == most]
        summaries[context] = (
            'You chose each approach first equally often.' if len(leaders) == len(DIMENSIONS) else
            f'You chose {" and ".join(leaders)} first most often: {most} of {count} situations'
            f'{" each" if len(leaders) > 1 else ""}.')

    sections = [{'id': 'welcome', 'title': 'Your approaches in action', 'text': (
        'Thank you for exploring how you approach everyday life and work. '
        'Your Natural and Adapted scores describe how often you use each behavior. '
        'Each dimension has its own scale, so several can be high together. '
        'Zero means never, fifty means sometimes, and one hundred means very often. '
        'Your first choices add another view: which approach you would start with in each situation. '
        f'For Natural, {summaries["natural"][0].lower() + summaries["natural"][1:]} '
        f'For Adapted, {summaries["adapted"][0].lower() + summaries["adapted"][1:]}')}]
    for dimension, info in DIMENSIONS.items():
        natural, adapted = (profiles[context][dimension] for context in CONTEXTS)
        difference = adapted['total'] - natural['total']
        comparison = ('You described these behaviors with the same average frequency in both contexts.'
                      if difference == 0 else
                      f'You described these behaviors more often in your {"Adapted work" if difference > 0 else "Natural everyday"} responses.')
        sections.append({'id': dimension, 'title': f'{dimension} · {info["name"]}', 'text': (
            f'{info["name"]} brings together {info["focus"]}. '
            f'Your Natural frequency score is {natural["score"]} out of 100; your answers average {natural["frequency"]}. '
            f'Your Adapted frequency score is {adapted["score"]} out of 100; your answers average {adapted["frequency"]}. '
            f'You chose this approach first in {natural["firsts"]} of {count} Natural situations '
            f'and {adapted["firsts"]} of {count} Adapted situations. '
            f'{comparison} {info["question"]}')})
    sections.append({'id': 'close', 'title': 'Put your approaches to work', 'text': (
        'Think of an upcoming situation and the approaches you could bring to it. '
        'Consider which one you would start with and which others would help you follow through. '
        'You can replay any section, download your report, or choose Start again for a fresh assessment. '
        'Thank you for exploring your behavioral preferences with XQ.')})
    return {'version': VERSION, 'score_kind': 'hybrid_frequency_with_first_choices',
            'scale': {'min': 0, 'max': 100, 'label': 'Behavior frequency',
                      'anchors': dict(zip((0, 25, 50, 75, 100), SCALE))},
            'scoring': {'score_source': 'independent_ratings', 'formula': '25 * rating_total / situation_count',
                        'situations_per_context': count, 'first_choice_effect_on_score': 0},
            'profiles': profiles, 'summaries': summaries, 'sections': sections, 'responses': responses}
