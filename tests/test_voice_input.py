"""
Voice input tests.

Run from the project folder:

    python -m unittest discover -s tests -v

The app-level tests replace Daily, the persona engine and
the family repository with in-memory fakes, so they need
neither Tavus, OpenAI, nor persona data. Nothing leaves
the machine.
"""

import io
import importlib.util
from unittest.mock import patch
import os
import struct
import sys
import threading
import time
import types
import unittest
import uuid
import wave
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))



# =========================================================
# AUDIO HELPERS
# =========================================================

SAMPLE_RATE = 16_000


def pcm(milliseconds: int, amplitude: int) -> bytes:
    """Square-ish 16-bit PCM: loud = speech, 0 = silence."""

    samples = SAMPLE_RATE * milliseconds // 1000

    return b"".join(
        struct.pack(
            "<h",
            amplitude if index % 2 == 0 else -amplitude,
        )
        for index in range(samples)
    )


SPEECH = 4000
SILENCE = 0


# =========================================================
# FAKES
# =========================================================

class FakeTranscriptions:
    def __init__(self) -> None:
        self.text = ""
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(text=self.text)


class FakeOpenAI:
    def __init__(self) -> None:
        self.audio = types.SimpleNamespace(
            transcriptions=FakeTranscriptions()
        )


class FakeAudioData:
    def __init__(self, frames: bytes) -> None:
        self.audio_frames = frames
        self.sample_rate = SAMPLE_RATE
        self.num_channels = 1
        self.bits_per_sample = 16
        self.num_audio_frames = len(frames) // 2


class FakeCallClient:
    def __init__(self, event_handler=None) -> None:
        self.event_handler = event_handler
        self.sent = []
        self.renderers = {}
        self.remote_participants = {}

    def join(self, url) -> None:
        pass

    def leave(self) -> None:
        pass

    def release(self) -> None:
        pass

    def send_app_message(self, message) -> None:
        self.sent.append(message)

    def set_audio_renderer(self, participant_id, callback, **kwargs) -> None:
        self.renderers[participant_id] = callback

    def participants(self):
        return {
            "local": {"id": "backend", "info": {"isLocal": True}},
            **self.remote_participants,
        }


def install_daily_stub() -> None:
    daily = types.ModuleType("daily")

    class EventHandler:
        def __init__(self) -> None:
            pass

    class Daily:
        @staticmethod
        def init() -> None:
            pass

        @staticmethod
        def create_native_vad(**kwargs):
            raise AssertionError(
                "Tests use XQ_VAD_BACKEND=energy."
            )

    daily.EventHandler = EventHandler
    daily.Daily = Daily
    daily.CallClient = FakeCallClient
    sys.modules["daily"] = daily


SENTENCES = (
    "Your DISC profile shows a strong D. "
    "You move quickly toward results. "
    "Others may need more time."
)


def install_engine_stubs() -> None:
    from debrief_state import DebriefState, InteractionMode

    engine_module = types.ModuleType("debrief_engine")

    class FakeEngine:
        def __init__(self, persona_file) -> None:
            self.display_name = "Test Parent"
            self.current_state = DebriefState.DISC_NARRATIVE
            self.interaction_mode = InteractionMode.DEBRIEF
            self.paused_state = None
            self.questions = []

        def get_current_state(self):
            return self.current_state

        def get_current_content(self) -> str:
            return SENTENCES

        def get_interaction_mode(self):
            return self.interaction_mode

        def enter_question_mode(self) -> None:
            self.paused_state = self.current_state
            self.interaction_mode = InteractionMode.QUESTION

        def exit_question_mode(self) -> None:
            if self.paused_state is not None:
                self.current_state = self.paused_state
            self.paused_state = None
            self.interaction_mode = InteractionMode.DEBRIEF

        def answer_question(self, question: str) -> str:
            self.questions.append(question)
            return "A strong D often means you like to decide quickly."

        def advance(self):
            return self.current_state

        def reset(self) -> None:
            pass

    engine_module.DebriefEngine = FakeEngine
    sys.modules["debrief_engine"] = engine_module

    repository_module = types.ModuleType("family_repository")

    class FakeRepository:
        def __init__(self, path) -> None:
            self.active_person_id = "parent"

        def get_active_member(self):
            return {
                "person_id": "parent",
                "display_name": "Test Parent",
                "family_role": "Parent",
                "persona_file": "unused.json",
            }

        def set_active_person(self, person_id) -> None:
            self.active_person_id = person_id

    repository_module.FamilyRepository = FakeRepository
    sys.modules["family_repository"] = repository_module


def wait_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)

    return False


# =========================================================
# UNIT TESTS
# =========================================================

