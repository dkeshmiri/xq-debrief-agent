
from dataclasses import dataclass
from enum import Enum

from debrief_engine import DebriefEngine
from playback_cursor import PlaybackCursor, Utterance
from sentence_splitter import split_sentences


class ConversationPhase(str, Enum):
    NARRATING = "narrating"
    QUESTION_READY = "question_ready"
    ANSWERING = "answering"


@dataclass(frozen=True)
class SpeechTurn:
    """
    Text that an external playback layer should speak.

    The utterance ID belongs to PlaybackCursor.
    It is not a Tavus conversation or event ID.
    """

    utterance_id: int
    text: str


class ConversationOrchestrator:
    """
    Coordinates narration, questions, and resumption.

    The engine owns debrief state and assessment logic.
    The cursor owns sentence position.
    This class owns the interaction sequence.
    """

    RESUME_PREFIX = "To continue where we left off... "
    DISMISS_PREFIX = "No problem. Picking up where we left off... "
    TIMEOUT_PREFIX = "Let's keep going. Picking up where we left off... "

    def __init__(
        self,
        engine: DebriefEngine,
        cursor: PlaybackCursor | None = None,
    ) -> None:
        self.engine = engine

        self.cursor = (
            cursor
            if cursor is not None
            else PlaybackCursor()
        )

        self.phase = ConversationPhase.NARRATING
        self.pending_answer: str | None = None

    def load_current_section(self) -> None:
        """
        Load the engine's current narrative into the cursor.

        Do not silently discard an active or paused
        conversation.
        """

        if self.cursor.active_utterance is not None:
            raise RuntimeError(
                "Cannot load a section during playback."
            )

        if self.phase != ConversationPhase.NARRATING:
            raise RuntimeError(
                "Cannot load a section during a question."
            )

        narrative = self.engine.get_current_content()
        sentences = split_sentences(narrative)

        self.cursor.load_section(
            section=self.engine.get_current_state(),
            sentences=sentences,
        )

    def next_narration(self) -> SpeechTurn | None:
        """
        Request the next sentence for playback.

        Does not mark that sentence complete.
        """

        if self.phase != ConversationPhase.NARRATING:
            return None

        utterance = self.cursor.start_next()

        if utterance is None:
            return None

        return self._speech_turn(utterance)

    def narration_finished(
        self,
        utterance_id: int,
    ) -> bool:
        """
        Confirm completion of a specific sentence.

        A stale event from interrupted playback
        cannot advance the cursor.
        """

        if self.phase != ConversationPhase.NARRATING:
            return False

        return self.cursor.complete(utterance_id)

    def interrupt(self) -> None:
        """
        Pause narration and enter question mode.

        Actual audio cancellation will be handled
        by the Tavus integration later.
        """

        if self.phase != ConversationPhase.NARRATING:
            raise RuntimeError(
                "This first version only supports "
                "interrupting narration."
            )

        if self.cursor.active_utterance is None:
            raise RuntimeError(
                "There is no active narration to interrupt."
            )

        self.cursor.interrupt()
        self.engine.enter_question_mode()

        self.phase = ConversationPhase.QUESTION_READY

    def open_question(self) -> None:
        """Open questions between sections or after the closing narration."""
        if self.phase != ConversationPhase.NARRATING or self.cursor.active_utterance is not None:
            raise RuntimeError("Finish or interrupt narration before opening question mode.")
        self.cursor.interrupt()
        self.engine.enter_question_mode()
        self.phase = ConversationPhase.QUESTION_READY

    def ask_question(self, question: str) -> str:
        """
        Generate an approved answer using the existing
        XQ engine and its guardrails.

        The caller must deliver the returned text
        and confirm playback completion separately.
        """

        if self.phase != ConversationPhase.QUESTION_READY:
            raise RuntimeError(
                "The orchestrator is not ready for a question."
            )

        if not question.strip():
            raise ValueError(
                "A question cannot be empty."
            )

        # If reasoning raises an exception, remain in
        # QUESTION_READY so the caller can retry.
        answer = self.engine.answer_question(question)

        self.pending_answer = answer
        self.phase = ConversationPhase.ANSWERING

        return answer

    def dismiss_question(
        self,
        prefix: str | None = None,
    ) -> SpeechTurn | None:
        """
        Leave question mode without asking anything
        ("never mind", "continue", a timeout, ...).

        No answer is generated. Restore the original
        debrief section and replay the interrupted
        sentence, spoken after prefix (default:
        DISMISS_PREFIX).
        """

        if self.phase != ConversationPhase.QUESTION_READY:
            raise RuntimeError(
                "There is no open question to dismiss."
            )

        return self._resume_narration(
            self.DISMISS_PREFIX if prefix is None else prefix
        )

    def recover_from_interrupted_answer(self) -> None:
        """
        Recover after answer playback was interrupted.

        Leaves the interrupted narration sentence
        preserved and ready to resume later.
        """

        if self.phase != ConversationPhase.ANSWERING:
            raise RuntimeError(
                "There is no interrupted answer to recover from."
            )

        self.engine.exit_question_mode()

        self.pending_answer = None
        self.phase = ConversationPhase.NARRATING

        # Unpause without starting playback: the next
        # narration request replays the preserved
        # sentence. (cursor.resume() would start it now.)
        self.cursor.paused = False

    def answer_finished(self) -> SpeechTurn | None:
        """
        Called only after the answer has actually
        finished playing.

        Restore the original debrief section and
        replay the interrupted sentence.
        """

        if self.phase != ConversationPhase.ANSWERING:
            raise RuntimeError(
                "There is no completed answer to resume from."
            )

        return self._resume_narration(self.RESUME_PREFIX)

    def _resume_narration(self, prefix: str) -> SpeechTurn | None:
        self.engine.exit_question_mode()

        self.pending_answer = None
        self.phase = ConversationPhase.NARRATING

        utterance = self.cursor.resume()

        if utterance is None:
            return None

        return SpeechTurn(
            utterance_id=utterance.id,
            text=prefix + utterance.text,
        )

    @staticmethod
    def _speech_turn(
        utterance: Utterance,
    ) -> SpeechTurn:
        return SpeechTurn(
            utterance_id=utterance.id,
            text=utterance.text,
        )
