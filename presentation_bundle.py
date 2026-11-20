"""Validate scripted presentation imports without extending debrief persona schemas."""
from copy import deepcopy
from math import isfinite
from presentation_acumen import DIMENSIONS, VALUATIONS, PROBLEMS
from presentation_visuals import charts, DISC, FORCES, EQ
from presentation_investor import investor_visuals
from presentation_reports import report_visuals


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object.')
    return value


def score(value):
    if value is not None and (type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 100):
        raise ValueError('Reported scores must be numbers from 0 to 100, or null when not reported.')


def presentation_parts(bundle, chapters):
    """Contiguous chapter ranges, each played in its own provider session."""
    parts = bundle.get('parts')
    if parts is None:
        return [dict(title='Presentation', chapter_start=0, chapter_end=len(chapters)-1)]
    if not isinstance(parts, list) or not 1 <= len(parts) <= len(chapters):
        raise ValueError('Presentation parts must cover all chapters in order.')
    expected = 0
    for part in parts:
        object_value(part, 'Part')
        start, end = part.get('chapter_start'), part.get('chapter_end')
        if (not isinstance(part.get('title'), str) or not part['title'].strip()
                or type(start) is not int or type(end) is not int
                or start != expected or not start <= end < len(chapters)):
            raise ValueError('Each part needs a title and consecutive chapter boundaries.')
        expected = end + 1
    if expected != len(chapters):
        raise ValueError('Presentation parts must cover every chapter exactly once.')
    return deepcopy(parts)


def bundle_presentation(bundle):
    if type(bundle.get('presentation_version')) is not int or bundle['presentation_version'] != 1:
        raise ValueError('Unsupported presentation version.')
    if bundle.get('language', 'en') not in ('en', 'fa'):
        raise ValueError('Presentation language must be en or fa.')
    kind = bundle.get('presentation_type')
    if kind == 'investor':
        visuals, source = investor_visuals(bundle)
    elif kind == 'report_debrief':
        visuals, source = report_visuals(bundle)
    elif kind is None:
        visuals, source = profile_visuals(bundle.get('profile'))
    else:
        raise ValueError('Unknown presentation type.')
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
    presentation_parts(bundle, chapters)
    return deepcopy(chapters), visuals, source


def profile_visuals(profile):
    profile = object_value(profile, 'profile')
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
    ranks = object_value(forces.get('ranks', {}), 'Driving Forces ranks')
    known_forces = {key for pair in FORCES for key in pair}
    if any(key not in known_forces or type(value) is not int or not 1 <= value <= 12
           for key, value in ranks.items()):
        raise ValueError('Driving Forces ranks must use known force names and whole numbers from 1 to 12.')
    if len(set(ranks.values())) != len(ranks):
        raise ValueError('Each reported Driving Force rank must be unique.')
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
    wheel = disc.get('wheel')
    if wheel is not None:
        # Curated report assets only: uploads cannot supply arbitrary image URLs.
        if wheel != 'mario-2026-11-11':
            raise ValueError('Unknown report wheel.')
        visuals['disc_wheel'] = dict(
            kind='report_image', title='DISC · People and action',
            note='Mario’s Natural and Adapted behavioral styles',
            image='/static/presentation-assets/mario-insights-wheel.png',
            alt='Mario’s Success Insights Wheel: Natural dot at position 14, Persuading Promoter; Adapted star at position 13, Promoting Persuader.',
            legend=['● Natural · 14 · Persuading Promoter',
                    '★ Adapted · 13 · Promoting Persuader'],
            attribution='Source: Mario Calamita · TriMetrix HD · November 11, 2026 · page 29. TTI Success Insights® Wheel. Copyright © 1992–2026 TTI Success Insights LTD.')
    return visuals, source
