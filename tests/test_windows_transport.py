"""Windows browser transport contracts; no Tavus requests or real microphone."""
import base64
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import windows_daily

ROOT = Path(__file__).resolve().parents[1]

FAKE_DAILY = r"""
window.fakeMessages = [];
window.fakeListeners = {};
window.fakeParticipants = {
  local:{session_id:'local', user_name:'backend', local:true},
  user:{session_id:'user', user_name:'XQ Family Member', local:false},
  pal:{session_id:'pal', user_name:'Avatar', local:false}
};
window.DailyIframe = {createCallObject(options) {
  window.fakeOptions = options;
  return {
    on(name, fn) { fakeListeners[name]=fn; },
    async join(args) { window.fakeJoin=args; fakeListeners['joined-meeting']({}); },
    participants() { return fakeParticipants; },
    sendAppMessage(data, to) { fakeMessages.push({data,to}); },
    updateParticipant(id, options) { window.fakeSubscription={id,options}; },
    async leave() { fakeListeners['left-meeting']({}); },
    async destroy() {}
  };
}};
"""


class WindowsDispatchTests(unittest.TestCase):
    def test_audio_is_pcm16_and_control_events_are_not_dropped(self):
        client = object.__new__(windows_daily.CallClient)
        client.handler = Mock()
        callback = Mock()
        client.renderers = {'user':callback}
        pcm = b'\x01\x00' * 320
        client._dispatch({'type':'audio','id':'user','pcm':base64.b64encode(pcm).decode()})
        self.assertEqual(callback.call_args.args[1].audio_frames, pcm)
        self.assertEqual(callback.call_args.args[1].sample_rate, 16000)
        client._dispatch({'type':'audio','id':'pal','pcm':base64.b64encode(pcm).decode()})
        callback.assert_called_once()
        client.events = queue.Queue()
        client.closed = threading.Event()
        for _ in range(201):
            client.events.put({'type':'audio'})
        client._receive(None, {'type':'audio'})
        client._receive(None, {'type':'message','data':{'event_type':'conversation.replica.stopped_speaking'}})
        self.assertEqual(client.events.qsize(), 202)
        client.closed.set()
        client._receive(None, {'type':'message'})
        self.assertEqual(client.events.qsize(), 202)

    def test_bad_audio_frame_is_rejected(self):
        client = object.__new__(windows_daily.CallClient)
        client.renderers = {'user':Mock()}
        with self.assertRaises(ValueError):
            client._dispatch({'type':'audio','id':'user','pcm':'AA=='})

    @unittest.skipUnless(os.name == 'nt', 'Windows VAD wheel')
    def test_native_vad_accepts_existing_ten_ms_segmenter_frames(self):
        scorer = windows_daily.Daily.create_native_vad(sample_rate=16000, channels=1, reset_period_ms=1000)
        self.assertEqual(scorer.analyze_frames(bytes(320)), 0.0)


@unittest.skipUnless((ROOT / 'browsers').is_dir(), 'Run Windows browser asset setup first')
class BrowserContractTests(unittest.TestCase):
    def setUp(self):
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'browsers')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        folder = Path(self.directory.name)
        (folder / 'static/vendor').mkdir(parents=True)
        (folder / 'static/vendor/daily.js').write_text(FAKE_DAILY, encoding='utf-8')
        shutil.copyfile(ROOT / 'static/windows-daily.js', folder / 'static/windows-daily.js')
        self.patch = patch.object(windows_daily, 'ROOT', folder)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.handler = Mock()
        self.client = windows_daily.CallClient(self.handler)
        self.addCleanup(self.client.release)
        self.client.join('https://test.invalid/room', meeting_token='test-token')

    def evaluate(self, expression, args=None):
        return self.client._submit(self.client._evaluate(expression, args))

    def test_join_echo_interrupt_and_participants(self):
        self.assertEqual(self.evaluate('() => fakeJoin.token'), 'test-token')
        self.assertFalse(self.evaluate('() => fakeOptions.audioSource'))
        self.assertFalse(self.evaluate('() => fakeOptions.videoSource'))
        self.assertEqual(self.client.participants()['user']['info']['userName'], 'XQ Family Member')
        echo = {'event_type':'conversation.echo','properties':{'text':'Exactly once'}}
        self.client.send_app_message(echo)
        self.client.send_app_message({'event_type':'conversation.interrupt'})
        messages = self.evaluate('() => fakeMessages')
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], {'data':echo,'to':'*'})

    def test_callback_can_call_transport_without_deadlock(self):
        finished = threading.Event()
        received = []
        def on_message(message, sender):
            received.append((message, sender, self.client.participants()))
            finished.set()
        self.handler.on_app_message.side_effect = on_message
        event = {'event_type':'conversation.replica.stopped_speaking','inference_id':'turn-1'}
        self.evaluate("data => fakeListeners['app-message']({data,fromId:'pal'})", event)
        self.assertTrue(finished.wait(5))
        self.assertEqual(received[0][:2], (event, 'pal'))

    def test_selected_remote_audio_is_received_at_16khz(self):
        received = threading.Event()
        frames = []
        self.evaluate('''async () => {
          const ctx = new AudioContext({sampleRate:48000});
          await ctx.resume();
          const oscillator = ctx.createOscillator();
          const destination = ctx.createMediaStreamDestination();
          oscillator.connect(destination); oscillator.start();
          window.testAudio = {ctx,oscillator};
          fakeParticipants.user.tracks = {audio:{persistentTrack:destination.stream.getAudioTracks()[0]}};
        }''')
        def audio(pid, data, source):
            frames.append((pid,data,source))
            received.set()
        self.client.set_audio_renderer('user', audio, audio_source='microphone', sample_rate=16000, callback_interval_ms=20)
        self.assertTrue(received.wait(8))
        self.assertEqual(len(frames[0][1].audio_frames), 640)
        self.assertEqual(frames[0][1].sample_rate, 16000)
        self.assertEqual(self.evaluate('() => fakeSubscription.options.setSubscribedTracks.video'), False)
        self.client.leave()

    def test_release_stops_thread_and_rejects_late_commands(self):
        self.client.release()
        self.assertFalse(self.client.thread.is_alive())
        with self.assertRaises(RuntimeError):
            self.client.send_app_message({'event_type':'conversation.echo'})


if __name__ == '__main__':
    unittest.main()
