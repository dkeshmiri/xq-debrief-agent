import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
from flask import Flask
from local_playback import LocalPlayback, local_playback_blueprint


class LocalPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.future = Future()
        synth = Mock()
        synth.audio.return_value = self.future
        self.player = LocalPlayback(synth)
        self.events = []
        self.player.on_playback_event = self.events.append
        self.session = self.player.create_conversation()['conversation_id']
        app = Flask(__name__)
        app.register_blueprint(local_playback_blueprint(self.player))
        self.api = app.test_client()

    def command(self):
        return self.player.command(self.session, -1)

    def test_synthesis_does_not_complete_playback(self):
        self.player.speak('Hello.')
        self.assertNotIn('ready', self.command())
        self.future.set_result(b'RIFF-audio')
        command = self.command()
        self.assertTrue(command['ready'])
        self.assertEqual(self.events, [])
        with self.assertRaises(ValueError):
            self.player.acknowledge(self.session, command['id'], 'ended')
        self.player.acknowledge(self.session, command['id'], 'started')
        self.player.acknowledge(self.session, command['id'], 'ended')
        self.assertEqual(len(self.events), 2)
        self.assertFalse(self.events[-1]['properties']['interrupted'])
        with self.assertRaises(ValueError):
            self.player.acknowledge(self.session, command['id'], 'ended')

    def test_interrupt_requires_browser_stop_and_does_not_complete(self):
        self.player.speak('Hello.')
        self.future.set_result(b'RIFF-audio')
        utterance = self.command()['id']
        self.player.acknowledge(self.session, utterance, 'started')
        self.player.interrupt()
        self.assertEqual(len(self.events), 1)
        self.player.acknowledge(self.session, utterance, 'interrupted')
        self.assertTrue(self.events[-1]['properties']['interrupted'])

    def test_natural_end_racing_pause_preserves_interruption(self):
        self.player.speak('Hello.')
        self.future.set_result(b'audio')
        utterance = self.command()['id']
        self.player.acknowledge(self.session, utterance, 'started')
        self.player.interrupt()
        self.player.acknowledge(self.session, utterance, 'ended')
        self.assertTrue(self.events[-1]['properties']['interrupted'])

    def test_old_session_and_old_audio_are_rejected(self):
        self.player.speak('Hello.')
        old = self.command()['id']
        self.player.end_conversation()
        self.future.set_result(b'old audio')
        self.player.create_conversation()
        with self.assertRaises(ValueError):
            self.player.command(self.session, -1)
        with self.assertRaises(ValueError):
            self.player.acknowledge(self.session, old, 'started')
        self.assertIsNone(self.player.pending)

    def test_failure_is_visible_without_false_completion(self):
        self.player.speak('Hello.')
        self.future.set_exception(RuntimeError('model failed'))
        self.assertIn('error', self.command())
        self.assertEqual(self.events, [])

    def test_audio_route_is_scoped_and_uncached(self):
        self.player.speak('Hello.')
        self.future.set_result(b'RIFF-audio')
        url = '/api/local/audio/'+self.command()['id']
        self.assertEqual(self.api.get(url+'?session=wrong').status_code, 409)
        response = self.api.get(url+'?session='+self.session)
        self.assertEqual(response.data, b'RIFF-audio')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_page_warmup_is_nonblocking_and_does_not_submit_speech(self):
        response = self.api.post('/api/local/warmup')
        self.assertEqual(response.status_code, 200)
        self.player.speech.warmup.assert_called_once_with()
        self.player.speech.audio.assert_not_called()
        self.assertIsNone(self.player.pending)

    def test_next_speech_can_be_queued_from_completion_callback(self):
        self.player.speak('First.')
        self.future.set_result(b'audio')
        utterance = self.command()['id']
        self.player.acknowledge(self.session, utterance, 'started')
        self.player.on_playback_event = lambda _: self.player.speak('Second.')
        self.player.acknowledge(self.session, utterance, 'ended')
        self.assertEqual(self.command()['text'], 'Second.')


