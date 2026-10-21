from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecoveryState(Enum):
    IDLE = "idle"

    ANSWER_INTERRUPTED = "answer_interrupted"

    RESUME_DELIVERY_UNCERTAIN = (
        "resume_delivery_uncertain"
    )

    READY_TO_RESUME_NARRATION = (
        "ready_to_resume_narration"
    )

    READY_TO_RETRY_RESUME = (
        "ready_to_retry_resume"
    )

    RESUME_DELIVERY_CONFIRMED = (
        "resume_delivery_confirmed"
    )


class RecoveryReason(Enum):
    ANSWER_INTERRUPTED = "answer_interrupted"

    RESUME_SUBMISSION_ERROR = (
        "resume_submission_error"
    )


@dataclass(frozen=True)
class PlaybackSnapshot:
    """
    Playback position that must survive recovery.

    Recovery must never advance this position.
    """

    section: str | None
    sentence_index: int
    utterance_id: int | None


@dataclass(frozen=True)
class RecoveryRecord:
    reason: RecoveryReason
    snapshot: PlaybackSnapshot

    answer_inference_id: str | None = None

    resume_utterance_id: int | None = None
    resume_inference_id: str | None = None


class FailureRecovery:
    """
    Standalone recovery state machine.

    This module intentionally has no Flask,
    Tavus, engine, or orchestrator dependencies.
    """

    def __init__(self) -> None:
        self._state = RecoveryState.IDLE
        self._record: RecoveryRecord | None = None

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def record(self) -> RecoveryRecord | None:
        return self._record

    @property
    def active(self) -> bool:
        return self._state != RecoveryState.IDLE

    def begin_answer_interrupted(
        self,
        snapshot: PlaybackSnapshot,
        *,
        answer_inference_id: str | None = None,
    ) -> None:
        """
        The answer definitely stopped.

        Answer ownership may later be cleared,
        but narration position must remain frozen.
        """

        self._require_idle()

        self._record = RecoveryRecord(
            reason=RecoveryReason.ANSWER_INTERRUPTED,
            snapshot=snapshot,
            answer_inference_id=answer_inference_id,
        )

        self._state = (
            RecoveryState.ANSWER_INTERRUPTED
        )

    def recover_from_answer_interruption(
        self,
    ) -> PlaybackSnapshot:
        """
        Resolve an interrupted answer.

        The caller may clear answer playback ownership
        and return to the preserved narration sentence.
        """

        self._require_state(
            RecoveryState.ANSWER_INTERRUPTED
        )

        assert self._record is not None

        snapshot = self._record.snapshot

        self._state = (
            RecoveryState.READY_TO_RESUME_NARRATION
        )

        return snapshot

    def begin_resume_delivery_uncertain(
        self,
        snapshot: PlaybackSnapshot,
        *,
        resume_utterance_id: int,
    ) -> None:
        """
        Resume Echo submission raised after ownership
        had already been registered.

        Delivery may have succeeded.

        Never automatically retry from this state.
        """

        self._require_idle()

        self._record = RecoveryRecord(
            reason=(
                RecoveryReason.RESUME_SUBMISSION_ERROR
            ),
            snapshot=snapshot,
            resume_utterance_id=resume_utterance_id,
        )

        self._state = (
            RecoveryState.RESUME_DELIVERY_UNCERTAIN
        )

    def confirm_resume_delivery_started(
        self,
        inference_id: str,
    ) -> PlaybackSnapshot:
        """
        Tavus later proves that the uncertain
        resume submission actually started.

        Existing narration ownership should remain.
        """

        self._require_state(
            RecoveryState.RESUME_DELIVERY_UNCERTAIN
        )

        if not inference_id:
            raise ValueError(
                "inference_id is required."
            )

        assert self._record is not None

        self._record = RecoveryRecord(
            reason=self._record.reason,
            snapshot=self._record.snapshot,
            answer_inference_id=(
                self._record.answer_inference_id
            ),
            resume_utterance_id=(
                self._record.resume_utterance_id
            ),
            resume_inference_id=inference_id,
        )

        self._state = (
            RecoveryState.RESUME_DELIVERY_CONFIRMED
        )

        return self._record.snapshot

    def confirm_resume_not_delivered(
        self,
    ) -> PlaybackSnapshot:
        """
        External evidence proves that Tavus did not
        start the uncertain resume submission.

        Only now is retrying the same sentence safe.
        """

        self._require_state(
            RecoveryState.RESUME_DELIVERY_UNCERTAIN
        )

        assert self._record is not None

        snapshot = self._record.snapshot

        self._state = (
            RecoveryState.READY_TO_RETRY_RESUME
        )

        return snapshot

    def reset(self) -> None:
        """
        Clear recovery state.

        Intended for successful recovery,
        session reset, or session shutdown.
        """

        self._record = None
        self._state = RecoveryState.IDLE

    def _require_idle(self) -> None:
        if self.active:
            raise RuntimeError(
                "A recovery operation is already active."
            )

    def _require_state(
        self,
        expected: RecoveryState,
    ) -> None:
        if self._state != expected:
            raise RuntimeError(
                "Invalid recovery transition: "
                f"{self._state.value} -> "
                f"{expected.value}"
            )