class VoiceIntentTests(unittest.TestCase):
    def classify(self, text):
        from voice_intent import classify_question_mode_utterance
        return classify_question_mode_utterance(text)

    def test_dismissals(self):
        from voice_intent import VoiceIntent

        for text in (
            "Never mind.",
            "nevermind",
            "My mistake!",
            "Oh, sorry, my bad.",
            "Continue.",
            "Please continue",
            "Okay, you can continue.",
            "Can you continue?",
            "No, never mind, keep going.",
            "Go ahead",
            "Sorry, I didn't mean to interrupt.",
            "It's nothing. Carry on.",
            "No question, thanks.",
            "Forget about it",
            "Um, false alarm",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    self.classify(text).intent,
                    VoiceIntent.DISMISS,
                )

    def test_questions(self):
        from voice_intent import VoiceIntent

        for text in (
            "What does a high D mean?",
            "Never mind, what about my EQ?",
            "Sorry, can you explain Driving Forces?",
            "Continue with the part about my kids",
            "Why is my adapted style different?",
            "Nothing about my scores makes sense",
            "Can you go on about my EQ?",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    self.classify(text).intent,
                    VoiceIntent.QUESTION,
                )

    def test_empty(self):
        from voice_intent import VoiceIntent

        for text in (
            "",
            "Um...",
            "Wait.",
            "Hold on, I have a question",
            "Thank you.",
            "Excuse me",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    self.classify(text).intent,
                    VoiceIntent.EMPTY,
                )

    def test_question_text_is_preserved(self):
        result = self.classify("  What does my EQ mean?  ")
        self.assertEqual(result.text, "What does my EQ mean?")


class SegmenterTests(unittest.TestCase):
    def run_frames(self, pattern):
        from voice_activity import (
            EnergySpeechScorer,
            UtteranceSegmenter,
        )

        segmenter = UtteranceSegmenter()
        scorer = EnergySpeechScorer()
        events = []

        for milliseconds, amplitude in pattern:
            audio = pcm(milliseconds, amplitude)

            for offset in range(0, len(audio), 320):
                frame = audio[offset:offset + 320]
                events.extend(
                    segmenter.process(frame, scorer(frame))
                )

        return events

    def test_speech_produces_start_then_utterance(self):
        from voice_activity import SegmentEventType

        events = self.run_frames([
            (500, SILENCE),
            (600, SPEECH),
            (1000, SILENCE),
        ])

        self.assertEqual(
            [event.event_type for event in events],
            [
                SegmentEventType.SPEECH_STARTED,
                SegmentEventType.UTTERANCE_ENDED,
            ],
        )

        # 300 ms pre-roll + 40 ms of silence still in the start
        # window + 600 ms speech + 700 ms closing silence.
        self.assertEqual(events[1].duration_ms, 1640)
        self.assertEqual(len(events[1].audio), 1640 * 32)

    def test_short_noise_is_ignored(self):
        events = self.run_frames([
            (300, SILENCE),
            (80, SPEECH),
            (1000, SILENCE),
        ])

        self.assertEqual(events, [])

    def test_long_speech_is_capped(self):
        from voice_activity import (
            EnergySpeechScorer,
            SegmenterConfig,
            SegmentEventType,
            UtteranceSegmenter,
        )

        segmenter = UtteranceSegmenter(
            SegmenterConfig(max_utterance_ms=1000)
        )
        scorer = EnergySpeechScorer()
        audio = pcm(2000, SPEECH)
        events = []

        for offset in range(0, len(audio), 320):
            frame = audio[offset:offset + 320]
            events.extend(segmenter.process(frame, scorer(frame)))

        ended = [
            event
            for event in events
            if event.event_type == SegmentEventType.UTTERANCE_ENDED
        ]

        # Continuous speech is cut into capped chunks.
        self.assertEqual(
            [event.duration_ms for event in ended],
            [1000, 1000],
        )


class TranscriberTests(unittest.TestCase):
    def test_pcm_is_sent_as_wav(self):
        from speech_transcriber import SpeechTranscriber

        client = FakeOpenAI()
        client.audio.transcriptions.text = "  What is my EQ?  "

        transcriber = SpeechTranscriber(
            client=client,
            model="test-model",
        )

        text = transcriber.transcribe_pcm16(
            pcm(500, SPEECH),
            SAMPLE_RATE,
        )

        self.assertEqual(text, "What is my EQ?")

        call = client.audio.transcriptions.calls[0]
        filename, payload = call["file"]

        self.assertEqual(call["model"], "test-model")
        self.assertEqual(filename, "utterance.wav")

        with wave.open(io.BytesIO(payload)) as wav_file:
            self.assertEqual(wav_file.getframerate(), SAMPLE_RATE)
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)

    def test_empty_audio_is_rejected(self):
        from speech_transcriber import SpeechTranscriber

        transcriber = SpeechTranscriber(client=FakeOpenAI())

        with self.assertRaises(ValueError):
            transcriber.transcribe_pcm16(b"", SAMPLE_RATE)


