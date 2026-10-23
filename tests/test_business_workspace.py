import copy
import io
import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app as family_app
from ai_reasoner import AIReasoner
from assessment_importer import AssessmentImporter
from assessment_schema import Extraction, FamilyLanguage
from business_repository import BusinessRepository
from comparison_reasoner import ComparisonReasoner
from debrief_engine import DebriefEngine
from debrief_state import DebriefState, DEBRIEF_SEQUENCE
from family_group_reasoner import FamilyGroupReasoner
from narratives.score_wording import score_wording
from workspace_host import load_workspace
from werkzeug.middleware.dispatcher import DispatcherMiddleware

ROOT = Path(__file__).resolve().parent.parent
KIN = re.compile(r'\b(family|families|household|parenting|spouse|relatives)\b|\ba relative\b', re.I)


def business_profile(number=1):
    p = json.loads((ROOT / 'data/personas/samuel.json').read_text())
    p['experience'] = 'business'
    p['person'].update(person_id=f'business-test-{number}', first_name=f'Alex{number}',
                       display_name=f'Alex{number}', family_role='Team lead')
    p['disc'].update(behavioral_characteristics=['You may communicate directly.'], value_to_family=['You can clarify shared priorities.'],
                     communication_do=['You can ask others to agree on priorities with you.'], communication_dont=['You can ask others to avoid assuming your agreement.'])
    p['driving_forces'].update(motivational_strengths=['You may pursue useful outcomes.'], energizers=['Clear goals may energize you.'], stressors=['Unclear priorities may frustrate you.'])
    p['integrated'].update(overview='Your workplace profile can inform your communication.', strengths=['You can clarify priorities.'],
                           development_areas=['You can ask for feedback.'], family_applications=['You can discuss project handoffs.'],
                           closing_summary='You can choose one practical communication experiment.')
    return p


def language_for(p):
    return FamilyLanguage.model_validate({
        'disc': {k: p['disc'][k] for k in ('behavioral_characteristics', 'value_to_family', 'communication_do', 'communication_dont')},
        'driving_forces': {k: p['driving_forces'][k] for k in ('motivational_strengths', 'energizers', 'stressors')},
        'integrated': p['integrated']})


def extraction_for(p):
    facts = {key: copy.deepcopy(p[key]) for key in ('person', 'assessment', 'disc', 'driving_forces', 'eq')}
    facts['person'] = {k: facts['person'].get(k) for k in ('first_name', 'display_name', 'age')}
    facts['assessment'].pop('assessment_id')
    facts['disc'] = {k: facts['disc'][k] for k in ('natural', 'adapted', 'primary_style')}
    facts['driving_forces'] = {k: facts['driving_forces'][k] for k in ('scores', 'primary_cluster', 'situational_cluster', 'indifferent_cluster')}
    return Extraction.model_validate({'facts': facts, 'evidence': [], 'sections': [], 'warnings': []})


