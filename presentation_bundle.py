"""Validate scripted presentation imports without extending debrief persona schemas."""
from copy import deepcopy
from math import isfinite
from presentation_acumen import DIMENSIONS, VALUATIONS, PROBLEMS
from presentation_visuals import charts, DISC, FORCES, EQ


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object.')
    return value


def score(value):
    if value is not None and (type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 100):
        raise ValueError('Reported scores must be numbers from 0 to 100, or null when not reported.')


def bundle_presentation(bundle):
    if type(bundle.get('presentation_version')) is not int or bundle['presentation_version'] != 1:
        raise ValueError('Unsupported presentation version.')
    profile = object_value(bundle.get('profile'), 'profile')
    source = profile.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('A presentation source label is required.')
    disc = object_value(profile.get('disc', {}), 'DISC')
    for mode in ('natural', 'adapted'):
        values = object_value(disc.get(mode, {}), mode)
        for key in DISC:
            score(values.get(key))
    forces = object_value(profile.get('driving_forces', {}), 'Driving Forces')
    values = object_value(forces.get('scores', {}), 'Driving Forces scores')
    for pair in FORCES:
        for key in pair:
            score(values.get(key))
    if 'aci' in profile and 'eq' in profile:
        raise ValueError('Choose ACI or EQ for this presentation, not both.')
    if 'aci' in profile:
        aci = object_value(profile['aci'], 'ACI')
        dimensions = object_value(aci.get('dimensions', {}), 'ACI dimensions')
        for key, *_ in DIMENSIONS:
            values = object_value(dimensions.get(key, {}), key)
            score(values.get('clarity'))
            score(values.get('blind_spot'))
            if values.get('bias') is not None and values['bias'] not in VALUATIONS:
                raise ValueError('ACI bias must be over, mixed, under, or null.')
        for view in ('world', 'self'):
            values = object_value(aci.get(view, {}), view)
            score(values.get('clarity_average'))
            score(values.get('emotional_bias_distortion'))
            problems = object_value(values.get('problem_solving', {}), 'Problem solving')
            for key, _ in PROBLEMS:
                problem = object_value(problems.get(key, {}), key)
                score(problem.get('score'))
                score(problem.get('report_reference'))
    else:
        eq = object_value(profile.get('eq', {}), 'EQ')
        values = object_value(eq.get('scores', {}), 'EQ scores')
        for key in EQ:
            score(values.get(key))
        for key in ('self_composite', 'others_composite', 'total_eq'):
            score(eq.get(key))
    visuals = charts(profile)
    chapters = bundle.get('chapters')
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 30:
        raise ValueError('Supply between 1 and 30 presentation chapters.')
    for chapter in chapters:
        object_value(chapter, 'Chapter')
        for key in ('title', 'text', 'visual'):
            if not isinstance(chapter.get(key), str) or not chapter[key].strip():
                raise ValueError(f'Each chapter needs a {key}.')
        if chapter['visual'] not in visuals:
            raise ValueError('A chapter references an unavailable chart.')
    return deepcopy(chapters), visuals, source
