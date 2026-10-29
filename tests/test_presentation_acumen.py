import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, create_presentation_blueprint, PRESENTATION_BUDGET
from presentation_bundle import bundle_presentation
from presentation_acumen import acumen_charts

ROOT = Path(__file__).resolve().parents[1]


class AcumenPresentationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((ROOT / 'content/presentations/amethyst.json').read_text())
        self.session = Presentation(Mock(conversation_id=None, connected=False, pal_id='test'))
        app = Flask(__name__)
        app.register_blueprint(create_presentation_blueprint(self.session))
        self.api = app.test_client()

    def test_prepared_source_switches_narration_and_scores_together(self):
        response = self.api.post('/api/presentation/source', json={'profile': None, 'preset': 'amethyst'})
        self.assertEqual(response.status_code, 200)
        state = self.session.status()
        self.assertEqual(state['chapters'], self.bundle['chapters'])
        self.assertNotIn('eq', state['visuals'])
        self.assertIn('Amethyst', state['source'])
        self.assertEqual(state['visuals']['disc_di']['profiles'][0]['scores'][1]['value'], 94)
        self.assertEqual(state['visuals']['forces_second']['rows'][-1]['series'][1]['value'], 71)
        self.assertLessEqual(state['word_count'] / 110 * 60 + 60, PRESENTATION_BUDGET)
        self.api.post('/api/presentation/source', json={'profile': None})
        self.assertIn('eq', self.session.visuals)
        self.assertNotIn('aci_balance', self.session.visuals)

    def test_all_reported_aci_values_and_bias_directions(self):
        _, visuals, _ = bundle_presentation(self.bundle)
        panels = visuals['aci_balance']['panels']
        scores = [d for p in panels for d in p['dimensions']]
        self.assertEqual([s['clarity'] for s in scores], [92, 84, 80, 56, 60, 48])
        self.assertEqual([s['blind_spot'] for s in scores], [8, 16, 20, 44, 40, 52])
        self.assertEqual([s['bias'] for s in scores], ['mixed', 'under', 'over', 'under', 'over', 'over'])
        self.assertEqual([p['clarity_average'] for p in panels], [85, 55])
        self.assertEqual([p['emotional_bias_distortion'] for p in panels], [15, 45])
        self.assertEqual([s['value'] for p in panels for s in p['problems']], [84, 80, 78, 84, 64, 68, 56, 30])
        self.assertEqual([s['reference'] for p in panels for s in p['problems']], [86, 82, 81, 79, 77, 75, 75, 66])

    def test_missing_values_stay_missing_and_zero_stays_zero(self):
        aci = {'dimensions': {'understanding_others': {'clarity': 0, 'blind_spot': 0}}}
        panel = acumen_charts(aci)['aci_world']['panels'][0]
        self.assertEqual(panel['dimensions'][0]['clarity'], 0)
        self.assertIsNone(panel['dimensions'][1]['clarity'])
        self.assertIsNone(panel['clarity_average'])
        self.assertEqual(panel['dimensions'][0]['valuation'], 'Not reported')

    def test_invalid_upload_cannot_partially_replace_existing_source(self):
        original = self.session.status()
        for bad in (-1, 101, True, '92', float('nan'), float('inf')):
            bundle = copy.deepcopy(self.bundle)
            bundle['profile']['aci']['dimensions']['understanding_others']['clarity'] = bad
            response = self.api.post('/api/presentation/source', json={'profile': bundle})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.session.status(), original)
        for change in ('unknown_chart', 'unknown_bias', 'wrong_type', 'eq'):
            bundle = copy.deepcopy(self.bundle)
            if change == 'unknown_chart': bundle['chapters'][0]['visual'] = 'eq'
            if change == 'unknown_bias': bundle['profile']['aci']['dimensions']['sense_of_self']['bias'] = 'positive'
            if change == 'wrong_type': bundle['profile']['aci']['world'] = []
            if change == 'eq': bundle['profile']['eq'] = {}
            self.assertEqual(self.api.post('/api/presentation/source', json={'profile': bundle}).status_code, 400)
            self.assertEqual(self.session.status(), original)

    def test_unknown_preset_and_active_session_are_rejected(self):
        for preset in ('../presentation', {}, 'missing'):
            self.assertEqual(self.api.post('/api/presentation/source', json={'profile': None, 'preset': preset}).status_code, 400)
        self.session.client.conversation_id = 'live'
        self.assertEqual(self.api.post('/api/presentation/source', json={'profile': None, 'preset': 'amethyst'}).status_code, 400)
        self.assertEqual(self.session.revision, 0)

    def test_bundle_import_preserves_script_without_mutating_input(self):
        original = copy.deepcopy(self.bundle)
        response = self.api.post('/api/presentation/source', json={'profile': self.bundle})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session.chapters, original['chapters'])
        self.assertEqual(self.bundle, original)
        self.assertTrue(all(c['visual'] in self.session.visuals for c in self.session.chapters))
        clean = (ROOT / 'content/presentation_sources/amethyst/presentation-script.txt').read_text()
        for chapter in self.session.chapters:
            self.assertIn(chapter['text'], clean)
