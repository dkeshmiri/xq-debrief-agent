import copy
import json
from pathlib import Path
import unittest

from pydantic import TypeAdapter, ValidationError
from assessment_schema import Score
from narratives.narrative_renderer import (
    render_disc_narrative, render_driving_forces_narrative,
    render_eq_narrative, render_integrated_narrative,
)
from score_formatting import format_score


class ScoreFormattingTests(unittest.TestCase):
    def test_import_contract_emits_integers_and_preserves_unknowns(self):
        adapter = TypeAdapter(Score | None)
        for value in (0, 0.0, 72, 72.0, 100.0):
            result = adapter.validate_python(value)
            self.assertIs(type(result), int)
            self.assertEqual(adapter.dump_json(result), str(int(value)).encode())
        self.assertIsNone(adapter.validate_python(None))
        for value in (72.5, True, '72', -1, 101, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                adapter.validate_python(value)
        self.assertEqual(TypeAdapter(Score).json_schema()['type'], 'integer')

    def test_formatting_does_not_round_genuine_fractional_scores(self):
        self.assertEqual(format_score(72.0), '72')
        self.assertEqual(format_score(72.125), '72.125')

    def test_legacy_decimal_profiles_have_identical_narration_in_both_products(self):
        root = Path(__file__).resolve().parents[1]
        original = json.loads((root / 'data/personas/samuel.json').read_text())
        decimal = copy.deepcopy(original)
        groups = [decimal['disc']['natural'], decimal['disc']['adapted'],
                  decimal['driving_forces']['scores'], decimal['eq']['scores']]
        for group in groups:
            for key in group:
                group[key] = float(group[key])
        for key in ('self_composite', 'others_composite', 'total_eq'):
            decimal['eq'][key] = float(decimal['eq'][key])
        for experience in ('family', 'business'):
            for render in (render_disc_narrative, render_driving_forces_narrative,
                           render_eq_narrative, render_integrated_narrative):
                with self.subTest(experience=experience, renderer=render.__name__):
                    self.assertEqual(render(original, experience), render(decimal, experience))
