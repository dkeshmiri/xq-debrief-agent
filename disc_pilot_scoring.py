"""Deterministic, self-contained scoring for the XQ DISC frequency pilot.

Scores summarize response frequency, independently for each dimension/context.
They are not fed through the imported-assessment narrative classifiers.
"""
from fractions import Fraction

VERSION = 'xq-disc-frequency-v1'
CONTEXTS = {'natural': 'Everyday', 'adapted': 'At work'}
SCALE = ['Never', 'Rarely', 'Sometimes', 'Often', 'Very often']
DIMENSIONS = {
    'D': {'name': 'Direction', 'color': '#c73449',
          'focus': 'taking initiative, making decisions, and addressing challenges',
          'question': 'Where would a clear decision help you move something forward?'},
    'I': {'name': 'Interaction', 'color': '#967000',
          'focus': 'starting conversations, sharing ideas, and involving people',
          'question': 'Who would benefit from hearing your ideas or encouragement?'},
    'S': {'name': 'Steadiness', 'color': '#23805b',
          'focus': 'maintaining a steady pace, listening, and following through',
          'question': 'Which routine helps you give people dependable support?'},
    'C': {'name': 'Precision', 'color': '#326cb5',
          'focus': 'checking details, using criteria, and working through information',
          'question': 'Where would clearer information make your next step easier?'},
}

# Item identities and wording are part of VERSION. Change the version when either changes.
_STATEMENTS = {
    'D': [
        'I take the initiative when a next step needs an owner.',
        'I state my preferred outcome directly.',
        'I make a decision when several workable options are available.',
        'I address an obstacle as soon as I notice it.',
        'I question an approach when it slows progress toward a goal.',
        'I set a challenging target for myself.',
    ],
    'I': [
        'I start conversations with people I have just met.',
        'I express enthusiasm when sharing an idea.',
        'I invite others into a discussion.',
        'I think through ideas by talking about them.',
        'I reach out to people to build a connection.',
        'I encourage others by describing possibilities.',
    ],
    'S': [
        'I work at a steady pace.',
        'I let someone finish explaining before I respond.',
        'I return to familiar routines to organize my day.',
        'I follow through on recurring commitments.',
        'I give people time to adjust when a plan changes.',
        'I offer ongoing support while someone works through a task.',
    ],
    'C': [
        'I check details before sharing my work.',
        'I ask for clear criteria before starting a task.',
        'I compare available information before choosing an approach.',
        'I work through a task in a planned sequence.',
        'I look for the reason behind an inconsistency.',
        'I refer to instructions when a process is unfamiliar.',
    ],
}
ITEMS = tuple({'id': f'{dimension}{index + 1}', 'dimension': dimension, 'text': statements[index]}
              for index in range(6) for dimension, statements in _STATEMENTS.items())
ITEM_IDS = frozenset(item['id'] for item in ITEMS)


def questionnaire():
    return {'version': VERSION, 'contexts': CONTEXTS, 'scale': SCALE,
            'dimensions': DIMENSIONS, 'dimension_order': list(DIMENSIONS), 'items': ITEMS}


def validate_submission(payload):
    if not isinstance(payload, dict) or set(payload) != {'version', 'responses'}:
        raise ValueError('Submit the assessment version and both sets of answers.')
    if payload['version'] != VERSION:
        raise ValueError('This questionnaire has changed. Start a new assessment from the pilot menu.')
    responses = payload['responses']
    if not isinstance(responses, dict) or set(responses) != set(CONTEXTS):
        raise ValueError('Complete both Everyday and At work answers.')
    for context, answers in responses.items():
        if not isinstance(answers, dict) or set(answers) != ITEM_IDS:
            raise ValueError(f'Answer every statement in {CONTEXTS[context]}.')
        if any(type(value) is not int or not 0 <= value <= 4 for value in answers.values()):
            raise ValueError('Choose a response from Never through Very often for every statement.')
    return responses


def frequency_description(total, count):
    average = Fraction(total, count)
    lower = average.numerator // average.denominator
    if average.denominator == 1:
        return SCALE[lower].lower()
    return f'between {SCALE[lower].lower()} and {SCALE[lower + 1].lower()}'


def score_assessment(payload):
    responses = validate_submission(payload)
    profiles = {}
    for context, answers in responses.items():
        profiles[context] = {}
        for dimension in DIMENSIONS:
            values = [answers[item['id']] for item in ITEMS if item['dimension'] == dimension]
            total, count = sum(values), len(values)
            # Round half up for display; retain exact totals for comparisons/re-scoring.
            index = Fraction(total * 25, count)
            profiles[context][dimension] = {
                'total': total, 'count': count,
                'score': (2 * index.numerator + index.denominator) // (2 * index.denominator),
                'frequency': frequency_description(total, count),
            }

    sections = [{'id': 'welcome', 'title': 'Your behavioral preferences', 'text': (
        'Thank you for taking time to reflect on how you approach everyday life and work. '
        'Your report brings together direction, interaction, steadiness, and precision. '
        'Each score summarizes how often you described these behaviors. '
        'The scale runs from zero for never to one hundred for very often, '
        'with sometimes at fifty. Let’s explore the two contexts side by side.')}]
    for dimension, info in DIMENSIONS.items():
        natural, adapted = (profiles[context][dimension] for context in CONTEXTS)
        difference = adapted['total'] - natural['total']
        comparison = ('You described these behaviors with the same average frequency in both contexts.'
                      if difference == 0 else
                      f'You described these behaviors more often {"at work than in everyday life" if difference > 0 else "in everyday life than at work"}.')
        sections.append({'id': dimension, 'title': f'{dimension} · {info["name"]}', 'text': (
            f'{info["name"]} brings together {info["focus"]}. '
            f'Your Everyday score is {natural["score"]} out of 100; your answers average {natural["frequency"]}. '
            f'Your At work score is {adapted["score"]} out of 100; your answers average {adapted["frequency"]}. '
            f'{comparison} {info["question"]}')})
    sections.append({'id': 'close', 'title': 'Put your reflections into action', 'text': (
        'Choose one behavior you would like to bring into your next conversation or task. '
        'Think about when it helps, and what you would like to try next. '
        'You can revisit any section, download your report, or choose Start again for a fresh assessment. '
        'Thank you for exploring your behavioral preferences with XQ.')})
    return {'version': VERSION, 'score_kind': 'response_frequency_index',
            'scale': {'min': 0, 'max': 100, 'anchors': dict(zip((0, 25, 50, 75, 100), SCALE))},
            'profiles': profiles, 'sections': sections, 'responses': responses}
