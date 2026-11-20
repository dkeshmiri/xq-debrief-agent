import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation,create_presentation_blueprint
from presentation_bundle import bundle_presentation

ROOT=Path(__file__).resolve().parents[1]

class KevinPresentationTests(unittest.TestCase):
    def setUp(self):
        self.bundle=json.loads((ROOT/'content/presentations/kevin.json').read_text())

    def test_scripts_sources_and_two_session_budget_match(self):
        chapters,visuals,_=bundle_presentation(self.bundle)
        self.assertEqual(len(chapters),16)
        self.assertEqual([(p['chapter_start'],p['chapter_end']) for p in self.bundle['parts']],[(0,6),(7,15)])
        folder=ROOT/'content/presentation_sources/kevin'
        metadata=json.loads((folder/'sources.json').read_text())
        for i,p in enumerate(self.bundle['parts']):
            subset=chapters[p['chapter_start']:p['chapter_end']+1]
            words=sum(len(c['text'].split()) for c in subset)
            self.assertEqual(words,metadata['parts'][i]['word_count'])
            self.assertLess(words/110*60+60,900)
            for c in subset:self.assertIn(c['text'],(folder/f'part-{i+1}-script.txt').read_text())
        for v in visuals.values():
            self.assertEqual(v['kind'],'report_gallery')
            for item in v['items']:self.assertTrue((ROOT/item['image'].lstrip('/')).is_file())
        self.assertEqual({a['page'] for a in metadata['assets']},{25,28,38,59,52,54,58})
        self.assertEqual(len(list(folder.glob('*-*.raw.txt'))),8) # seven chunks plus combined acumen-12df

    def test_inherited_pattern_passages_are_preserved_and_specific_errors_corrected(self):
        text=' '.join(c['text'] for c in self.bundle['chapters'])
        for passage in ['five generations','32 different variables','great-great-grandfather',
                        'epigenetic background','parents, grandparents, great-grandparents',
                        "separate yourself from what you've inherited"]:self.assertIn(passage,text)
        self.assertIn('Graph One is Adapted, and Graph Two is Natural',text)
        self.assertIn('an increase of four points',text)
        self.assertNotIn('30% increase',text)
        self.assertNotIn('let me rephrase',text)
        self.assertNotIn('point of concern',text)

    def test_operator_preset_and_exact_echo_across_fresh_session(self):
        from test_presentation_parts import Provider
        provider=Provider();s=Presentation(provider);app=Flask(__name__,template_folder=str(ROOT/'templates'))
        app.register_blueprint(create_presentation_blueprint(s));api=app.test_client()
        self.assertEqual(api.post('/api/presentation/source',json={'profile':None,'preset':'kevin'}).status_code,403)
        api.post('/api/presentation/unlock',json={'pin':'2020'})
        self.assertEqual(api.post('/api/presentation/source',json={'profile':None,'preset':'kevin'}).status_code,200)
        self.assertIn(b'id="kevin-source"',api.get('/presentation').data)
        s.start();first_id=provider.conversation_id
        for i,c in enumerate(self.bundle['chapters']):
            if i==7:
                self.assertEqual(api.post('/api/presentation/next-part',json={'session_id':first_id}).status_code,200)
                self.assertNotEqual(first_id,provider.conversation_id)
                self.assertEqual(api.post('/api/presentation/next-part',json={'session_id':first_id}).status_code,409)
            s.play('play' if i in (0,7) else 'next')
            self.assertEqual(provider.calls[-1],('speak',c['text']))
            for kind in ('started_speaking','stopped_speaking'):
                s.on_playback(dict(event_type='conversation.replica.'+kind,inference_id=str(i),conversation_id=provider.conversation_id,properties={'interrupted':False}))
        self.assertEqual(provider.counter,2)
        self.assertEqual(len([c for c in provider.calls if c[0]=='speak']),16)
        self.assertTrue(s.completed)
