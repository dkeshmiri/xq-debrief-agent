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
from test_family_group import group_personas


class FamilyGroupRouteTests(unittest.TestCase):
    def setUp(self):
        self.personas = group_personas()
        self.ids = [p['person']['person_id'] for p in self.personas]
        self.repository = copy.deepcopy(app_module.repository)
        for persona in self.personas:
            pid = persona['person']['person_id']
            self.repository._personas[pid] = persona
            self.repository._members[pid] = {**persona['person'], 'debrief_enabled': True}
        self.patch = patch.object(app_module, 'repository', self.repository)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.reasoner = Mock()
        self.reasoner.answer_question.return_value = SimpleNamespace(
            response='A cautious family interpretation.', resolved_domain=ContextDomain.DISC, validation_issues=None)
        self.factory = Mock(return_value=self.reasoner)
        self.app = Flask(__name__, template_folder=str(Path('templates').resolve()))
        self.app.register_blueprint(create_family_blueprint(
            roster_snapshot=app_module.family_roster_snapshot,
            pair_snapshot=app_module.family_pair_snapshot, reasoner_factory=self.factory,
            group_snapshot=app_module.family_members_snapshot, group_reasoner_factory=self.factory))
        self.client = self.app.test_client()

    def ask(self, **extra):
        return self.client.post('/api/family/group/question', json={'person_ids': self.ids, 'question': 'Compare DISC', **extra})

    def test_group_fact_requests_preserve_live_session_and_timeout(self):
        before = (app_module.engine, app_module.orchestrator, app_module.playback_tracker,
                  app_module.answer_playback_tracker, self.repository.active_person_id,
                  app_module.voice_session_generation, app_module.orchestrator.cursor.sentence_index)
        with (patch.object(app_module, 'active_tavus_conversation_id', 'ongoing'),
              patch.object(app_module, 'question_mode_deadline', 500),
              patch.object(app_module.tavus, 'speak') as speak):
            response = self.client.post('/api/family/group/compare', json={'person_ids': self.ids})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json['comparison']['pairs']), 6)
            self.assertEqual(app_module.question_mode_deadline, 500)
            self.assertEqual(app_module.active_tavus_conversation_id, 'ongoing')
            self.assertEqual(self.ask().status_code, 200)
            self.assertEqual(app_module.question_mode_deadline, 500)
            speak.assert_not_called()
        self.assertEqual(before, (app_module.engine, app_module.orchestrator, app_module.playback_tracker,
                         app_module.answer_playback_tracker, self.repository.active_person_id,
                         app_module.voice_session_generation, app_module.orchestrator.cursor.sentence_index))

    def test_bad_selection_and_experimental_options_are_rejected(self):
        for ids, expected in [([], 400), (self.ids[:1], 400), (self.ids + ['fifth'], 400),
                              ([self.ids[0]] * 2, 400), (self.ids[:1] + ['missing'], 404)]:
            self.assertEqual(self.client.post('/api/family/group/compare', json={'person_ids': ids}).status_code, expected)
        for field in ['birth_order', 'gender_role_experiences', 'experiment_enabled', 'options']:
            self.assertEqual(self.ask(**{field: True}).status_code, 400)
        self.factory.assert_not_called()
        self.repository._members[self.ids[3]]['debrief_enabled'] = False
        self.assertEqual(self.ask().status_code, 409)

    def test_reasoner_only_receives_detached_selected_profiles(self):
        before = copy.deepcopy(self.personas)
        def answer(question, personas):
            self.assertEqual([p['person']['person_id'] for p in personas], self.ids)
            personas[0]['disc']['natural']['D'] = 0
            return SimpleNamespace(response='A cautious answer.', resolved_domain=ContextDomain.DISC, validation_issues=None)
        self.reasoner.answer_question.side_effect = answer
        self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(self.personas, before)

    def test_failures_do_not_publish_unverified_answers_or_block_retry(self):
        self.reasoner.answer_question.side_effect = RuntimeError('private service failure')
        self.assertEqual(self.ask().status_code, 503)
        self.reasoner.answer_question.side_effect = None
        self.reasoner.answer_question.return_value.validation_issues = ['Bad score']
        response = self.ask()
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('answer', response.json)
        self.reasoner.answer_question.return_value.validation_issues = None
        self.assertEqual(self.ask().status_code, 200)

    def test_pair_and_group_share_one_reasoning_slot_without_holding_playback_lock(self):
        entered, release = Event(), Event()
        result = self.reasoner.answer_question.return_value
        responses = []
        def answer(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('Test timeout')
            return result
        self.reasoner.answer_question.side_effect = answer
        worker = Thread(target=lambda: responses.append(self.app.test_client().post(
            '/api/family/group/question', json={'person_ids': self.ids, 'question': 'Compare DISC'})), daemon=True)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            acquired = app_module.playback_lock.acquire(timeout=.5)
            self.assertTrue(acquired)
            if acquired:
                app_module.playback_lock.release()
            pair = {'person_a_id': self.ids[0], 'person_b_id': self.ids[1], 'question': 'Compare EQ'}
            self.assertEqual(self.client.post('/api/family/question', json=pair).status_code, 409)
            self.assertEqual(self.ask().status_code, 409)
            self.assertEqual(app_module.app.test_client().get('/api/activity').status_code, 200)
        finally:
            release.set()
            worker.join(3)
        self.assertEqual(responses[0].status_code, 200)

    def test_old_pair_endpoint_keeps_original_response_shape(self):
        response = self.client.post('/api/family/compare', json={'person_a_id': self.ids[0], 'person_b_id': self.ids[1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json['comparison']), {'people', 'disc', 'driving_forces', 'eq'})
