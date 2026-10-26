import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, create_presentation_blueprint
from playback_event_tracker import PlaybackEventTracker


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(conversation_id=None, connected=False, pal_id='demo')
        self.now = 0
        self.session = Presentation(self.client, clock=lambda: self.now)
        def start(**kwargs):
            self.client.conversation_id = 'session'
            self.client.connected = True
            return dict(conversation_id='session', conversation_url='https://example.test', secret='hidden')
        self.client.create_conversation.side_effect = start
        self.session.start()

    def event(self, kind, inference='first', interrupted=False, conversation='session'):
        self.session.on_playback(dict(event_type=kind, inference_id=inference,
            conversation_id=conversation, properties=dict(interrupted=interrupted)))

    def finish(self, inference='first', interrupted=False):
        self.event(PlaybackEventTracker.STARTED, inference)
        self.event(PlaybackEventTracker.STOPPED, inference, interrupted)

    def test_start_budget_and_duplicate_start(self):
        self.client.create_conversation.assert_called_once_with(
            conversation_name='XQ Investor Presentation', max_call_duration=900)
        with self.assertRaises(ValueError):
            self.session.start()

    def test_chapter_requires_matching_completion(self):
        self.session.play('play')
        self.client.speak.assert_called_once_with(self.session.chapters[0]['text'])
        with self.assertRaises(ValueError):
            self.session.play('next')
        self.event(PlaybackEventTracker.STARTED, conversation='other')
        self.event(PlaybackEventTracker.STOPPED)
        self.assertFalse(self.session.completed)
        self.finish()
        self.session.play('next')
        self.assertEqual(self.session.index, 1)
        self.finish()  # Duplicate inference cannot complete the next chapter.
        self.assertFalse(self.session.completed)
        self.finish('second')
        self.assertTrue(self.session.completed)

    def test_interruption_allows_repeat_but_not_advance(self):
        self.session.play('play')
        self.finish(interrupted=True)
        with self.assertRaises(ValueError):
            self.session.play('next')
        self.session.play('repeat')
        self.assertEqual(self.session.index, 0)
        self.assertTrue(self.session.status()['pending'])

    def test_budget_blocks_new_speech(self):
        self.now = 901
        with self.assertRaises(ValueError):
            self.session.play('play')
        self.client.speak.assert_not_called()

    def test_shutdown_blocks_speech_and_records_reason(self):
        self.session.on_system(dict(conversation_id='other'))
        self.assertIsNone(self.session.shutdown_reason)
        self.session.on_system(dict(properties=dict(shutdown_reason='max_call_duration')))
        self.assertEqual(self.session.status()['shutdown_reason'], 'max_call_duration')
        with self.assertRaises(ValueError):
            self.session.play('play')

    def test_failed_delivery_is_not_blindly_retried(self):
        self.client.speak.side_effect = RuntimeError('uncertain delivery')
        with self.assertRaises(RuntimeError):
            self.session.play('play')
        with self.assertRaises(ValueError):
            self.session.play('repeat')
        self.assertEqual(self.client.speak.call_count, 1)

    def test_api_conflicts_and_status(self):
        app = Flask(__name__)
        app.register_blueprint(create_presentation_blueprint(self.session))
        api = app.test_client()
        self.assertEqual(api.post('/api/presentation/start').status_code, 409)
        self.assertEqual(api.post('/api/presentation/unknown').status_code, 404)
        response = api.get('/api/presentation/status')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(len(response.json['chapters']), 6)
        self.assertEqual(api.post('/api/presentation/play').status_code, 200)
        self.assertEqual(api.post('/api/presentation/next').status_code, 409)

    def test_end_clears_playback(self):
        self.session.play('play')
        self.session.end()
        self.client.end_conversation.assert_called_once()
        self.assertFalse(self.session.status()['pending'])
        self.assertIsNone(self.session.started_at)
