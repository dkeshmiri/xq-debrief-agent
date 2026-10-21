from array import array
from collections import deque
from dataclasses import dataclass
from enum import Enum
import math


class SegmentEventType(str, Enum):
    SPEECH_STARTED = "speech_started"
    UTTERANCE_ENDED = "utterance_ended"


@dataclass(frozen=True)
class SegmentEvent:
    event_type: SegmentEventType
    audio: bytes = b""
    duration_ms: int = 0


@dataclass(frozen=True)
class SegmenterConfig:
    """
    Endpointing thresholds.

    All durations are in milliseconds and must be
    multiples of frame_ms.
    """

    frame_ms: int = 10

    # A frame counts as speech above this probability.
    speech_threshold: float = 0.6

    # Speech must fill most of this window before it
    # counts as the user starting to talk. Filters
    # coughs, clicks, and short noises.
    start_window_ms: int = 200
    start_ratio: float = 0.8

    # Silence that ends an utterance.
    end_silence_ms: int = 700

    # Audio kept from just before speech was confirmed,
    # so the first syllable is not cut off.
    preroll_ms: int = 300

    # Hard cap: a stuck stream must not grow forever.
    max_utterance_ms: int = 30_000

    def __post_init__(self) -> None:
        if self.frame_ms <= 0:
            raise ValueError("frame_ms must be positive.")
        for name in ("start_window_ms", "end_silence_ms", "max_utterance_ms"):
            value = getattr(self, name)
            if value <= 0 or value % self.frame_ms:
                raise ValueError(f"{name} must be a positive multiple of frame_ms.")
        if self.preroll_ms < 0 or self.preroll_ms % self.frame_ms:
            raise ValueError("preroll_ms must be a non-negative multiple of frame_ms.")
        if not 0 < self.start_ratio <= 1 or not 0 < self.speech_threshold <= 1:
            raise ValueError("Speech thresholds must be in (0, 1].")
        if self.max_utterance_ms < self.start_window_ms + self.preroll_ms:
            raise ValueError("max_utterance_ms must include the speech-start window and preroll.")


class _Phase(str, Enum):
    IDLE = "idle"
    SPEAKING = "speaking"


class UtteranceSegmenter:
    """
    Turns a stream of scored audio frames into
    speech-start and utterance-end events.

    It does not score audio, transcribe, or talk to
    the debrief. One instance per audio stream.
    """

    def __init__(
        self,
        config: SegmenterConfig | None = None,
    ) -> None:
        self.config = config or SegmenterConfig()

        frame_ms = self.config.frame_ms

        self._start_frames = max(
            1,
            self.config.start_window_ms // frame_ms,
        )
        self._end_frames = max(
            1,
            self.config.end_silence_ms // frame_ms,
        )
        self._max_frames = max(
            1,
            self.config.max_utterance_ms // frame_ms,
        )

        preroll_frames = (
            self.config.preroll_ms // frame_ms
        )

        self._window: deque[tuple[bytes, bool]] = deque(
            maxlen=self._start_frames
        )
        self._preroll: deque[bytes] = deque(
            maxlen=preroll_frames
        )

        self._phase = _Phase.IDLE
        self._utterance: list[bytes] = []
        self._trailing_silence = 0

    @property
    def speaking(self) -> bool:
        return self._phase == _Phase.SPEAKING

    def reset(self) -> None:
        self._window.clear()
        self._preroll.clear()
        self._phase = _Phase.IDLE
        self._utterance = []
        self._trailing_silence = 0

    def process(
        self,
        frame: bytes,
        speech_probability: float,
    ) -> list[SegmentEvent]:
        """
        Feed one frame. Return the events it caused.
        """

        is_speech = (
            speech_probability
            >= self.config.speech_threshold
        )

        if self._phase == _Phase.IDLE:
            return self._process_idle(
                frame,
                is_speech,
            )

        return self._process_speaking(
            frame,
            is_speech,
        )

    def _process_idle(
        self,
        frame: bytes,
        is_speech: bool,
    ) -> list[SegmentEvent]:
        if len(self._window) == self._window.maxlen:
            # The oldest window frame becomes pre-roll.
            oldest_frame, _ = self._window[0]
            self._preroll.append(oldest_frame)

        self._window.append((frame, is_speech))

        speech_frames = sum(
            1
            for _, flagged in self._window
            if flagged
        )

        required = math.ceil(
            self._start_frames
            * self.config.start_ratio
        )

        if (
            len(self._window) < self._start_frames
            or speech_frames < required
        ):
            return []

        self._phase = _Phase.SPEAKING
        self._utterance = (
            list(self._preroll)
            + [buffered for buffered, _ in self._window]
        )
        self._trailing_silence = 0
        self._window.clear()
        self._preroll.clear()

        return [
            SegmentEvent(SegmentEventType.SPEECH_STARTED)
        ]

    def _process_speaking(
        self,
        frame: bytes,
        is_speech: bool,
    ) -> list[SegmentEvent]:
        self._utterance.append(frame)

        if is_speech:
            self._trailing_silence = 0
        else:
            self._trailing_silence += 1

        if (
            self._trailing_silence < self._end_frames
            and len(self._utterance) < self._max_frames
        ):
            return []

        audio = b"".join(self._utterance)
        duration_ms = (
            len(self._utterance)
            * self.config.frame_ms
        )

        self.reset()

        return [
            SegmentEvent(
                SegmentEventType.UTTERANCE_ENDED,
                audio=audio,
                duration_ms=duration_ms,
            )
        ]


class EnergySpeechScorer:
    """
    Dependency-free fallback scorer.

    Returns 1.0 when a frame is louder than the RMS
    threshold, otherwise 0.0. Prefer Daily's native
    VAD in production: loud background noise passes
    this check.
    """

    def __init__(
        self,
        rms_threshold: float = 500.0,
    ) -> None:
        self.rms_threshold = rms_threshold

    def __call__(self, frame: bytes) -> float:
        samples = array("h")
        samples.frombytes(frame)

        if not samples:
            return 0.0

        mean_square = (
            sum(sample * sample for sample in samples)
            / len(samples)
        )

        return (
            1.0
            if math.sqrt(mean_square) >= self.rms_threshold
            else 0.0
        )