class PipelineTests(unittest.TestCase):
    def test_live_audio_produces_start_and_transcript(self):
        from speech_transcriber import SpeechTranscriber
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline

        client = FakeOpenAI()
        client.audio.transcriptions.text = "Never mind"

        received = []

        pipeline = VoiceInputPipeline(
            transcriber=SpeechTranscriber(client=client),
            on_speech_started=lambda pid: received.append(("start", pid)),
            on_transcript=lambda pid, text: received.append(("text", pid, text)),
            scorer_factory=EnergySpeechScorer,
        )
        pipeline.start()

        try:
            # Daily delivers 20 ms chunks.
            for milliseconds, amplitude in (
                (200, SILENCE),
                (600, SPEECH),
                (1000, SILENCE),
            ):
                audio = pcm(milliseconds, amplitude)

                for offset in range(0, len(audio), 640):
                    pipeline.feed_audio(
                        "user-1",
                        audio[offset:offset + 640],
                        SAMPLE_RATE,
                    )

            self.assertTrue(
                wait_until(lambda: len(received) == 2)
            )

        finally:
            pipeline.stop()

        self.assertEqual(
            received,
            [
                ("start", "user-1"),
                ("text", "user-1", "Never mind"),
            ],
        )

    def test_reset_or_departure_discards_in_flight_transcript(self):
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline

        for action in ("reset", "drop"):
            with self.subTest(action=action):
                entered = threading.Event()
                release = threading.Event()
                delivered = []

                def transcribe(*args):
                    entered.set()
                    release.wait(2)
                    return "Old question"

                transcriber = types.SimpleNamespace(transcribe_pcm16=transcribe)
                pipeline = VoiceInputPipeline(
                    transcriber=transcriber,
                    on_speech_started=lambda pid: True,
                    on_transcript=lambda *args: delivered.append(args),
                    scorer_factory=EnergySpeechScorer,
                )
                pipeline.start()
                try:
                    pipeline.feed_audio("user", pcm(600, SPEECH) + pcm(1000, SILENCE), SAMPLE_RATE)
                    self.assertTrue(entered.wait(1))
                    if action == "reset":
                        pipeline.reset()
                    else:
                        pipeline.drop_participant("user")
                    self.assertFalse(pipeline.busy())
                    # Reusing the same participant ID must not revive old work.
                    pipeline.feed_audio("user", pcm(20, SILENCE), SAMPLE_RATE)
                    release.set()
                finally:
                    release.set()
                    pipeline.stop()
                self.assertEqual(delivered, [])

    def test_ignored_speech_does_not_call_transcriber(self):
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline
        from unittest.mock import Mock

        transcriber = Mock()
        pipeline = VoiceInputPipeline(
            transcriber=transcriber,
            on_speech_started=lambda pid: False,
            on_transcript=lambda *args: self.fail("Ignored speech was delivered"),
            scorer_factory=EnergySpeechScorer,
        )
        pipeline.start()
        try:
            pipeline.feed_audio("user", pcm(600, SPEECH) + pcm(1000, SILENCE), SAMPLE_RATE)
            self.assertTrue(wait_until(lambda: not pipeline.busy()))
            transcriber.transcribe_pcm16.assert_not_called()
        finally:
            pipeline.stop()

    def test_reset_discards_queued_speech_start(self):
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline
        from unittest.mock import Mock

        started = Mock()
        pipeline = VoiceInputPipeline(
            transcriber=Mock(), on_speech_started=started,
            on_transcript=Mock(), scorer_factory=EnergySpeechScorer,
        )
        pipeline.feed_audio("user", pcm(600, SPEECH) + pcm(1000, SILENCE), SAMPLE_RATE)
        pipeline.reset()
        pipeline.start()
        pipeline.stop()
        started.assert_not_called()

    def test_muted_stream_finishes_without_more_audio_frames(self):
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline
        from unittest.mock import Mock

        received = []
        pipeline = VoiceInputPipeline(
            transcriber=Mock(transcribe_pcm16=Mock(return_value="Never mind")),
            on_speech_started=lambda pid: True,
            on_transcript=lambda *args: received.append(args),
            scorer_factory=EnergySpeechScorer,
        )
        pipeline.feed_audio("user", pcm(600, SPEECH), SAMPLE_RATE)
        with patch("voice_input.time.monotonic", return_value=time.monotonic() + 2):
            self.assertTrue(pipeline.busy())
        pipeline.start()
        try:
            self.assertTrue(wait_until(lambda: received))
            self.assertEqual(received, [("user", "Never mind")])
            self.assertFalse(pipeline.busy())
        finally:
            pipeline.stop()

    def test_transcript_cannot_answer_a_replacement_question(self):
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline
        from unittest.mock import Mock

        context = [1]
        delivered = Mock()

        def transcribe(*args):
            context[0] = 2
            return "Old question"

        pipeline = VoiceInputPipeline(
            transcriber=types.SimpleNamespace(transcribe_pcm16=transcribe),
            on_speech_started=lambda pid: True,
            on_transcript=delivered,
            scorer_factory=EnergySpeechScorer,
            get_question_context=lambda: context[0],
        )
        pipeline.start()
        try:
            pipeline.feed_audio("user", pcm(600, SPEECH) + pcm(1000, SILENCE), SAMPLE_RATE)
            self.assertTrue(wait_until(lambda: not pipeline.busy()))
            delivered.assert_not_called()
        finally:
            pipeline.stop()

    def test_wrong_sample_rate_fails_loudly(self):
        from speech_transcriber import SpeechTranscriber
        from voice_activity import EnergySpeechScorer
        from voice_input import VoiceInputPipeline

        pipeline = VoiceInputPipeline(
            transcriber=SpeechTranscriber(client=FakeOpenAI()),
            on_speech_started=lambda pid: None,
            on_transcript=lambda pid, text: None,
            scorer_factory=EnergySpeechScorer,
        )

        with self.assertRaises(ValueError):
            pipeline.feed_audio("user-1", pcm(20, SPEECH), 48_000)