class LocalConversationIntegrationTests(unittest.TestCase):
    def test_conclusion_questions_and_restart_in_both_products(self):
        from workspace_host import load_workspace
        from debrief_state import DebriefState
        for experience, wording in [('family', 'family'), ('business', 'workplace')]:
            with self.subTest(experience=experience), patch.dict('os.environ', {'XQ_PLAYBACK_PROVIDER': 'kokoro'}):
                module = load_workspace(experience)
                self.addCleanup(module.background_stop.set)
                self.addCleanup(module.voice_pipeline.stop)
                future = Future()
                future.set_result(b'test audio')
                module.tavus.speech = Mock()
                module.tavus.speech.audio.return_value = future
                api = module.app.test_client()
                start = api.post('/api/session/start')
                self.assertEqual(start.status_code, 200)
                session = start.json['conversation']['conversation_id']
                module.engine.current_state = DebriefState.INTEGRATED_NARRATIVE
                self.assertEqual(api.post('/api/debrief/next').status_code, 200)
                spoken = []
                while module.playback_tracker.utterance_id is not None:
                    command = module.tavus.command(session, -1)
                    spoken.append(command['text'])
                    module.tavus.acknowledge(session, command['id'], 'started')
                    module.tavus.acknowledge(session, command['id'], 'ended')
                conclusion = ' '.join(spoken)
                self.assertIn(f'{wording} insights', conclusion)
                self.assertIn(module.engine.display_name, conclusion)
                self.assertIn('Restart the debrief', conclusion)
                self.assertIn('Ask your guide', conclusion)
                self.assertTrue(module.tavus.connected)
                self.assertEqual(module.engine.current_state, DebriefState.COMPLETE)
                # Repeated questions after the final sentence must not replay it.
                for _ in range(2):
                    self.assertEqual(api.post('/api/debrief/interrupt').status_code, 200)
                    self.assertTrue(api.get('/api/activity').json['question_ready'])
                    with patch.object(module.engine, 'answer_question', return_value='An answer.'):
                        self.assertEqual(api.post('/api/question', json={'question': 'What next?'}).status_code, 200)
                    command = module.tavus.command(session, -1)
                    module.tavus.acknowledge(session, command['id'], 'started')
                    module.tavus.acknowledge(session, command['id'], 'ended')
                    self.assertIsNone(module.playback_tracker.utterance_id)
                    self.assertEqual(module.engine.current_state, DebriefState.COMPLETE)
                self.assertEqual(api.post('/api/debrief/restart').status_code, 200)
                self.assertEqual(module.engine.current_state, DebriefState.INTRODUCTION)
                self.assertIsNotNone(module.playback_tracker.utterance_id)
                self.assertEqual(api.post('/api/session/end').status_code, 200)

    def test_question_answer_and_resume_keep_local_playback_ownership(self):
        from workspace_host import load_workspace
        with patch.dict('os.environ', {'XQ_PLAYBACK_PROVIDER':'kokoro'}):
            module = load_workspace('family')
        self.addCleanup(module.background_stop.set)
        self.addCleanup(module.voice_pipeline.stop)
        future = Future()
        future.set_result(b'test audio')
        module.tavus.speech = Mock()
        module.tavus.speech.audio.return_value = future
        api = module.app.test_client()
        start = api.post('/api/session/start')
        self.assertEqual(start.status_code, 200)
        session = start.json['conversation']['conversation_id']
        self.assertEqual(api.post('/api/debrief/speak').status_code, 200)
        self.assertEqual(api.post('/api/debrief/repeat').status_code, 409)
        first = module.tavus.command(session, -1)['id']
        module.tavus.acknowledge(session, first, 'started')
        self.assertEqual(api.post('/api/debrief/interrupt').status_code, 200)
        module.tavus.acknowledge(session, first, 'interrupted')
        self.assertTrue(api.get('/api/activity').json['question_ready'])
        with patch.object(module.engine, 'answer_question', return_value='An assessment-grounded answer.'):
            answer = api.post('/api/question', json={'question':'What does this mean?'})
        self.assertEqual(answer.status_code, 200)
        command = module.tavus.command(session, -1)
        self.assertEqual(command['text'], 'An assessment-grounded answer.')
        module.tavus.acknowledge(session, command['id'], 'started')
        module.tavus.acknowledge(session, command['id'], 'ended')
        resumed = module.tavus.command(session, -1)
        self.assertIn('To continue where we left off', resumed['text'])
        self.assertFalse(api.get('/api/activity').json['question_ready'])
        self.assertEqual(api.post('/api/session/end').status_code, 200)
        self.assertFalse(module.tavus.connected)
