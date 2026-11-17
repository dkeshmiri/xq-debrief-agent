import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from flask import Flask
from playback_event_tracker import PlaybackEventTracker
from presentation import Presentation, create_presentation_blueprint, PRESENTATION_BUDGET
from presentation_bundle import bundle_presentation

ROOT = Path(__file__).resolve().parents[1]


class MarioPresentationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((ROOT / 'content/presentations/mario.json').read_text())
        self.provider = Mock(conversation_id=None, connected=False, pal_id='test')
        self.session = Presentation(self.provider)
        app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        app.register_blueprint(create_presentation_blueprint(self.session))
        self.api = app.test_client()
        self.api.post('/api/presentation/unlock', json={'pin': '2020'})

    def test_mario_selection_loads_own_script_and_scores_atomically(self):
        response = self.api.post('/api/presentation/source', json={'profile': None, 'preset': 'mario'})
        self.assertEqual(response.status_code, 200)
        state = self.session.status()
        self.assertEqual(state['chapters'], self.bundle['chapters'])
        self.assertIn('Mario', state['source'])
        self.assertNotIn('eq', state['visuals'])
        self.assertEqual([s['value'] for s in state['visuals']['disc_di']['profiles'][0]['scores']], [56, 72, 36, 42])
        self.assertEqual([s['value'] for s in state['visuals']['disc_di']['profiles'][1]['scores']], [58, 64, 45, 45])
        self.assertEqual(state['part_count'],2)
        self.assertIn(b'id="mario-source"', self.api.get('/presentation').data)
        self.api.post('/api/presentation/source', json={'profile': None})
        self.assertIn('eq', self.session.visuals)
        self.assertNotIn('forces_priorities', self.session.visuals)
        self.provider.create_conversation.assert_not_called()

    def test_people_and_action_uses_original_report_wheel(self):
        chapters, visuals, _ = bundle_presentation(self.bundle)
        chapter = next(c for c in chapters if c['title'] == 'DISC · People and action')
        self.assertEqual(chapter['visual'], 'disc_wheel')
        wheel = visuals['disc_wheel']
        self.assertEqual(wheel['legend'], ['● Natural · 14 · Persuading Promoter',
                                          '★ Adapted · 13 · Promoting Persuader'])
        self.assertTrue((ROOT / wheel['image'].lstrip('/')).is_file())
        bad = copy.deepcopy(self.bundle)
        bad['profile']['disc']['wheel'] = 'https://example.com/arbitrary.png'
        with self.assertRaises(ValueError):
            bundle_presentation(bad)

    def test_force_ranks_do_not_turn_into_scores(self):
        _, visuals, _ = bundle_presentation(self.bundle)
        priorities = visuals['forces_priorities']
        self.assertEqual(priorities['kind'], 'force_ranks')
        self.assertEqual([(item['label'], item['rank']) for item in priorities['items'][:5]], [
            ('Receptive', 1), ('Intellectual', 2), ('Resourceful', 3), ('Intentional', 4), ('Harmonious', 5)])
        self.assertEqual([item['color'] for item in priorities['items'][:5]],
                         ['methodologies', 'knowledge', 'utility', 'others', 'surroundings'])
        self.assertEqual(len(priorities['items']),12)
        self.assertEqual(self.bundle['profile']['driving_forces']['scores'], dict(
            Intellectual=79,Instinctive=11,Resourceful=65,Selfless=12,Harmonious=51,Objective=25,
            Intentional=65,Altruistic=21,Collaborative=46,Commanding=33,Receptive=90,Structured=0))

    def test_aci_uses_report_values_and_preserves_valuation_arrows(self):
        _, visuals, _ = bundle_presentation(self.bundle)
        panels = visuals['aci_balance']['panels']
        dimensions = [dimension for panel in panels for dimension in panel['dimensions']]
        self.assertEqual([d['clarity'] for d in dimensions], [96, 92, 92, 78, 80, 70])
        self.assertEqual([d['bias'] for d in dimensions], ['mixed', 'mixed', 'over', 'under', 'mixed', 'over'])
        self.assertEqual([p['emotional_bias_distortion'] for p in panels], [7, 24])
        self.assertEqual([d['blind_spot'] for d in dimensions],[4,8,8,22,20,30])
        self.assertEqual([p['clarity_average'] for p in panels],[93,76])
        self.assertEqual([[p['value'] for p in panel['problems']] for panel in panels],
                         [[100,100,82,96],[80,100,78,86]])
        self.assertEqual([[p['reference'] for p in panel['problems']] for panel in panels],
                         [[86,82,81,79],[77,75,75,66]])

    def test_script_review_copy_and_timing_metadata_match_active_bundle(self):
        folder = ROOT / 'content/presentation_sources/mario'
        script = (folder / 'presentation-script.txt').read_text()
        metadata = json.loads((folder / 'sources.json').read_text())
        words = sum(len(c['text'].split()) for c in self.bundle['chapters'])
        self.assertEqual(words, metadata['presentation_word_count'])
        for part in self.bundle['parts']:
            part_words = sum(len(c['text'].split()) for c in self.bundle['chapters'][part['chapter_start']:part['chapter_end']+1])
            self.assertGreater(part_words,1400)
            self.assertLessEqual(part_words / 110 * 60 + 60, PRESENTATION_BUDGET)
        for chapter in self.bundle['chapters']:
            self.assertIn(chapter['text'], script)
        for record in metadata['recordings']:
            for chunk in record['chunks']:
                self.assertTrue((folder / f'{chunk["id"]}.raw.txt').exists())
            self.assertEqual(record['chunks'][0]['start_seconds'], 0)
            self.assertEqual(record['chunks'][-1]['end_seconds'], record['duration_seconds'])
        self.assertIn('82 against a report reference of 70', script)
        self.assertIn('James Bond', script)
        self.assertNotIn('not a diagnostic', script.lower())
        self.assertNotIn('for coaching purposes only', script.lower())

    def test_every_chapter_uses_exact_script_through_existing_echo_path(self):
        self.session.configure(None, 'mario')
        self.provider.conversation_id = 'mario-test'
        self.provider.connected = True
        def create(**kwargs):
            self.provider.conversation_id = 'mario-part-2'
            return {'conversation_id':'mario-part-2','conversation_url':'https://test.invalid'}
        self.provider.create_conversation.side_effect = create
        for index, chapter in enumerate(self.bundle['chapters']):
            boundary = index == self.bundle['parts'][1]['chapter_start']
            if boundary:
                self.session.next_part('mario-test')
            self.session.play('play' if index == 0 or boundary else 'next')
            self.provider.speak.assert_called_with(chapter['text'])
            for event_type in (PlaybackEventTracker.STARTED, PlaybackEventTracker.STOPPED):
                self.session.on_playback({'event_type': event_type, 'inference_id': f'mario-{index}',
                                          'conversation_id': self.provider.conversation_id, 'properties': {'interrupted': False}})
        self.assertEqual(self.provider.speak.call_count, len(self.bundle['chapters']))

    def test_invalid_ranks_and_live_source_changes_cannot_replace_the_script(self):
        self.session.configure(None, 'mario')
        before = self.session.status()
        for ranks in (None, [], {'Unknown': 1}, {'Receptive': 0}, {'Receptive': 13},
                      {'Receptive': True}, {'Receptive': 1.0}, {'Receptive': '1'},
                      {'Receptive': 1, 'Intellectual': 1}):
            bad = copy.deepcopy(self.bundle)
            bad['profile']['driving_forces']['ranks'] = ranks
            with self.subTest(ranks=ranks):
                self.assertEqual(self.api.post('/api/presentation/source', json={'profile': bad}).status_code, 400)
                self.assertEqual(self.session.status(), before)
        self.provider.conversation_id = 'live'
        self.assertEqual(self.api.post('/api/presentation/source', json={'profile': None, 'preset': 'mario'}).status_code, 400)
        self.assertEqual(self.session.chapters, before['chapters'])

    def test_uploaded_bundle_preserves_narration_and_requires_operator_access(self):
        client = self.api.application.test_client()
        self.assertEqual(client.post('/api/presentation/source', json={'profile': None, 'preset': 'mario'}).status_code, 403)
        original = copy.deepcopy(self.bundle)
        self.assertEqual(self.api.post('/api/presentation/source', json={'profile': self.bundle}).status_code, 200)
        self.assertEqual(self.session.chapters, original['chapters'])
        self.assertEqual(self.bundle, original)


if __name__ == '__main__':
    unittest.main()
