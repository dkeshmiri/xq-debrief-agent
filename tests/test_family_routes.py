import copy
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask

import app as app_module
from context_router import ContextDomain
from family_routes import create_family_blueprint


class FamilyRouteTests(unittest.TestCase):
    def setUp(self):
        self.members = app_module.repository.list_members(debrief_enabled_only=True)
        self.ids = [person['person_id'] for person in self.members[:2]]
        self.selection = dict(zip(('person_a_id', 'person_b_id'), self.ids))
        self.personas = [copy.deepcopy(app_module.repository.get_persona(i)) for i in self.ids]
        self.reasoner = Mock()
        self.reasoner.answer_question.return_value = SimpleNamespace(
            response='These preferences may lead to different pacing.',
            resolved_domain=ContextDomain.DISC, validation_issues=None)
        self.factory = Mock(return_value=self.reasoner)
        self.app = Flask(__name__, template_folder=str(Path('templates').resolve()))
        self.app.register_blueprint(create_family_blueprint(
            roster_snapshot=app_module.family_roster_snapshot,
            pair_snapshot=app_module.family_pair_snapshot,
            reasoner_factory=self.factory))
        self.client = self.app.test_client()

    def test_family_page_and_roster_do_not_expose_persona_paths(self):
        self.assertEqual(self.client.get('/family').status_code, 200)
        response = self.client.get('/api/family')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        for member in response.json['members']:
            self.assertEqual(set(member), {'person_id', 'display_name', 'family_role'})
        self.factory.assert_not_called()

    def test_comparison_returns_exact_facts_without_model_or_session_changes(self):
        app = app_module
        before = (app.repository.active_person_id, app.engine, app.orchestrator,
                  app.playback_tracker, app.answer_playback_tracker,
                  app.orchestrator.cursor.sentence_index, app.voice_session_generation)
        with (patch.object(app, 'active_tavus_conversation_id', 'active-demo'),
              patch.object(app, 'question_mode_deadline', 123.0),
              patch.object(app.tavus, 'interrupt') as interrupt,
              patch.object(app.tavus, 'speak') as speak):
            response = self.client.post('/api/family/compare', json=self.selection)
            self.assertEqual(response.status_code, 200, response.json)
            data = response.json['comparison']
            self.assertEqual(data['disc']['natural']['D']['person_a'], self.personas[0]['disc']['natural']['D'])
            self.assertEqual(data['disc']['natural']['D']['person_b'], self.personas[1]['disc']['natural']['D'])
            self.assertEqual(app.question_mode_deadline, 123.0)
            self.assertEqual(app.active_tavus_conversation_id, 'active-demo')
            interrupt.assert_not_called()
            speak.assert_not_called()
        self.assertEqual(before, (app.repository.active_person_id, app.engine, app.orchestrator,
                         app.playback_tracker, app.answer_playback_tracker,
                         app.orchestrator.cursor.sentence_index, app.voice_session_generation))
        self.factory.assert_not_called()

    def test_invalid_selection_and_question_are_rejected_before_reasoning(self):
        cases = [(None, 400), ([], 400), ({}, 400),
                 ({**self.selection, 'person_a_id': []}, 400),
                 ({**self.selection, 'person_b_id': self.ids[0]}, 400),
                 ({**self.selection, 'person_b_id': 'missing'}, 404)]
        for body, status in cases:
            with self.subTest(body=body):
                response = self.client.post('/api/family/compare', json=body)
                self.assertEqual(response.status_code, status)
        for question in ['', '   ', [], 'x' * 2001]:
            response = self.client.post('/api/family/question', json={**self.selection, 'question': question})
            self.assertEqual(response.status_code, 400)
        self.factory.assert_not_called()

    def test_disabled_members_are_not_listed_or_comparable(self):
        repository = copy.deepcopy(app_module.repository)
        repository._members[self.ids[1]]['debrief_enabled'] = False
        with patch.object(app_module, 'repository', repository):
            roster = self.client.get('/api/family').json
            self.assertNotIn(self.ids[1], [member['person_id'] for member in roster['members']])
            self.assertEqual(self.client.post('/api/family/compare', json=self.selection).status_code, 409)

    def test_reasoning_receives_detached_profiles_and_cannot_mutate_repository(self):
        def answer(question, a, b):
            self.assertEqual(question, 'How do our DISC preferences differ?')
            a['disc']['natural']['D'] = 0
            b['person']['display_name'] = 'Changed in request'
            return SimpleNamespace(response='A cautious comparison.', resolved_domain=ContextDomain.DISC, validation_issues=None)
        self.reasoner.answer_question.side_effect = answer
        response = self.client.post('/api/family/question', json={**self.selection, 'question': 'How do our DISC preferences differ?'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['domain'], 'disc')
        for person_id, original in zip(self.ids, self.personas):
            self.assertEqual(app_module.repository.get_persona(person_id), original)

    def test_unsupported_domain_does_not_call_model(self):
        self.reasoner.resolve_comparison_domain.side_effect = ValueError('Mention DISC, Driving Forces, or EQ.')
        response = self.client.post('/api/family/question', json={**self.selection, 'question': 'What about us?'})
        self.assertEqual(response.status_code, 400)
        self.reasoner.answer_question.assert_not_called()

    def test_rejected_generated_response_is_not_published_as_an_answer(self):
        self.reasoner.answer_question.return_value.validation_issues = ['Unsupported assertion']
        response = self.client.post('/api/family/question', json={**self.selection, 'question': 'Compare DISC'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('answer', response.json)

    def test_service_failure_keeps_facts_available_and_releases_reasoning_slot(self):
        self.reasoner.answer_question.side_effect = RuntimeError('private upstream details')
        response = self.client.post('/api/family/question', json={**self.selection, 'question': 'Compare DISC'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private upstream details', response.json['error'])
        self.assertEqual(self.client.post('/api/family/compare', json=self.selection).status_code, 200)
        self.reasoner.answer_question.side_effect = None
        self.assertEqual(self.client.post('/api/family/question', json={**self.selection, 'question': 'Compare DISC'}).status_code, 200)

    def test_family_reasoning_does_not_hold_playback_lock_and_rejects_overlap(self):
        entered, release = Event(), Event()
        results = []
        original = self.reasoner.answer_question.return_value
        def answer(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('Test timed out')
            return original
        self.reasoner.answer_question.side_effect = answer
        def ask():
            results.append(self.app.test_client().post('/api/family/question', json={**self.selection, 'question': 'Compare DISC'}))
        worker = Thread(target=ask, daemon=True)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            acquired = app_module.playback_lock.acquire(timeout=.5)
            self.assertTrue(acquired, 'Family reasoning blocked the playback lock')
            if acquired:
                app_module.playback_lock.release()
            self.assertEqual(app_module.app.test_client().get('/api/activity').status_code, 200)
            self.assertEqual(self.client.post('/api/family/question', json={**self.selection, 'question': 'Compare EQ'}).status_code, 409)
            self.assertEqual(self.client.post('/api/family/compare', json=self.selection).status_code, 200)
        finally:
            release.set()
            worker.join(3)
        self.assertEqual(results[0].status_code, 200)
