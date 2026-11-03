import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, create_presentation_blueprint

ROOT = Path(__file__).resolve().parents[1]


class LegacyPitchTests(unittest.TestCase):
    def setUp(self):
        self.provider = Mock(conversation_id=None, connected=False, pal_id='test')
        self.session = Presentation(self.provider)
        app = Flask(__name__)
        app.register_blueprint(create_presentation_blueprint(self.session))
        self.api = app.test_client()
        self.api.post('/api/presentation/unlock', json={'pin':'2020'})

    def test_both_editions_preserve_script_and_share_chapter_structure(self):
        keys = []
        for name, language in [('iranian-american','en'),('iranian-american-fa','fa')]:
            bundle = json.loads((ROOT/f'content/presentations/{name}.json').read_text())
            for payload in ({'profile':None,'preset':name},{'profile':bundle}):
                self.assertEqual(self.api.post('/api/presentation/source',json=payload).status_code,200)
                self.assertEqual(self.session.chapters,bundle['chapters'])
                self.assertEqual(self.session.visuals,bundle['visuals'])
                self.assertEqual(self.session.status()['language'],language)
            keys.append([c['visual'] for c in self.session.chapters])
            self.assertEqual([v for stage in bundle['persuasive_structure'].values() for v in stage],keys[-1])
            script = (ROOT/f'content/presentation_sources/{name}/presentation-script.txt').read_text()
            for chapter in self.session.chapters:
                self.assertIn(chapter['text'],script)
            self.assertEqual(len(self.session.chapters),15)
        self.assertEqual(keys[0],keys[1])

    def test_persian_start_is_rejected_without_provider_call_or_state_change(self):
        self.session.configure(None,'iranian-american-fa')
        before = self.session.status()
        self.assertFalse(before['narration_supported'])
        self.assertEqual(self.api.post('/api/presentation/start').status_code,409)
        self.provider.create_conversation.assert_not_called()
        self.assertEqual(before,self.session.status())
        self.session.configure(None,'iranian-american')
        self.assertTrue(self.session.status()['narration_supported'])
        self.provider.create_conversation.return_value={'conversation_id':'test'}
        self.assertEqual(self.api.post('/api/presentation/start').status_code,200)
        self.provider.create_conversation.assert_called_once()

    def test_language_reset_and_invalid_upload_are_atomic(self):
        self.session.configure(None,'iranian-american-fa')
        before = self.session.status()
        bundle = json.loads((ROOT/'content/presentations/iranian-american-fa.json').read_text())
        for language in ('ar','<script>',None,{},['fa']):
            bad = copy.deepcopy(bundle)
            bad['language'] = language
            self.assertEqual(self.api.post('/api/presentation/source',json={'profile':bad}).status_code,400)
            self.assertEqual(before,self.session.status())
        for preset in ('amethyst','workforce-investor',None):
            self.session.configure(None,'iranian-american-fa')
            self.session.configure(None,preset)
            self.assertEqual(self.session.status()['language'],'en')
            self.assertTrue(self.session.status()['narration_supported'])

    def test_new_sources_stay_locked_during_active_session(self):
        before = self.session.status()
        self.provider.conversation_id = 'live'
        for name in ('iranian-american','iranian-american-fa'):
            self.assertEqual(self.api.post('/api/presentation/source',json={'profile':None,'preset':name}).status_code,400)
        self.assertEqual(self.session.chapters,before['chapters'])

    def test_english_pitch_fits_session_and_echo_keeps_exact_text(self):
        self.session.configure(None,'iranian-american')
        self.assertLess(self.session.status()['word_count']/110*60+60,900)
        self.provider.conversation_id = 'live'
        self.provider.connected = True
        self.session.play('play')
        self.provider.speak.assert_called_once_with(self.session.chapters[0]['text'])
        with self.assertRaises(ValueError):
            self.session.play('play')
        self.assertEqual(self.provider.speak.call_count,1)


    def test_full_deck_coverage_and_aicdc_order(self):
        for name in ('iranian-american','iranian-american-fa'):
            bundle = json.loads((ROOT/f'content/presentations/{name}.json').read_text())
            source = json.loads((ROOT/f'content/presentation_sources/{name}/sources.json').read_text())
            pages = [source['chapter_source_pages'][c['visual']][0] for c in bundle['chapters']]
            self.assertEqual(sorted(pages), list(range(1,16)))
            self.assertEqual(pages[-3:], [15,13,14])
            self.assertEqual(list(bundle['persuasive_structure']), ['Attention','Interest','Conviction','Desire','Close'])
            self.assertIn('evidence', bundle['persuasive_structure']['Conviction'])
            self.assertEqual(bundle['persuasive_structure']['Desire'], ['solution'])
            self.assertEqual(bundle['persuasive_structure']['Close'], ['close'])
        self.session.configure(None,'iranian-american')
        self.assertGreaterEqual(self.session.status()['word_count'], 1400)