class BusinessContentTests(unittest.TestCase):
    def setUp(self):
        self.profile = business_profile()

    def test_business_narration_uses_workplace_content_and_unchanged_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            path.write_text(json.dumps(self.profile))
            engine = DebriefEngine(path, ai_reasoner=Mock(), experience='business')
            for state in DEBRIEF_SEQUENCE:
                engine.current_state = state
                text = engine.get_current_content()
                self.assertFalse(KIN.search(text), (state, KIN.search(text)))
            self.assertEqual(engine.data['disc']['natural'], self.profile['disc']['natural'])
            self.assertIn('D 72', engine.get_disc_narrative())

    def test_score_wording_uses_same_bands_and_business_applications(self):
        original = score_wording(self.profile, 'integrated')
        business = score_wording(self.profile, 'integrated', experience='business')
        for domain, scores in original.items():
            for key, value in scores.items():
                self.assertEqual((value['score'], value['band']), (business[domain][key]['score'], business[domain][key]['band']))
        self.assertFalse(KIN.search(json.dumps(business)))

    def test_all_business_library_values_exclude_household_content(self):
        def strings(v):
            if isinstance(v, dict):
                for child in v.values(): yield from strings(child)
            elif isinstance(v, list):
                for child in v: yield from strings(child)
            elif isinstance(v, str): yield v
        for path in (ROOT / 'content/business').rglob('*.json'):
            for text in strings(json.loads(path.read_text())):
                self.assertFalse(KIN.search(text), (path.name, text))

    def test_business_individual_and_group_questions_accept_coaching_topics(self):
        reasoner = AIReasoner(client=object(), experience='business')
        context = reasoner.build_context('How can I adapt my leadership communication?', DebriefState.INTRODUCTION, self.profile)
        self.assertEqual(context['route']['domain'], 'integrated')
        values = json.dumps(context)
        # Internal compatibility keys may contain family; their language values must not.
        self.assertNotIn('Within the family', values)
        pair = ComparisonReasoner(client=object(), experience='business')
        self.assertEqual(pair.resolve_comparison_domain('How can our team give feedback more effectively?').value, 'integrated')
        with self.assertRaises(ValueError):
            ComparisonReasoner(client=object()).resolve_comparison_domain('How can our team give feedback more effectively?')

    def test_single_and_group_model_requests_use_business_prompts(self):
        requests = []
        def answer(**kwargs):
            requests.append(kwargs)
            return SimpleNamespace(output_text='You can agree on the purpose of your feedback conversation.')
        client = SimpleNamespace(responses=SimpleNamespace(create=answer))
        result = AIReasoner(client=client, experience='business').answer_question('How can I give feedback?', DebriefState.INTRODUCTION, self.profile)
        self.assertIn('feedback', result.response)
        self.assertIn('workplace coaching', requests[0]['input'][0]['content'])
        self.assertNotIn('parenting and', requests[0]['input'][0]['content'])
        profiles = [business_profile(number) for number in range(1, 5)]
        ids = [p['person']['person_id'] for p in profiles]
        client.responses.create = lambda **kwargs: (requests.append(kwargs) or SimpleNamespace(output_text=json.dumps({
            'observations': [{'member_ids': ids, 'text': 'Agreeing on priorities may help the team coordinate.'}]})))
        result = FamilyGroupReasoner(client=client, experience='business').answer_question('How can our team coordinate feedback?', profiles)
        self.assertIsNone(result.validation_issues)
        self.assertIn('workplace coaching', requests[-1]['input'][0]['content'])
        self.assertNotIn('Within the family', requests[-1]['input'][1]['content'])
        self.assertEqual(len(json.loads(requests[-1]['input'][1]['content'])['context']['pairs']), 6)

    def test_business_import_preserves_facts_and_marks_scope(self):
        importer = AssessmentImporter(experience='business')
        capture = []
        def parse(contract, instructions, content):
            capture.append((instructions, content))
            return language_for(self.profile)
        importer._parse = parse
        extraction = extraction_for(self.profile)
        result = importer.generate(extraction, 'Team lead')
        self.assertTrue(result['ready_for_debrief'])
        self.assertEqual(result['persona']['experience'], 'business')
        self.assertEqual(result['persona']['disc']['natural'], self.profile['disc']['natural'])
        self.assertIn('workplace coaching', capture[0][0])
        self.assertNotIn('Write family-oriented', capture[0][0])


class BusinessApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.module = load_workspace(data_root=Path(cls.directory.name))
        cls.addClassCleanup(cls.directory.cleanup)
        cls.addClassCleanup(cls.module.background_stop.set)
        cls.addClassCleanup(cls.module.voice_pipeline.stop)

    def setUp(self):
        self.business = self.module
        self.client = self.business.app.test_client()

    def test_entry_points_render_without_business_profiles_or_family_data(self):
        for path in ('/', '/debrief', '/team', '/json-maker'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(b'data-api-base="/business"', response.data)
            self.assertIn(b'Workplace', response.data)
        self.assertEqual(self.client.get('/api/personas').json, {'personas': []})
        self.assertEqual(self.client.get('/api/family').json['members'], [])
        self.assertEqual(self.client.get('/api/status').status_code, 200)
        self.assertIn('workplace profile', self.client.get('/api/activity').json['detail'])
        self.assertNotIn('family profile', self.client.get('/api/activity').json['detail'])
        with patch.object(self.business.tavus, 'create_conversation') as create:
            self.assertEqual(self.client.post('/api/session/start').status_code, 409)
            self.assertEqual(self.client.post('/api/debrief/interrupt').status_code, 409)
            create.assert_not_called()

    def test_mounted_routes_use_separate_state_and_workspace_prefix(self):
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        host = DispatcherMiddleware(family_app.app, {'/business': self.business.app})
        client = Client(host, Response)
        for url in ('/business/', '/business/debrief', '/business/team'):
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b'Within the family', response.data)
        with patch.object(family_app, 'active_tavus_conversation_id', 'family-live'):
            self.assertFalse(client.get('/business/api/activity').json['active'])
            self.assertTrue(client.get('/api/activity').json['active'])
        self.assertIsNot(self.business.playback_lock, family_app.playback_lock)
        self.assertIsNot(self.business.orchestrator, family_app.orchestrator)
        self.assertIsNot(self.business.repository, family_app.repository)
        self.assertIsNot(self.business.voice_pipeline, family_app.voice_pipeline)

    def test_business_profile_save_select_and_narration_leave_family_roster_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = BusinessRepository(Path(directory) / 'roster.json')
            before = copy.deepcopy(family_app.repository.family_data)
            with (patch.object(self.business, 'repository', repository),
                  patch.object(self.business, 'PERSONA_DIR', Path(directory) / 'personas'),
                  patch.object(self.business, 'engine', self.business.engine),
                  patch.object(self.business, 'orchestrator', self.business.orchestrator),
                  patch.object(self.business, 'playback_tracker', self.business.playback_tracker),
                  patch.object(self.business, 'answer_playback_tracker', self.business.answer_playback_tracker)):
                filename = self.business.save_assessment_persona(business_profile())
                saved = BusinessRepository(repository.manifest_path)
                self.assertEqual(saved.get_active_persona()['experience'], 'business')
                response = self.client.post('/api/person/select', json={'file': filename})
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(self.business.engine.experience.name, 'business')
                self.assertFalse(KIN.search(self.business.engine.get_disc_narrative()))
                self.assertEqual(family_app.repository.family_data, before)

    def test_cross_workspace_profiles_and_drafts_are_rejected(self):
        family_file = family_app.get_available_personas()[0]['file']
        self.assertEqual(self.client.post('/api/person/select', json={'file': family_file}).status_code, 404)
        with self.assertRaises(ValueError):
            self.business.repository.save_persona(family_app.repository.get_default_persona(), Path(self.directory.name) / 'personas')
        with self.assertRaises(family_app.DraftConflict):
            family_app.save_assessment_persona(business_profile())
        draft = family_app.app.config.get('ASSESSMENT_DRAFT_DIR', ROOT / 'data/assessment_drafts')
        self.assertNotEqual(Path(draft), self.business.app.config['ASSESSMENT_DRAFT_DIR'])
        self.assertEqual(self.client.get('/api/assessments/00000000-0000-0000-0000-000000000000').status_code, 404)

    def test_full_business_upload_generate_publish_flow_uses_only_business_storage(self):
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        host = DispatcherMiddleware(family_app.app, {'/business': self.business.app})
        client = Client(host, Response)
        with tempfile.TemporaryDirectory() as directory:
            repository = BusinessRepository(Path(directory) / 'roster.json')
            before = copy.deepcopy(family_app.repository.family_data)
            with (patch.object(self.business, 'repository', repository),
                  patch.object(self.business, 'PERSONA_DIR', Path(directory) / 'personas'),
                  patch.object(AssessmentImporter, 'extract', return_value=extraction_for(business_profile())),
                  patch.object(AssessmentImporter, '_parse', return_value=language_for(business_profile())) as generate):
                response = client.post('/business/api/assessments/extract', data={
                    'family_role': 'Team lead', 'reports': (io.BytesIO(b'%PDF-test'), 'assessment.pdf')})
                self.assertEqual(response.status_code, 200, response.json)
                draft = response.json
                payload = {'draft_id': draft['draft_id'], 'revision': draft['revision'], 'reviewed': True}
                response = client.post('/business/api/assessments/generate', json=payload)
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(response.json['persona']['experience'], 'business')
                self.assertIn('workplace coaching', generate.call_args.args[1])
                saved = client.post('/business/api/assessments/use', json=payload)
                self.assertEqual(saved.status_code, 200, saved.json)
                self.assertEqual(saved.json['next_url'], '/business/debrief')
                self.assertTrue((Path(directory) / 'personas' / saved.json['file']).exists())
                self.assertEqual(family_app.repository.family_data, before)
                self.assertEqual(client.get(f"/api/assessments/{draft['draft_id']}").status_code, 404)

    def test_business_manual_pause_answer_and_resume_keep_family_session_untouched(self):
        from ai_reasoner import AIReasoningResult
        from conversation_orchestrator import ConversationOrchestrator
        from playback_event_tracker import PlaybackEventTracker
        with tempfile.TemporaryDirectory() as directory:
            repository = BusinessRepository(Path(directory) / 'roster.json')
            filename = repository.save_persona(business_profile(), Path(directory) / 'personas')
            engine = DebriefEngine(Path(directory) / 'personas' / filename, ai_reasoner=Mock(), experience='business')
            engine.ai_reasoner.answer_question.return_value = AIReasoningResult('Try agreeing on the next step together.', 'disc', False)
            orchestrator = ConversationOrchestrator(engine)
            with (patch.multiple(self.business, repository=repository, engine=engine, orchestrator=orchestrator,
                    playback_tracker=PlaybackEventTracker(), answer_playback_tracker=PlaybackEventTracker(),
                    active_tavus_conversation_id=None, interruption_pending=False, interrupted_inference_id=None,
                    question_mode_deadline=None, question_mode_generation=0, retired_inference_ids=set(),
                    untracked_playback_active=False, untracked_inference_id=None),
                  patch.object(self.business.tavus, 'connected', True),
                  patch.object(self.business.tavus, 'speak') as speak,
                  patch.object(self.business.tavus, 'interrupt') as interrupt,
                  patch.object(self.business.tavus, 'create_conversation', return_value={
                      'conversation_id': 'business-demo', 'conversation_url': 'https://example.invalid/room'}) as create,
                  patch.object(self.business.tavus, 'listen_to_existing_participants'),
                  patch.object(family_app, 'active_tavus_conversation_id', 'family-demo')):
                response = self.client.post('/api/session/start')
                self.assertEqual(response.status_code, 200, response.json)
                create.assert_called_once_with(conversation_name='XQ Workplace Debrief')
                self.assertEqual(self.client.post('/api/debrief/tracked/next').status_code, 200)
                index = orchestrator.cursor.sentence_index
                def event(kind, inference, interrupted=False):
                    self.business.handle_tavus_playback_event({'event_type': kind,
                        'conversation_id': 'business-demo', 'inference_id': inference,
                        'properties': {'interrupted': interrupted}})
                event(PlaybackEventTracker.STARTED, 'business-narration')
                self.assertEqual(self.client.post('/api/debrief/interrupt').status_code, 200)
                interrupt.assert_called_once()
                event(PlaybackEventTracker.STOPPED, 'business-narration', True)
                self.assertTrue(self.client.get('/api/activity').json['question_ready'])
                self.assertGreater(self.business.question_mode_seconds_left(), 0)
                self.assertEqual(self.business.QUESTION_MODE_TIMEOUT_SECONDS, family_app.QUESTION_MODE_TIMEOUT_SECONDS)
                response = self.client.post('/api/question', json={'question': 'How might my DISC preferences affect feedback?'})
                self.assertEqual(response.status_code, 200, response.json)
                event(PlaybackEventTracker.STARTED, 'business-answer')
                event(PlaybackEventTracker.STOPPED, 'business-answer')
                self.assertEqual(orchestrator.phase.value, 'narrating')
                self.assertEqual(orchestrator.cursor.sentence_index, index)
                self.assertTrue(speak.call_args.args[0].startswith('To continue where we left off...'))
                self.assertEqual(family_app.active_tavus_conversation_id, 'family-demo')

    def test_workspace_call_clients_initialize_shared_native_sdk_once(self):
        import tavus_client
        sdk = Mock()
        with (patch.object(tavus_client, 'Daily', sdk),
              patch.object(tavus_client, 'CallClient'),
              patch.object(tavus_client.TavusClient, '_daily_sdk', None)):
            first, second = tavus_client.TavusClient(), tavus_client.TavusClient()
            first.connect('https://example.invalid/first', 'first')
            second.connect('https://example.invalid/second', 'second')
            sdk.init.assert_called_once()
            self.assertIsNot(first.call_client, None)
            self.assertIsNot(second.call_client, None)
