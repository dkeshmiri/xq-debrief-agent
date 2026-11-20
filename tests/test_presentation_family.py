import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, create_presentation_blueprint
from presentation_bundle import bundle_presentation

ROOT=Path(__file__).resolve().parents[1]

class FamilyReportPresentationTests(unittest.TestCase):
    def setUp(self):
        self.bundle=json.loads((ROOT/'content/presentations/sheila-kieren.json').read_text())

    def test_source_images_and_script_are_complete(self):
        chapters,visuals,_=bundle_presentation(self.bundle)
        self.assertEqual(len(chapters),9)
        items=[i for v in visuals.values() for i in v.get('items',[])]
        self.assertEqual(len({i['image'] for i in items}),8)
        for item in items:
            self.assertTrue((ROOT/item['image'].lstrip('/')).is_file())
            self.assertIn('page ',item['attribution'])
        self.assertIn('Indigo export',visuals['section_1']['items'][0]['attribution'])
        script=' '.join(c['text'] for c in chapters)
        self.assertNotIn('[Listen',script)
        self.assertNotIn('Agent:',script)
        self.assertIn('after the presentation',script)
        self.assertNotIn('what you have chosen',script)
        words=len(script.split())
        self.assertLess(words/110*60+60,900)
        folder=ROOT/'content/presentation_sources/sheila-kieren'
        self.assertEqual(words,json.loads((folder/'sources.json').read_text())['word_count'])
        review=(folder/'presentation-script.txt').read_text()
        for c in chapters:self.assertIn(c['text'],review)

    def test_gallery_rejects_external_and_missing_images_and_bad_types(self):
        for image in ('https://example.com/p.png','/static/presentation-assets/../secret.png',
                      '/static/presentation-assets/family/missing.png','data:image/png;base64,abc',None):
            bad=copy.deepcopy(self.bundle)
            bad['visuals']['section_1']['items'][0]['image']=image
            with self.subTest(image=image),self.assertRaises(ValueError):bundle_presentation(bad)
        bad=copy.deepcopy(self.bundle);bad['visuals']['section_1']['kind']='html'
        with self.assertRaises(ValueError):bundle_presentation(bad)

    def test_preset_uses_existing_exact_echo_and_operator_gate(self):
        provider=Mock(conversation_id=None,connected=False,pal_participant_ids=set())
        session=Presentation(provider)
        app=Flask(__name__,template_folder=str(ROOT/'templates'))
        app.register_blueprint(create_presentation_blueprint(session));api=app.test_client()
        self.assertEqual(api.post('/api/presentation/source',json={'profile':None,'preset':'sheila-kieren'}).status_code,403)
        api.post('/api/presentation/unlock',json={'pin':'2020'})
        self.assertEqual(api.post('/api/presentation/source',json={'profile':None,'preset':'sheila-kieren'}).status_code,200)
        self.assertEqual(session.status()['part_count'],1)
        self.assertIn(b'id="family-source"',api.get('/presentation').data)
        provider.conversation_id='family-test';provider.connected=True
        for i,c in enumerate(self.bundle['chapters']):
            session.play('play' if i==0 else 'next')
            provider.speak.assert_called_with(c['text'])
            for kind in ('started_speaking','stopped_speaking'):
                session.on_playback(dict(event_type='conversation.replica.'+kind,inference_id=str(i),conversation_id='family-test',properties={'interrupted':False}))
        self.assertEqual(provider.speak.call_count,9)
        self.assertTrue(session.completed)
