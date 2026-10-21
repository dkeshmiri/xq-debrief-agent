import queue
import threading
import time
import traceback
from array import array
from dataclasses import dataclass
from typing import Callable

from speech_transcriber import SpeechTranscriber
from voice_activity import (
    SegmenterConfig,
    SegmentEventType,
    UtteranceSegmenter,
)


SpeechScorer = Callable[[bytes], float]


@dataclass(frozen=True)
class _SpeechStarted:
    participant_id: str
    stream: "_ParticipantStream"


@dataclass(frozen=True)
class _UtteranceReady:
    participant_id: str
    stream: "_ParticipantStream"
    audio: bytes
    duration_ms: int


class _Stop:
    pass


class _ParticipantStream:
    def __init__(
        self,
        scorer: SpeechScorer,
        config: SegmenterConfig,
    ) -> None:
        self.scorer = scorer
        self.segmenter = UtteranceSegmenter(config)
        self.remainder = b""
        self.pending = 0
        self.accepted = True
        self.last_audio_at = time.monotonic()


class VoiceInputPipeline:
    """
    Turns live user audio into two signals:

        speech started  -> on_speech_started(participant_id)
        utterance text  -> on_transcript(participant_id, text)

    feed_audio() is called from the transport's audio
    thread and only does fast work. Callbacks and
    speech-to-text run on one worker thread, in order.

    This class knows nothing about Flask, Tavus,
    or the debrief state.
    """

    SAMPLE_RATE = 16_000

    def __init__(
        self,
        *,
        transcriber: SpeechTranscriber,
        on_speech_started: Callable[[str], bool | None],
        on_transcript: Callable[[str, str], None],
        scorer_factory: Callable[[], SpeechScorer],
        config: SegmenterConfig | None = None,
        min_utterance_ms: int = 300,
        callback_lock=None,
        before_transcript: Callable[[], None] = lambda: None,
        get_question_context: Callable[[], object] = lambda: True,
    ) -> None:
        self.before_transcript = before_transcript
        self.get_question_context = get_question_context
        self.transcriber = transcriber
        self.on_speech_started = on_speech_started
        self.on_transcript = on_transcript
        self.scorer_factory = scorer_factory
        self.config = config or SegmenterConfig()
        self.min_utterance_ms = min_utterance_ms

        self._frame_bytes = (
            self.SAMPLE_RATE
            * self.config.frame_ms
            // 1000
            * 2
        )

        self._streams: dict[str, _ParticipantStream] = {}
        self._failed_participants: set[str] = set()
        self._lock = threading.Lock()

        # Bound memory if transcription is slower than incoming speech.
        self._queue: queue.Queue = queue.Queue(maxsize=64)
        self._callback_lock = callback_lock or threading.RLock()
        self._worker: threading.Thread | None = None


    # -----------------------------------------------------
    # LIFECYCLE
    # -----------------------------------------------------

    def start(self) -> None:
        if self._worker is not None:
            return

        self._worker = threading.Thread(
            target=self._run,
            name="xq-voice-input",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        if self._worker is None:
            return

        self.reset()
        self._queue.put(_Stop())
        self._worker.join(timeout=5)
        if not self._worker.is_alive():
            self._worker = None

    def reset(self) -> None:
        """
        Invalidate queued events and in-flight transcripts from old streams.
        """

        with self._callback_lock, self._lock:
            self._streams.clear()
            self._failed_participants.clear()

    def drop_participant(
        self,
        participant_id: str,
    ) -> None:
        with self._callback_lock, self._lock:
            self._streams.pop(participant_id, None)
            self._failed_participants.discard(participant_id)

    # -----------------------------------------------------
    # AUDIO INPUT (transport thread)
    # -----------------------------------------------------

    def feed_audio(
        self,
        participant_id: str,
        pcm: bytes,
        sample_rate: int,
        num_channels: int = 1,
    ) -> None:
        if sample_rate != self.SAMPLE_RATE:
            raise ValueError(
                f"Voice input expects {self.SAMPLE_RATE} Hz "
                f"audio, got {sample_rate} Hz."
            )

        if num_channels == 2:
            pcm = _downmix_stereo(pcm)
        elif num_channels != 1:
            raise ValueError(
                "Voice input supports mono or stereo audio, "
                f"got {num_channels} channels."
            )

        with self._lock:
            stream = self._stream_for(participant_id)

            if stream is None:
                return

            stream.last_audio_at = time.monotonic()
            data = stream.remainder + pcm
            usable = (
                len(data)
                - len(data) % self._frame_bytes
            )
            stream.remainder = data[usable:]

            for offset in range(
                0,
                usable,
                self._frame_bytes,
            ):
                frame = data[
                    offset:offset + self._frame_bytes
                ]

                events = stream.segmenter.process(
                    frame,
                    stream.scorer(frame),
                )

                for event in events:
                    if self._streams.get(participant_id) is not stream:
                        return
                    self._enqueue_segment_event(
                        participant_id,
                        event,
                    )

    def _stream_for(
        self,
        participant_id: str,
    ) -> _ParticipantStream | None:
        stream = self._streams.get(participant_id)

        if stream is not None:
            return stream

        if participant_id in self._failed_participants:
            return None

        try:
            scorer = self.scorer_factory()

        except Exception:
            # Logged once per participant; frames from
            # this participant are dropped until reset.
            self._failed_participants.add(participant_id)

            print(
                "[XQ VOICE] Could not create a speech "
                f"detector for participant {participant_id}. "
                "Voice input is disabled for them."
            )
            traceback.print_exc()

            return None

        stream = _ParticipantStream(
            scorer,
            self.config,
        )
        self._streams[participant_id] = stream

        return stream

    def _enqueue_segment_event(
        self,
        participant_id: str,
        event,
    ) -> None:
        stream = self._streams[participant_id]
        if event.event_type == SegmentEventType.SPEECH_STARTED:
            item = _SpeechStarted(participant_id, stream)
        elif event.duration_ms >= self.min_utterance_ms:
            item = _UtteranceReady(
                participant_id, stream, event.audio, event.duration_ms
            )
        else:
            return

        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Discard this stream's partial conversation rather than deliver
            # an utterance whose speech-start event may have been dropped.
            self._streams.pop(participant_id, None)
        else:
            stream.pending += 1

    # -----------------------------------------------------
    # WORKER
    # -----------------------------------------------------

    def _run(self) -> None:
        while True:
            item = self._queue.get()

            if isinstance(item, _Stop):
                return

            try:
                self._handle(item)

            except Exception:
                print(
                    "[XQ VOICE] Voice event failed: "
                    f"{item!r:.200}"
                )
                traceback.print_exc()

            finally:
                with self._lock:
                    item.stream.pending -= 1
                self._queue.task_done()

    def _is_current(self, item) -> bool:
        with self._lock:
            return self._streams.get(item.participant_id) is item.stream

    def _handle(self, item) -> None:
        # Use the app's playback lock for callbacks, but never for STT.
        # This makes session reset and callback delivery atomic.
        with self._callback_lock:
            if not self._is_current(item):
                return
            if isinstance(item, _SpeechStarted):
                item.stream.accepted = (
                    self.on_speech_started(item.participant_id) is not False
                )
                return
            if not item.stream.accepted:
                return

        self.before_transcript()
        with self._callback_lock:
            if not self._is_current(item):
                return
            context = self.get_question_context()
            if context is None:
                return

        text = self.transcriber.transcribe_pcm16(item.audio, self.SAMPLE_RATE)

        with self._callback_lock:
            if self._is_current(item) and context == self.get_question_context():
                self.on_transcript(item.participant_id, text)

    def busy(self) -> bool:
        """
        True while the user is talking or an utterance
        is still being transcribed or handled.
        """

        with self._lock:
            # Muting a microphone may stop frames entirely. Supply the missing
            # endpoint silence so a half-finished utterance cannot block timeout.
            now = time.monotonic()
            for participant_id, stream in tuple(self._streams.items()):
                if (stream.segmenter.speaking
                        and now - stream.last_audio_at >= self.config.end_silence_ms / 1000):
                    for _ in range(self.config.end_silence_ms // self.config.frame_ms):
                        events = stream.segmenter.process(bytes(self._frame_bytes), 0.0)
                        for event in events:
                            self._enqueue_segment_event(participant_id, event)
                        if not stream.segmenter.speaking:
                            break
            return any(
                stream.pending > 0 or stream.segmenter.speaking
                for stream in self._streams.values()
            )

    def status(self) -> dict:
        with self._lock:
            return {
                "worker_running": (
                    self._worker is not None
                    and self._worker.is_alive()
                ),
                "listening_participants": sorted(
                    self._streams
                ),
                "user_speaking": any(
                    stream.segmenter.speaking
                    for stream in self._streams.values()
                ),
                "queued_events": self._queue.qsize(),
                "stt_model": self.transcriber.model,
            }


def _downmix_stereo(pcm: bytes) -> bytes:
    samples = array("h")
    samples.frombytes(
        pcm[: len(pcm) - len(pcm) % 4]
    )

    mono = array(
        "h",
        (
            (samples[index] + samples[index + 1]) // 2
            for index in range(0, len(samples), 2)
        ),
    )

    return mono.tobytes()
