import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, create_presentation_blueprint, PRESENTATION_BUDGET
from presentation_bundle import bundle_presentation

ROOT = Path(__file__).resolve().parents[1]


class InvestorPresentationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((ROOT / 'content/presentations/workforce-investor.json').read_text())
        self.session = Presentation(Mock(conversation_id=None, connected=False, pal_id='test'))
        app = Flask(__name__)
        app.register_blueprint(create_presentation_blueprint(self.session))
        self.api = app.test_client()
        self.assertEqual(self.api.post('/api/presentation/unlock', json={'pin':'2020'}).status_code, 200)

    def test_preset_and_uploaded_bundle_preserve_script_and_business_graphics(self):
        for payload in ({'profile': None, 'preset': 'workforce-investor'}, {'profile': self.bundle}):
            self.assertEqual(self.api.post('/api/presentation/source', json=payload).status_code, 200)
            self.assertEqual(self.session.chapters, self.bundle['chapters'])
            self.assertEqual(self.session.visuals, self.bundle['visuals'])
            self.assertNotIn('disc_di', self.session.visuals)
        self.assertLessEqual(self.session.status()['word_count']/110*60 + 60, PRESENTATION_BUDGET)
        script = (ROOT / 'content/presentation_sources/workforce-investor/presentation-script.txt').read_text()
        for chapter in self.session.chapters:
            self.assertIn(chapter['visual'], self.session.visuals)
            self.assertIn(chapter['text'], script)

    def test_active_presentation_cannot_change_to_investor_and_reset_is_safe(self):
        self.session.configure(None, 'workforce-investor')
        before = self.session.status()
        self.session.client.conversation_id = 'live'
        self.assertEqual(self.api.post('/api/presentation/source', json={'profile': None, 'preset': 'amethyst'}).status_code, 400)
        self.assertEqual(self.session.chapters, before['chapters'])
        self.session.client.conversation_id = None
        self.session.configure(None, 'amethyst')
        self.assertIn('aci_world', self.session.visuals)
        self.session.configure(None)
        self.assertIn('eq', self.session.visuals)

    def test_invalid_graphs_fail_atomically(self):
        before = self.session.status()
        for bad in (-1, True, '600000', float('nan'), float('inf')):
            candidate = copy.deepcopy(self.bundle)
            candidate['visuals']['roi']['items'][0]['bars'][0]['value'] = bad
            self.assertEqual(self.api.post('/api/presentation/source', json={'profile': candidate}).status_code, 400)
            self.assertEqual(self.session.status(), before)
        for field, value in [('layout','html'), ('items',[]), ('source',None), ('kind','disc')]:
            candidate = copy.deepcopy(self.bundle)
            candidate['visuals']['roi'][field] = value
            with self.assertRaises(ValueError): bundle_presentation(candidate)
        candidate = copy.deepcopy(self.bundle)
        candidate['chapters'][0]['visual'] = 'missing'
        with self.assertRaises(ValueError): bundle_presentation(candidate)

    def test_financial_examples_are_internally_consistent_and_labeled(self):
        charts = self.bundle['visuals']
        roi = charts['roi']['items'][0]['bars']
        self.assertEqual(roi[0]['value'], 49*12*1000)
        self.assertEqual(roi[1]['value'], 200*100000*.05)
        self.assertEqual(roi[2]['value'], 200*100000*.10)
        self.assertAlmostEqual((roi[1]['value']-roi[0]['value'])/roi[0]['value']*100, 70.0680272)
        self.assertAlmostEqual((roi[2]['value']-roi[0]['value'])/roi[0]['value']*100, 240.1360544)
        self.assertIn('200 roles', charts['roi']['note'])
        self.assertEqual([b['value'] for b in charts['growth']['items'][0]['bars']], [9.3,56.1,198.8])
        self.assertAlmostEqual(sum(b['value'] for b in charts['growth']['items'][0]['bars']),264.2)
        self.assertIn('growth plan', charts['growth']['note'])
        self.assertIn('subscription', charts['churn']['note'])
        self.assertIn('11.76 h', str(charts['economics']))
        self.assertEqual(49*12/50,11.76)
        self.assertEqual(49*12/75,7.84)

    def test_validated_bundle_is_not_aliased_to_upload(self):
        chapters, visuals, _ = bundle_presentation(self.bundle)
        chapters[0]['text'] = 'Changed'
        visuals['roi']['items'][0]['bars'][0]['value'] = 0
        self.assertNotEqual(chapters, self.bundle['chapters'])
        self.assertNotEqual(visuals, self.bundle['visuals'])


    def test_barometer_transition_conserves_the_workforce(self):
        charts = self.bundle['visuals']
        before, after = charts['transformation']['items']
        self.assertEqual([b['value'] for b in before['bars']], [25, 50, 25])
        self.assertEqual([b['value'] for b in after['bars']], [40, 45, 15])
        self.assertEqual([b['value'] for b in charts['barometer']['items'][0]['bars']], [25, 50, 25])
        self.assertEqual(sum(b['value'] for b in after['bars']), 100)
        self.assertEqual(after['bars'][1]['value'], before['bars'][1]['value']-15+10)
        self.assertIn('goal', after['label'])
        self.assertEqual(10000000*.094, 940000)

    def test_bad_barometers_are_rejected_without_replacing_content(self):
        before = self.session.status()
        for values in ([25,50,24], [101,0,-1], [25,True,74], [25,50,float('nan')]):
            candidate = copy.deepcopy(self.bundle)
            for bar, value in zip(candidate['visuals']['barometer']['items'][0]['bars'], values):
                bar['value'] = value
            self.assertEqual(self.api.post('/api/presentation/source', json={'profile':candidate}).status_code, 400)
            self.assertEqual(self.session.status(), before)

    def test_persuasion_sequence_covers_each_chapter_once(self):
        order = self.bundle['persuasive_structure']
        self.assertEqual(list(order), ['Attention','Interest','Conviction','Desire','Close'])
        self.assertEqual([key for stage in order.values() for key in stage],
                         [c['visual'] for c in self.bundle['chapters']])
