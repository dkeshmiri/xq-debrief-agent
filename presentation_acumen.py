"""Report-backed ACI visuals for prepared presentations only."""

DIMENSIONS = (
    ('understanding_others', 'Understanding Others', 'People', 'intrinsic'),
    ('practical_thinking', 'Practical Thinking', 'Tasks', 'extrinsic'),
    ('systems_judgment', 'Systems Judgment', 'Systems', 'systemic'),
    ('sense_of_self', 'Sense of Self', 'Me', 'intrinsic'),
    ('role_awareness', 'Role Awareness', 'Roles', 'extrinsic'),
    ('self_direction', 'Self Direction', 'Future', 'systemic'),
)
PROBLEMS = (('people', 'People / Individuality'), ('practical', 'Practical situations / Roles'),
            ('theoretical', 'Theoretical situations / Future'), ('decisions', 'Overall problem solving and decision making'))
VALUATIONS = {'over': 'Overvaluation', 'mixed': 'Mixed valuation', 'under': 'Undervaluation'}


def acumen_charts(aci):
    panels = []
    for index, (key, title) in enumerate((('world', 'World View'), ('self', 'Self View'))):
        summary = aci.get(key, {})
        dimensions = []
        for name, label, context, color in DIMENSIONS[index * 3:index * 3 + 3]:
            score = aci.get('dimensions', {}).get(name, {})
            dimensions.append(dict(label=label, context=context, color=color,
                clarity=score.get('clarity'), blind_spot=score.get('blind_spot'),
                bias=score.get('bias'), valuation=VALUATIONS.get(score.get('bias'), 'Not reported')))
        panels.append(dict(title=title, dimensions=dimensions,
            clarity_average=summary.get('clarity_average'),
            emotional_bias_distortion=summary.get('emotional_bias_distortion'),
            problems=[dict(label=label, value=summary.get('problem_solving', {}).get(key, {}).get('score'),
                           reference=summary.get('problem_solving', {}).get(key, {}).get('report_reference'))
                      for key, label in PROBLEMS]))
    note = ('Clarity and blind spots are reported on a 0–100 scale, not percentiles. '
            'Arrows describe valuation direction, not a score or a diagnosis. '
            'Population bands and unnumbered dial magnitudes are not estimated.')
    return {key: dict(kind='aci', title=title, note=note, panels=selected)
            for key, title, selected in (
                ('aci_balance', 'Acumen · Dimensional balance', panels),
                ('aci_world', 'Acumen · World View', panels[:1]),
                ('aci_self', 'Acumen · Self View', panels[1:]))}
