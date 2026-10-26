import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from local_speech import KokoroSpeech


class SpeechSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.speech = KokoroSpeech()
        self.addCleanup(self.speech.close)
        self.addCleanup(lambda: self.speech.pool.shutdown(wait=True, cancel_futures=True))
        self.speech._cache_path = lambda text: Path(self.directory.name) / (text+'.wav')
        self.entered, self.release = Event(), Event()
        self.addCleanup(self.release.set)
        self.generated = []

        def synthesize(text):
            self.generated.append(text)
            if text == 'running':
                self.entered.set()
                if not self.release.wait(2):
                    raise TimeoutError('Test did not release the synthesis worker')
            return text.encode()
        self.speech._synthesize = synthesize

    def block_worker(self):
        future = self.speech.audio('running')
        self.assertTrue(self.entered.wait(1))
        return future

    def test_disk_cache_bypasses_busy_synthesizer(self):
        self.block_worker()
        self.speech._cache_path('cached').write_bytes(b'already prepared')
        self.assertEqual(self.speech.audio('cached').result(timeout=.1), b'already prepared')
        self.assertEqual(self.generated, ['running'])

    def test_question_skips_queued_lookahead_and_cancelled_work_can_be_requested_again(self):
        self.block_worker()
        lookahead = self.speech.prefetch('later')
        question = self.speech.audio('question')
        self.assertTrue(lookahead.cancelled())
        self.release.set()
        self.assertEqual(question.result(timeout=1), b'question')
        self.assertEqual(self.generated, ['running', 'question'])
        self.assertEqual(self.speech.audio('later').result(timeout=1), b'later')

    def test_foreground_promotes_prefetch_without_cancelling_active_playback(self):
        self.block_worker()
        lookahead = self.speech.prefetch('next')
        self.assertIs(self.speech.audio('next'), lookahead)
        other = self.speech.audio('other-workspace')
        self.assertFalse(lookahead.cancelled())
        self.release.set()
        self.assertEqual(other.result(timeout=1), b'other-workspace')
        self.assertEqual(self.generated, ['running', 'next', 'other-workspace'])

    def test_stop_cancels_only_queued_speculation(self):
        active = self.block_worker()
        queued = self.speech.prefetch('unused')
        foreground = self.speech.audio('requested')
        other = self.speech.prefetch('another-unused')
        self.speech.cancel_prefetch()
        self.assertTrue(queued.cancelled())
        self.assertTrue(other.cancelled())
        self.assertFalse(active.cancelled())
        self.assertFalse(foreground.cancelled())
        self.release.set()
        self.assertEqual(foreground.result(timeout=1), b'requested')

    def test_warmup_loads_worker_even_if_greeting_is_cached(self):
        self.speech._cache_path('Welcome to XQ.').write_bytes(b'cached greeting')
        self.speech.process = Mock()
        self.speech.process.poll.return_value = None
        with patch.object(self.speech, '_request_worker', return_value={'ready': True}) as request:
            self.speech.ready()
            self.speech.ready()
        request.assert_called_once_with({'action':'warmup'})

    def test_failed_warmup_can_be_retried(self):
        self.speech.process = Mock()
        self.speech.process.poll.return_value = None
        with patch.object(self.speech, '_request_worker', side_effect=[RuntimeError('unavailable'), {'ready':True}]):
            with self.assertRaises(RuntimeError):
                self.speech.ready()
            self.speech.ready()
