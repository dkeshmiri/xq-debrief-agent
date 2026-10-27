import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, SCRIPT_PATH, create_presentation_blueprint
from presentation_visuals import charts, profile_presentation

ROOT = Path(__file__).resolve().parents[1]


class PresentationVisualTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / 'data/personas/samuel.json').read_text())
        self.session = Presentation(Mock(conversation_id=None, connected=False, pal_id='test'))
        app = Flask(__name__)
        app.register_blueprint(create_presentation_blueprint(self.session))
        self.api = app.test_client()

    def test_recorded_chapters_have_all_workplace_scores(self):
        state = self.session.status()
        for chapter in state['chapters']:
            self.assertIn(chapter['visual'], state['visuals'])
        rows = state['visuals']['disc_sc']['rows']
        self.assertEqual([s['value'] for s in rows[1]['series']], [18, 28])
        forces = state['visuals']['forces_first']['rows'][1]['series']
        self.assertEqual(forces[0]['value'], 93)
        self.assertEqual(forces[1]['value'], 0)
        scores = [s['value'] for chart in state['visuals'].values()
                  for row in chart.get('rows', []) for s in row['series']]
        self.assertEqual(len(scores), 28)
        self.assertTrue(all(type(value) is int for value in scores))
        self.assertEqual([row['series'][0]['value'] for row in state['visuals']['eq']['rows'][-3:]], [84, 83, 84])
        self.assertEqual(state['chapters'], json.loads(SCRIPT_PATH.read_text()))

    def test_partial_sources_still_distinguish_missing_from_zero(self):
        visual = charts({'driving_forces': {'scores': {'Selfless': 0}}})
        forces = visual['forces_first']['rows'][1]['series']
        self.assertIsNone(forces[0]['value'])
        self.assertEqual(forces[1]['value'], 0)

    def test_profile_updates_script_and_charts_atomically_and_can_reset(self):
        original = copy.deepcopy(self.profile)
        response = self.api.post('/api/presentation/source', json={'profile': self.profile})
        self.assertEqual(response.status_code, 200)
        state = self.session.status()
        self.assertIn(self.profile['person']['display_name'], state['chapters'][0]['text'])
        self.assertIn('Natural Dominance score is 72.', state['chapters'][1]['text'])
        self.assertEqual(state['visuals']['disc_di']['rows'][0]['series'][0]['value'], 72)
        self.assertEqual(self.profile, original)
        self.assertEqual(state['index'], 0)
        self.assertEqual(state['revision'], 1)
        self.assertEqual(self.api.post('/api/presentation/source', json={'profile': None}).status_code, 200)
        self.assertEqual(self.session.chapters, json.loads(SCRIPT_PATH.read_text()))

    def test_bad_profiles_and_active_session_cannot_replace_source(self):
        for profile in ({}, [], {'person': 'bad'}):
            self.assertEqual(self.api.post('/api/presentation/source', json={'profile': profile}).status_code, 400)
        self.assertEqual(self.session.revision, 0)
        self.session.client.conversation_id = 'active'
        self.assertEqual(self.api.post('/api/presentation/source', json={'profile': self.profile}).status_code, 400)
        self.assertEqual(self.session.revision, 0)

    def test_all_profile_scores_are_charted_without_recalculation(self):
        chapters, visuals, source = profile_presentation(self.profile)
        self.assertEqual(sum(len(r['series']) for key, chart in visuals.items() for r in chart.get('rows', [])), 28)
        self.assertLess(sum(len(c['text'].split()) for c in chapters), 110 * 14)
        self.assertEqual(visuals['eq']['rows'][-1]['series'][0]['value'], self.profile['eq']['total_eq'])