# =========================================================
# APP INTEGRATION TESTS
# =========================================================

class AppVoiceFlowTests(unittest.TestCase):
    """
    Drives app.py the way Tavus and the user's
    microphone would, with in-memory fakes.
    """

    @classmethod
    def setUpClass(cls):
        # Load a private app so discovery order cannot swap the real engine
        # into these fake-service tests or contaminate the original suite.
        with patch.dict(sys.modules), patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key-not-used",
            "XQ_VAD_BACKEND": "energy",
            "XQ_QUESTION_TIMEOUT_SECONDS": "30",
            "XQ_PLAYBACK_PROVIDER": "tavus",
        }):
            install_daily_stub()
            install_engine_stubs()
            spec = importlib.util.spec_from_file_location("voice_test_app", PROJECT_DIR / "app.py")
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)
            cls.handler_class = sys.modules["tavus_client"].TavusEventHandler

        from voice_activity import EnergySpeechScorer
        app_module.voice_pipeline.scorer_factory = EnergySpeechScorer
        app_module.tavus.voice_user_name = "Parent"
        cls.app_module = app_module
        cls.openai = FakeOpenAI()
        app_module.speech_transcriber.client = cls.openai
        cls.addClassCleanup(app_module.voice_pipeline.stop)
        cls.addClassCleanup(app_module.background_stop.set)

    def setUp(self):
        app = self.app_module

        # Fresh conversation state for every test.
        with app.playback_lock:
            app.active_tavus_conversation_id = None

        app.tavus.disconnect()

        with app.playback_lock:
            app.engine = app.create_engine_for_active_person()
            app.orchestrator = app.ConversationOrchestrator(app.engine)
            app.playback_tracker = app.PlaybackEventTracker()
            app.answer_playback_tracker = app.PlaybackEventTracker()
            app.interruption_pending = False
            app.interrupted_inference_id = None
            app.untracked_playback_active = False
            app.untracked_inference_id = None
            app.failure_recovery.reset()
            app.question_mode_deadline = None
            app.reset_voice_state()

        self.call_client = FakeCallClient()
        app.tavus.call_client = self.call_client
        app.tavus.conversation_id = "conv-1"
        app.tavus.connected = True
        app.active_tavus_conversation_id = "conv-1"

        self.handler = self.handler_class(app.tavus)
        self.http = app.app.test_client()

        # app.py retires inference IDs for the whole process,
        # so every test needs its own.
        self.inference_prefix = uuid.uuid4().hex[:8]

        # The PAL announces itself; the user joins.
        self.handler.on_app_message(
            {"message_type": "system", "event_type": "system.replica_joined"},
            "pal-1",
        )
        self.handler.on_participant_joined(
            {"id": "pal-1", "info": {"userName": "XQ PAL", "isLocal": False}}
        )
        self.handler.on_participant_joined(
            {"id": "user-1", "info": {"userName": "Parent", "isLocal": False}}
        )

    def test_upload_keeps_question_open_during_slow_transcription(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()

        def transcribe(*args):
            with app.playback_lock:
                self.assertIsNone(app.check_question_mode_timeout(time.monotonic() + 60))
                self.assertEqual(self.phase(), "question_ready")
            return "What is my EQ?"

        with patch.object(app.speech_transcriber, "transcribe_file", side_effect=transcribe):
            response = self.http.post("/api/voice/audio", data=b"audio", content_type="audio/wav")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertFalse(app.http_voice_pending)

    def test_upload_from_previous_session_is_rejected(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()

        def transcribe(*args):
            # Simulate shutdown and a fresh session while STT is out of lock.
            with app.playback_lock:
                app.reset_voice_state()
            return "What is my EQ?"

        with patch.object(app.speech_transcriber, "transcribe_file", side_effect=transcribe):
            response = self.http.post("/api/voice/audio", data=b"audio", content_type="audio/wav")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(app.engine.questions, [])

    def test_upload_cannot_answer_a_later_question(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()

        def transcribe(*args):
            with app.playback_lock:
                app.dismiss_open_question()
            self.started("resumed")
            self.http.post("/api/debrief/interrupt")
            self.stopped("resumed", interrupted=True)
            return "What is my EQ?"

        with patch.object(app.speech_transcriber, "transcribe_file", side_effect=transcribe):
            response = self.http.post("/api/voice/audio", data=b"audio", content_type="audio/wav")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(app.engine.questions, [])

    def test_upload_failure_restarts_inactivity_timeout(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()
        with patch.object(app.speech_transcriber, "transcribe_file", side_effect=RuntimeError("offline")):
            response = self.http.post("/api/voice/audio", data=b"audio", content_type="audio/wav")
        self.assertEqual(response.status_code, 502)
        self.assertFalse(app.http_voice_pending)
        self.assertGreater(app.question_mode_seconds_left(), 29)

    def test_concurrent_upload_is_rejected(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()
        app.http_voice_pending = True
        response = self.http.post("/api/voice/audio", data=b"audio", content_type="audio/wav")
        self.assertEqual(response.status_code, 409)

    def test_upload_size_limit_is_enforced_before_interrupt(self):
        with patch.dict(self.app_module.app.config, MAX_CONTENT_LENGTH=4):
            response = self.http.post("/api/voice/audio", data=b"12345", content_type="audio/wav")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.interrupts(), [])

    def test_typed_filler_skips_reasoner_and_restarts_timer(self):
        self.start_narration()
        self.open_question_mode()
        self.app_module.question_mode_deadline = time.monotonic() + 1
        response = self.http.post("/api/question", json={"question": "Um, wait"})
        self.assertTrue(response.get_json()["still_listening"])
        self.assertEqual(self.app_module.engine.questions, [])
        self.assertGreater(self.app_module.question_mode_seconds_left(), 29)

    def test_reasoning_failure_restarts_timer_after_completion(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()

        def fail(question):
            app.question_mode_deadline = time.monotonic() - 10
            raise RuntimeError("offline")

        with patch.object(app.engine, "answer_question", side_effect=fail):
            response = self.http.post("/api/question", json={"question": "What is EQ?"})
        self.assertEqual(response.status_code, 500)
        self.assertGreater(app.question_mode_seconds_left(), 29)

    def test_unknown_participant_is_ignored_before_pal_announcement(self):
        self.handler.on_participant_joined({"id": "unknown", "info": {"userName": "PAL"}})
        self.assertNotIn("unknown", self.call_client.renderers)

    # ----------------------------------------------- helpers

    def echoes(self):
        return [
            message["properties"]["text"]
            for message in self.call_client.sent
            if message["event_type"] == "conversation.echo"
        ]

    def interrupts(self):
        return [
            message
            for message in self.call_client.sent
            if message["event_type"] == "conversation.interrupt"
        ]

    def tavus_event(self, event_type, inference_id, interrupted=None):
        message = {
            "message_type": "conversation",
            "event_type": event_type,
            "conversation_id": "conv-1",
            "inference_id": f"{self.inference_prefix}-{inference_id}",
            "properties": {"role": "pal"},
        }

        if interrupted is not None:
            message["properties"]["interrupted"] = interrupted

        self.handler.on_app_message(message, "pal-1")

    def started(self, inference_id):
        self.tavus_event(
            "conversation.replica.started_speaking",
            inference_id,
        )

    def stopped(self, inference_id, interrupted):
        self.tavus_event(
            "conversation.replica.stopped_speaking",
            inference_id,
            interrupted,
        )

    def speak_into_room(self, participant_id="user-1", speech_ms=600):
        renderer = self.call_client.renderers[participant_id]

        for milliseconds, amplitude in (
            (200, SILENCE),
            (speech_ms, SPEECH),
            (1000, SILENCE),
        ):
            audio = pcm(milliseconds, amplitude)

            for offset in range(0, len(audio), 640):
                renderer(
                    participant_id,
                    FakeAudioData(audio[offset:offset + 640]),
                    "microphone",
                )

    def start_narration(self):
        response = self.http.post("/api/debrief/tracked/next")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.started("narration-1")

    def phase(self):
        return self.app_module.orchestrator.phase.value

    def wait_for_voice(self, action):
        self.assertTrue(
            wait_until(
                lambda: (self.app_module.last_voice_event or {}).get("action")
                == action
            ),
            f"Voice action {action!r} not reached; "
            f"last={self.app_module.last_voice_event}",
        )

    def voice_interrupt_then_confirm(self, transcript):
        self.openai.audio.transcriptions.text = transcript
        self.start_narration()

        self.speak_into_room()

        # 1a: speech onset sends a Tavus interrupt.
        self.assertTrue(wait_until(lambda: len(self.interrupts()) == 1))
        self.assertTrue(self.app_module.interruption_pending)

        # Tavus confirms the stop -> question mode opens.
        self.stopped("narration-1", interrupted=True)
        self.assertEqual(self.phase(), "question_ready")
        self.assertEqual(
            self.app_module.engine.get_interaction_mode().value,
            "question",
        )

    def open_question_mode(self, narration="narration-1"):
        response = self.http.post("/api/debrief/interrupt")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.stopped(narration, interrupted=True)
        self.assertEqual(self.phase(), "question_ready")

    def ask_typed_question(self):
        response = self.http.post(
            "/api/question",
            json={"question": "What does a high D mean?"},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.phase(), "answering")

    def recovery_state(self):
        return self.app_module.failure_recovery.state.value

    def check_timeout(self, seconds_from_now):
        app = self.app_module

        with app.playback_lock:
            return app.check_question_mode_timeout(
                time.monotonic() + seconds_from_now
            )

    # ------------------------------------------------- tests

    def test_pal_audio_is_never_captured(self):
        self.assertIn("user-1", self.call_client.renderers)
        self.assertNotIn("pal-1", self.call_client.renderers)
        self.assertEqual(
            self.app_module.tavus.listening_participant_ids,
            {"user-1"},
        )

    def test_voice_question_interrupts_answers_and_resumes(self):
        self.voice_interrupt_then_confirm("What does a high D mean?")

        # 1b: transcript goes to the XQ engine and the answer is spoken.
        self.wait_for_voice("question_answered")
        self.assertEqual(
            self.app_module.engine.questions,
            ["What does a high D mean?"],
        )
        self.assertEqual(self.phase(), "answering")
        self.assertEqual(
            self.echoes()[-1],
            "A strong D often means you like to decide quickly.",
        )

        # Answer plays to the end -> interrupted sentence resumes.
        self.started("answer-1")
        self.stopped("answer-1", interrupted=False)

        self.assertEqual(self.phase(), "narrating")
        self.assertEqual(
            self.echoes()[-1],
            "To continue where we left off... "
            "Your DISC profile shows a strong D.",
        )

    def test_manual_button_route_pauses_without_voice_and_resumes_after_answer(self):
        self.start_narration()
        app = self.app_module
        original_index = app.orchestrator.cursor.sentence_index
        original_echoes = len(self.echoes())

        response = self.http.post("/api/debrief/interrupt")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(self.interrupts()), 1)
        pending = self.http.get("/api/activity").json
        self.assertTrue(pending["interrupted"])
        self.assertFalse(pending["question_ready"])

        # An unrelated stop cannot open question mode or advance narration.
        self.stopped("unrelated", interrupted=True)
        self.assertEqual(self.phase(), "narrating")
        self.stopped("narration-1", interrupted=True)
        paused = self.http.get("/api/activity").json
        self.assertTrue(paused["question_ready"])
        self.assertFalse(paused["interrupted"])
        self.assertEqual(app.engine.get_interaction_mode().value, "question")
        self.assertEqual(app.orchestrator.cursor.sentence_index, original_index)
        self.assertEqual(len(self.echoes()), original_echoes)
        self.assertGreater(app.question_mode_seconds_left(), 29)

        # A delayed completion cannot skip the interrupted sentence.
        self.stopped("narration-1", interrupted=False)
        self.assertEqual(app.orchestrator.cursor.sentence_index, original_index)
        self.ask_typed_question()
        self.started("answer-1")
        self.stopped("answer-1", interrupted=False)
        self.assertEqual(self.phase(), "narrating")
        self.assertEqual(app.orchestrator.cursor.sentence_index, original_index)
        self.assertTrue(self.echoes()[-1].startswith("To continue where we left off... "))
        self.assertIsNone(app.question_mode_seconds_left())

    def test_voice_dismissal_resumes_without_api_call(self):
        self.voice_interrupt_then_confirm("Oh, never mind. My mistake, please continue.")

        # 2: no reasoning call, narration resumes at the same sentence.
        self.wait_for_voice("question_dismissed")
        self.assertEqual(self.app_module.engine.questions, [])
        self.assertEqual(self.phase(), "narrating")
        self.assertEqual(
            self.app_module.engine.get_interaction_mode().value,
            "debrief",
        )
        self.assertEqual(
            self.echoes()[-1],
            "No problem. Picking up where we left off... "
            "Your DISC profile shows a strong D.",
        )

        # The resumed sentence is tracked: completing it moves on.
        self.started("narration-2")
        self.stopped("narration-2", interrupted=False)
        self.assertEqual(
            self.echoes()[-1],
            "You move quickly toward results.",
        )

    def test_filler_keeps_question_mode_open(self):
        self.voice_interrupt_then_confirm("Um, wait.")

        self.wait_for_voice("still_listening")
        self.assertEqual(self.phase(), "question_ready")
        self.assertEqual(self.app_module.engine.questions, [])

    def test_speech_between_sentences_interrupts_next_sentence(self):
        self.openai.audio.transcriptions.text = "Continue"

        response = self.http.post("/api/debrief/tracked/next")
        self.assertEqual(response.status_code, 200)

        # User talks before Tavus reports the sentence started.
        self.speak_into_room()
        self.assertTrue(
            wait_until(lambda: self.app_module.voice_interrupt_requested_at is not None)
        )
        self.assertEqual(self.interrupts(), [])

        self.started("narration-1")
        self.assertEqual(len(self.interrupts()), 1)

        self.stopped("narration-1", interrupted=True)
        self.wait_for_voice("question_dismissed")
        self.assertEqual(self.phase(), "narrating")

    def test_typed_dismissal_skips_reasoner(self):
        self.start_narration()
        self.http.post("/api/debrief/interrupt")
        self.stopped("narration-1", interrupted=True)

        response = self.http.post(
            "/api/question",
            json={"question": "My mistake"},
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200, body)
        self.assertTrue(body["dismissed"])
        self.assertEqual(self.app_module.engine.questions, [])
        self.assertEqual(body["playback"]["phase"], "narrating")

    def test_typed_question_still_answers(self):
        self.start_narration()
        self.http.post("/api/debrief/interrupt")
        self.stopped("narration-1", interrupted=True)

        response = self.http.post(
            "/api/question",
            json={"question": "How do I talk to my teenager?"},
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["question"], "How do I talk to my teenager?")
        self.assertEqual(body["playback"]["phase"], "answering")

    def test_dismiss_endpoint(self):
        response = self.http.post("/api/question/dismiss")
        self.assertEqual(response.status_code, 409)

        self.start_narration()
        self.http.post("/api/debrief/interrupt")
        self.stopped("narration-1", interrupted=True)

        response = self.http.post("/api/question/dismiss")
        body = response.get_json()

        self.assertEqual(response.status_code, 200, body)
        self.assertTrue(body["resumed"])
        self.assertEqual(body["playback"]["phase"], "narrating")

    def test_audio_upload_interrupts_and_answers(self):
        self.openai.audio.transcriptions.text = "Why is my EQ low?"
        self.start_narration()

        # Tavus confirms the stop while the upload is processed.
        threading.Timer(
            0.3,
            lambda: self.stopped("narration-1", interrupted=True),
        ).start()

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm(500, SPEECH))

        response = self.http.post(
            "/api/voice/audio",
            data=buffer.getvalue(),
            content_type="audio/wav",
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["transcript"], "Why is my EQ low?")
        self.assertEqual(body["voice_result"]["action"], "question_answered")
        self.assertEqual(self.app_module.engine.questions, ["Why is my EQ low?"])

    def test_audio_upload_rejects_unknown_type(self):
        response = self.http.post(
            "/api/voice/audio",
            data=b"abc",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 415)

    def test_status_reports_voice(self):
        body = self.http.get("/api/status").get_json()

        self.assertTrue(body["voice"]["worker_running"])
        self.assertEqual(
            body["tavus"]["voice_listening_participants"],
            ["user-1"],
        )
        self.assertEqual(body["tavus"]["pal_participants"], ["pal-1"])

    # ------------------------------- question mode timeout

    def test_question_mode_times_out_and_resumes(self):
        self.start_narration()
        self.open_question_mode()

        body = self.http.get("/api/status").get_json()
        self.assertEqual(body["playback"]["question_mode_timeout_seconds"], 30)
        self.assertGreater(body["playback"]["question_mode_seconds_left"], 29)

        # Not yet.
        self.assertIsNone(self.check_timeout(10))
        self.assertEqual(self.phase(), "question_ready")

        outcome = self.check_timeout(31)

        self.assertEqual(outcome["action"], "question_timed_out")
        self.assertEqual(self.phase(), "narrating")
        self.assertEqual(self.app_module.engine.questions, [])
        self.assertEqual(
            self.app_module.engine.get_interaction_mode().value,
            "debrief",
        )
        self.assertEqual(
            self.echoes()[-1],
            "Let's keep going. Picking up where we left off... "
            "Your DISC profile shows a strong D.",
        )

        # The resumed sentence is tracked as usual.
        self.started("narration-2")
        self.stopped("narration-2", interrupted=False)
        self.assertEqual(self.echoes()[-1], "You move quickly toward results.")

    def test_question_mode_timeout_waits_while_user_talks(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()

        original_busy = app.voice_pipeline.busy
        app.voice_pipeline.busy = lambda: True

        try:
            # Speaking or transcribing: never times out.
            self.assertIsNone(self.check_timeout(31))
            self.assertEqual(self.phase(), "question_ready")

        finally:
            app.voice_pipeline.busy = original_busy

        # The full timeout counts again from the last activity.
        self.assertIsNone(self.check_timeout(40))
        self.assertEqual(self.phase(), "question_ready")

        self.assertEqual(
            self.check_timeout(62)["action"],
            "question_timed_out",
        )
        self.assertEqual(self.phase(), "narrating")

    def test_live_speech_in_question_mode_restarts_timer(self):
        app = self.app_module
        self.start_narration()
        self.open_question_mode()

        with app.playback_lock:
            app.question_mode_deadline = time.monotonic() + 1

        app.handle_voice_speech_started("user-1")

        self.assertGreater(app.question_mode_seconds_left(), 29)
        # No second interrupt: question mode is already open.
        self.assertEqual(len(self.interrupts()), 1)

    def test_keepalive_restarts_timer(self):
        app = self.app_module

        response = self.http.post("/api/question/keepalive")
        self.assertEqual(response.status_code, 409)

        self.start_narration()
        self.open_question_mode()

        with app.playback_lock:
            app.question_mode_deadline = time.monotonic() + 1

        response = self.http.post("/api/question/keepalive")
        body = response.get_json()

        self.assertEqual(response.status_code, 200, body)
        self.assertGreater(body["question_mode_seconds_left"], 29)

    def test_answering_stops_the_timer(self):
        self.start_narration()
        self.open_question_mode()
        self.ask_typed_question()

        self.assertIsNone(self.check_timeout(31))
        self.assertIsNone(self.app_module.question_mode_deadline)
        self.assertEqual(self.phase(), "answering")

    # ------------------------------------- failure recovery

    def test_interrupted_answer_recovers_every_time(self):
        self.start_narration()

        for round_number in (1, 2, 3):
            self.open_question_mode(f"narration-{round_number}")
            self.ask_typed_question()

            self.started(f"answer-{round_number}")
            self.stopped(f"answer-{round_number}", interrupted=True)

            self.assertEqual(self.phase(), "narrating")
            self.assertEqual(self.recovery_state(), "ready_to_resume_narration")

            # The preserved sentence plays again on the next request.
            response = self.http.post("/api/debrief/tracked/next")
            body = response.get_json()

            self.assertEqual(response.status_code, 200, body)
            self.assertNotIn("finished", body)
            self.assertEqual(body["spoken"], "Your DISC profile shows a strong D.")
            self.assertEqual(self.recovery_state(), "idle")

            self.started(f"narration-{round_number + 1}")

    def test_uncertain_resume_is_confirmed_and_cleared(self):
        self.start_narration()
        self.open_question_mode()
        self.ask_typed_question()
        self.started("answer-1")

        # The resume reaches Tavus, but the client reports an error.
        original_send = self.call_client.send_app_message

        def delivered_then_raises(message):
            self.call_client.send_app_message = original_send
            original_send(message)
            raise ConnectionError("acknowledgement lost")

        self.call_client.send_app_message = delivered_then_raises

        self.stopped("answer-1", interrupted=False)

        self.assertEqual(self.phase(), "narrating")
        self.assertEqual(self.recovery_state(), "resume_delivery_uncertain")

        # Tavus proves it is playing: recovery is cleared.
        self.started("narration-2")
        self.assertEqual(self.recovery_state(), "idle")

        self.stopped("narration-2", interrupted=False)
        self.assertEqual(self.echoes()[-1], "You move quickly toward results.")

        # A later interrupted answer still recovers.
        self.started("narration-3")
        self.open_question_mode("narration-3")
        self.ask_typed_question()
        self.started("answer-2")
        self.stopped("answer-2", interrupted=True)

        self.assertEqual(self.phase(), "narrating")
        self.assertEqual(self.recovery_state(), "ready_to_resume_narration")


if __name__ == "__main__":
    unittest.main()
