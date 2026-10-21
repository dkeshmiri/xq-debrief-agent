import unittest
from unittest.mock import MagicMock, patch

import app
from conversation_orchestrator import ConversationOrchestrator, ConversationPhase
from debrief_state import DebriefState
from playback_event_tracker import PlaybackEventTracker


class TestFlaskAnswerLifecycle(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock()
        self.engine.get_current_state.return_value = DebriefState.DISC_NARRATIVE
        self.engine.get_current_content.return_value = 'First sentence. Second sentence.'
        self.engine.answer_question.return_value = 'An approved answer.'
        self.orchestrator = ConversationOrchestrator(self.engine)
        self.orchestrator.load_current_section()
        values = dict(engine=self.engine, orchestrator=self.orchestrator,
                      playback_tracker=PlaybackEventTracker(),
                      answer_playback_tracker=PlaybackEventTracker(),
                      interruption_pending=False, interrupted_inference_id=None,
                      untracked_playback_active=False, active_tavus_conversation_id='session',
                      retired_inference_ids=set(), untracked_inference_id=None,
                      session_ending=False)
        for name, value in values.items():
            item = patch.object(app, name, value, create=True)
            item.start()
            self.addCleanup(item.stop)
        for name, value in [('connected', True), ('speak', MagicMock()),
                            ('interrupt', MagicMock()), ('end_conversation', MagicMock()),
                            ('disconnect', MagicMock())]:
            item = patch.object(app.tavus, name, value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(app, 'current_payload', return_value={})
        item.start()
        self.addCleanup(item.stop)
        self.client = app.app.test_client()

    def event(self, kind, inference, **properties):
        app.handle_tavus_playback_event(dict(event_type=kind, inference_id=inference,
                                           properties=properties))

    def pause(self):
        with app.playback_lock:
            app.submit_next_tracked_sentence()
        self.event(PlaybackEventTracker.STARTED, 'old-narration')
        self.assertEqual(self.client.post('/api/debrief/interrupt').status_code, 200)
        self.event(PlaybackEventTracker.STOPPED, 'old-narration', interrupted=True)

    def ask(self):
        return self.client.post('/api/question', json={'question': 'What does this mean?'})

    def test_answer_waits_for_matching_completion_then_replays_sentence(self):
        self.pause()
        self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(self.orchestrator.phase, ConversationPhase.ANSWERING)
        self.assertIsNotNone(app.answer_playback_tracker.utterance_id)
        self.engine.exit_question_mode.assert_not_called()
        self.event(PlaybackEventTracker.STARTED, 'old-narration')
        self.event(PlaybackEventTracker.STOPPED, 'old-narration', interrupted=False)
        self.assertIsNone(app.answer_playback_tracker.inference_id)
        self.event(PlaybackEventTracker.STOPPED, 'answer', interrupted=False)
        self.assertEqual(self.orchestrator.phase, ConversationPhase.ANSWERING)
        self.event('conversation.pal.started_speaking', 'alias')
        self.assertIsNone(app.answer_playback_tracker.inference_id)
        self.event(PlaybackEventTracker.STARTED, 'answer')
        self.event(PlaybackEventTracker.STOPPED, 'wrong', interrupted=False)
        self.assertEqual(self.orchestrator.phase, ConversationPhase.ANSWERING)
        self.event(PlaybackEventTracker.STOPPED, 'answer', interrupted=False)
        self.assertEqual(self.orchestrator.phase, ConversationPhase.NARRATING)
        self.assertEqual(self.orchestrator.cursor.sentence_index, 0)
        self.assertIsNone(app.answer_playback_tracker.utterance_id)
        app.tavus.speak.assert_called_with('To continue where we left off... First sentence.')
        self.event(PlaybackEventTracker.STARTED, 'answer')
        self.event(PlaybackEventTracker.STOPPED, 'answer', interrupted=False)
        self.assertIsNone(app.playback_tracker.inference_id)
        self.assertEqual(app.tavus.speak.call_count, 3)
        self.event(PlaybackEventTracker.STARTED, 'resumed')
        self.event(PlaybackEventTracker.STOPPED, 'resumed', interrupted=False)
        self.assertEqual(self.orchestrator.cursor.sentence_index, 1)
        app.tavus.speak.assert_called_with('Second sentence.')

    def test_answer_start_ignores_missing_ids_and_other_sessions(self):
        self.pause()
        self.ask()
        self.event(PlaybackEventTracker.STARTED, None)
        app.handle_tavus_playback_event(dict(event_type=PlaybackEventTracker.STARTED,
                                           inference_id='foreign', conversation_id='old-session'))
        self.assertIsNone(app.answer_playback_tracker.inference_id)
        self.event(PlaybackEventTracker.STARTED, 'answer')
        self.assertEqual(app.answer_playback_tracker.inference_id, 'answer')

    def test_all_echo_routes_block_before_answer_start(self):
        self.pause()
        self.assertEqual(self.ask().status_code, 200)
        count = app.tavus.speak.call_count
        for route in ['/api/question', '/api/debrief/next', '/api/debrief/speak',
                      '/api/debrief/repeat', '/api/debrief/restart',
                      '/api/debrief/tracked/next', '/api/debrief/sentence/test',
                      '/api/dev/disc-narrative', '/api/dev/driving-forces-narrative',
                      '/api/dev/eq-narrative', '/api/dev/integrated-narrative']:
            with self.subTest(route=route):
                self.assertEqual(self.client.post(route, json={'question': 'Again?'}).status_code, 409)
        self.assertEqual(app.tavus.speak.call_count, count)
        self.engine.reset.assert_not_called()
        self.engine.advance.assert_not_called()

    def test_reasoning_failure_can_retry(self):
        self.pause()
        self.engine.answer_question.side_effect = RuntimeError('reasoning failed')
        self.assertEqual(self.ask().status_code, 500)
        self.assertEqual(self.orchestrator.phase, ConversationPhase.QUESTION_READY)
        self.assertIsNone(app.answer_playback_tracker.utterance_id)
        self.engine.answer_question.side_effect = None
        self.assertEqual(self.ask().status_code, 200)

    def test_uncertain_send_keeps_ownership(self):
        self.pause()
        app.tavus.speak.side_effect = RuntimeError('delivery uncertain')
        self.assertEqual(self.ask().status_code, 500)
        self.assertIsNotNone(app.answer_playback_tracker.utterance_id)
        self.assertEqual(self.ask().status_code, 409)

    def test_interrupted_answer_never_resumes(self):
        self.pause()
        self.ask()
        self.event(PlaybackEventTracker.STARTED, 'answer')
        self.event(PlaybackEventTracker.STOPPED, 'answer', interrupted=True)
        self.assertEqual(self.orchestrator.phase, ConversationPhase.NARRATING)
        self.assertEqual(app.tavus.speak.call_count, 2)
        self.assertEqual(self.ask().status_code, 409)

    def test_shutdown_failure_preserves_answer_then_success_clears(self):
        self.pause()
        self.ask()
        self.event(PlaybackEventTracker.STARTED, 'answer')
        app.tavus.end_conversation.side_effect = RuntimeError('shutdown failed')
        self.assertEqual(self.client.post('/api/session/end').status_code, 500)
        self.assertEqual(app.answer_playback_tracker.inference_id, 'answer')
        app.tavus.end_conversation.side_effect = None
        self.assertEqual(self.client.post('/api/session/end').status_code, 200)
        self.assertIsNone(app.answer_playback_tracker.utterance_id)
        self.assertIsNone(app.answer_playback_tracker.inference_id)
        self.assertIsNone(app.playback_tracker.utterance_id)

    def test_persona_active_session_rejected_without_reset(self):
        app.answer_playback_tracker.arm(1)
        response = self.client.post('/api/person/select', json={'file': 'any.json'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(app.answer_playback_tracker.utterance_id, 1)

    def test_persona_success_resets_answer_but_failure_preserves(self):
        app.active_tavus_conversation_id = None
        app.answer_playback_tracker.arm(1)
        with (patch.object(app, 'get_available_personas', return_value=[dict(file='test.json', person_id='test')]),
              patch.object(app.repository, 'set_active_person'),
              patch.object(app, 'create_engine_for_active_person', return_value=self.engine)):
            self.assertEqual(self.client.post('/api/person/select', json={'file': 'missing'}).status_code, 404)
            self.assertEqual(app.answer_playback_tracker.utterance_id, 1)
            self.engine.display_name = 'Test'
            self.assertEqual(self.client.post('/api/person/select', json={'file': 'test.json'}).status_code, 200)
        self.assertIsNone(app.answer_playback_tracker.utterance_id)

    def test_untracked_echo_reserved_before_start_and_wrong_stop_ignored(self):
        self.assertEqual(self.client.post('/api/debrief/speak').status_code, 200)
        self.assertEqual(self.client.post('/api/debrief/repeat').status_code, 409)
        self.event(PlaybackEventTracker.STOPPED, 'unrelated', interrupted=False)
        self.assertTrue(app.untracked_playback_active)
        self.event(PlaybackEventTracker.STARTED, 'untracked')
        self.event(PlaybackEventTracker.STOPPED, 'untracked', interrupted=False)
        self.assertFalse(app.untracked_playback_active)

    def test_shutdown_does_not_hold_callback_lock(self):
        from threading import Thread
        def shutdown():
            worker = Thread(target=lambda: self.event(PlaybackEventTracker.STARTED, 'late'))
            worker.start()
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(self.client.post('/api/debrief/speak').status_code, 409)
        app.tavus.end_conversation.side_effect = shutdown
        self.assertEqual(self.client.post('/api/session/end').status_code, 200)
