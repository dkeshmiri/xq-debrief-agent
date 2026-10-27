"""Presentation charts and optional narration from one assessment source."""
from schemas import validate_persona
from score_formatting import format_score

DISC = {'D': 'Dominance', 'I': 'Influence', 'S': 'Steadiness', 'C': 'Compliance'}
FORCES = [('Intellectual', 'Instinctive'), ('Resourceful', 'Selfless'),
          ('Harmonious', 'Objective'), ('Altruistic', 'Intentional'),
          ('Commanding', 'Collaborative'), ('Structured', 'Receptive')]
EQ = {'self_awareness': 'Self-Awareness', 'self_regulation': 'Self-Regulation',
      'motivation': 'Motivation', 'social_awareness': 'Social Awareness',
      'social_regulation': 'Social Regulation'}


def charts(profile):
    disc = profile.get('disc', {})
    forces = profile.get('driving_forces', {}).get('scores', {})
    eq = profile.get('eq', {})

    def disc_chart(keys):
        return {'kind': 'disc', 'focus': list(keys), 'profiles': [
                    {'label': mode.title(), 'scores': [{'key': key, 'label': label, 'value': disc.get(mode, {}).get(key)} for key, label in DISC.items()]}
                    for mode in ('natural', 'adapted')],
                'title': 'Natural and Adapted DISC', 'note': 'Scores on a 0–100 scale. Outlined columns mark this chapter’s focus. The 50 line is a reference, not a population average.',
                'rows': [{'label': DISC[key], 'series': [
                    {'label': mode.title(), 'value': disc.get(mode, {}).get(key), 'color': key}
                    for mode in ('natural', 'adapted')]} for key in keys]}

    def force_chart(pairs):
        return {'kind': 'forces', 'title': 'Driving Forces', 'note': 'Each force has its own score. Paired scores do not need to add up to 100.',
                'rows': [{'label': ' / '.join(pair), 'series': [
                    {'label': key, 'value': forces.get(key), 'color': 'force'} for key in pair]} for pair in pairs]}

    eq_chart = {'kind': 'eq', 'title': 'Emotional intelligence', 'note': 'Reported scores, not population percentiles or prescribed targets.',
                'rows': [{'label': label, 'series': [{'label': 'Score', 'value': eq.get('scores', {}).get(key), 'color': 'eq'}]}
                         for key, label in EQ.items()]}
    for key, label in [('self_composite', 'Self composite'), ('others_composite', 'Others composite'), ('total_eq', 'Total EQ')]:
        eq_chart['rows'].append({'label': label, 'composite': True, 'series': [{'label': 'Score', 'value': eq.get(key), 'color': 'eq'}]})
    return {'overview': {'title': 'Three perspectives. One conversation.', 'note': 'Explore behavior, motivation, and emotional intelligence without combining them into a single score.',
                         'cards': [{'title': 'DISC', 'text': 'How you approach people, pace, problems, and processes.'},
                                   {'title': 'Driving Forces', 'text': 'What makes an activity worth pursuing for you.'},
                                   {'title': 'EQ', 'text': 'How you understand and manage emotions and relationships.'}]},
            'disc_di': disc_chart('DI'), 'disc_sc': disc_chart('SC'),
            'forces_first': force_chart(FORCES[:3]), 'forces_second': force_chart(FORCES[3:]), 'eq': eq_chart}


def profile_presentation(profile):
    """Generate factual speech and visuals together; never reuse another person's script."""
    validate_persona(profile)
    name = profile['person']['display_name']
    visuals = charts(profile)
    chapters = [{'title': f'{name}: your profile', 'visual': 'overview',
                 'text': f'Thank you, {name}. We will explore your DISC preferences, Driving Forces, and emotional intelligence. These are reported assessment scores, not population percentiles.'}]
    for key in ('disc_di', 'disc_sc', 'forces_first', 'forces_second', 'eq'):
        chart = visuals[key]
        sentences = []
        for row in chart['rows']:
            for series in row['series']:
                if series['value'] is not None:
                    label = row['label'] if series['label'] == 'Score' else (
                        f"{series['label']} {row['label']}" if key.startswith('disc') else series['label'])
                    sentences.append(f"Your {label} score is {format_score(series['value'])}.")
        title = chart['title'] + ': ' + ', '.join(row['label'] for row in chart['rows'][:2]) if key != 'eq' else chart['title']
        chapters.append({'title': title, 'visual': key, 'text': ' '.join(sentences)})
    chapters[-1]['text'] += f' Thank you, {name}, for exploring your profile with us.'
    return chapters, visuals, f"Profile: {name} · {profile['assessment']['source']}"
