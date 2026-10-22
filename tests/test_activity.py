import unittest
from threading import Event, Thread
from unittest.mock import patch
import app
from activity_presenter import describe_activity
from conversation_orchestrator import ConversationPhase

class ActivityTests(unittest.TestCase):
    def test_plain_language_tracks_observed_states(self):
        base = dict(active=True, connected=True, starting=False, ending=False,
                    reasoning=False, interrupted=False, question_ready=False,
                    pending=False, speaking=False, voice_busy=False)
        cases = [
            ({}, 'between'), ({'active': False}, 'ready'),
            ({'connected': False}, 'disconnected'),
            ({'starting': True}, 'connecting'), ({'ending': True}, 'ending'),
            ({'reasoning': True, 'pending': True}, 'reasoning'),
            ({'interrupted': True, 'speaking': True}, 'pausing'),
            ({'pending': True}, 'preparing'),
            ({'pending': True, 'speaking': True}, 'speaking'),
            ({'question_ready': True}, 'question'), ({'voice_busy': True}, 'listening'),
        ]
        for changes, expected in cases:
            with self.subTest(expected=expected):
                code, title, detail = describe_activity(**(base | changes))
                self.assertEqual(code, expected)
                self.assertTrue(title and detail)

    def test_activity_remains_available_while_reasoning_holds_playback_lock(self):
        done = Event()
        responses = []
        def read():
            responses.append(app.app.test_client().get('/api/activity'))
            done.set()
        with app.playback_lock:
            worker = Thread(target=read, daemon=True)
            worker.start()
            responsive = done.wait(2)
        worker.join(3)
        self.assertTrue(responsive, 'Activity polling blocked behind conversation reasoning')
        self.assertEqual(responses[0].status_code, 200)
        payload = responses[0].json
        self.assertEqual(set(payload), {'code', 'title', 'detail', 'active', 'connected',
                         'changing', 'pending', 'question_ready', 'phase', 'interrupted',
                         'answer_pending', 'state', 'person_id'})
        self.assertEqual(responses[0].headers['Cache-Control'], 'no-store')

    def test_reasoning_flag_is_visible_and_cleared_on_failure(self):
        def fail(question):
            self.assertTrue(app.reasoning_active.is_set())
            self.assertEqual(app.app.test_client().get('/api/activity').json['code'], 'reasoning')
            raise ValueError('Reasoning unavailable')
        with (patch.object(app.orchestrator, 'phase', ConversationPhase.QUESTION_READY),
              patch.object(app.orchestrator, 'ask_question', side_effect=fail),
              patch.object(app.tavus, 'connected', True),
              patch.object(app, 'restart_question_mode_timer')):
            with self.assertRaises(app.RouteError):
                app.answer_open_question('Example question')
        self.assertFalse(app.reasoning_active.is_set())

