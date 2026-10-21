from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from failure_recovery import (
    FailureRecovery,
    PlaybackSnapshot,
    RecoveryState,
)


class TrackerLike(Protocol):
    utterance_id: int | None
    inference_id: str | None

    def clear(self) -> None:
        ...


class CursorLike(Protocol):
    section: object
    sentence_index: int
    active_utterance: object | None


class OrchestratorLike(Protocol):
    cursor: CursorLike

    def recover_from_interrupted_answer(self) -> None:
        ...


@dataclass(frozen=True)
class RecoveryResult:
    state: RecoveryState
    snapshot: PlaybackSnapshot


class RecoveryController:
    """
    Coordinates recovery state with playback ownership.

    This class deliberately knows nothing about:
    - Flask
    - Tavus
    - HTTP routes
    - Daily
    - frontend state
    """

    def __init__(
        self,
        recovery: FailureRecovery,
    ) -> None:
        self.recovery = recovery

    def snapshot_from_orchestrator(
        self,
        orchestrator: OrchestratorLike,
    ) -> PlaybackSnapshot:

        cursor = orchestrator.cursor

        section = (
            cursor.section.value
            if getattr(
                cursor.section,
                "value",
                None,
            ) is not None
            else str(cursor.section)
            if cursor.section is not None
            else None
        )

        active_utterance = (
            cursor.active_utterance
        )

        utterance_id = (
            active_utterance.id
            if active_utterance is not None
            else None
        )

        return PlaybackSnapshot(
            section=section,
            sentence_index=(
                cursor.sentence_index
            ),
            utterance_id=utterance_id,
        )

    def handle_answer_interrupted(
        self,
        *,
        orchestrator: OrchestratorLike,
        answer_tracker: TrackerLike,
    ) -> RecoveryResult:
        """
        The answer definitely stopped.

        Safe actions:
        - preserve narration cursor
        - record answer failure
        - clear answer ownership
        - exit question mode

        Unsafe action:
        - advancing narration
        """

        snapshot = (
            self.snapshot_from_orchestrator(
                orchestrator
            )
        )

        self.recovery.begin_answer_interrupted(
            snapshot,
            answer_inference_id=(
                answer_tracker.inference_id
            ),
        )

        recovered = (
            self.recovery
            .recover_from_answer_interruption()
        )

        answer_tracker.clear()

        orchestrator.recover_from_interrupted_answer()

        return RecoveryResult(
            state=self.recovery.state,
            snapshot=recovered,
        )

    def handle_resume_submission_error(
        self,
        *,
        orchestrator: OrchestratorLike,
        narration_tracker: TrackerLike,
    ) -> RecoveryResult:
        """
        Resume submission raised after narration
        ownership was registered.

        Delivery may have succeeded.

        Do not clear narration ownership.
        Do not retry.
        Do not advance the cursor.
        """

        if narration_tracker.utterance_id is None:
            raise RuntimeError(
                "Cannot recover uncertain resume "
                "without narration ownership."
            )

        snapshot = (
            self.snapshot_from_orchestrator(
                orchestrator
            )
        )

        self.recovery.begin_resume_delivery_uncertain(
            snapshot,
            resume_utterance_id=(
                narration_tracker.utterance_id
            ),
        )

        return RecoveryResult(
            state=self.recovery.state,
            snapshot=snapshot,
        )

    def confirm_resume_started(
        self,
        *,
        inference_id: str,
    ) -> RecoveryResult:
        """
        Tavus later proves the uncertain resume
        actually started.

        Existing narration ownership remains valid.
        """

        snapshot = (
            self.recovery
            .confirm_resume_delivery_started(
                inference_id
            )
        )

        return RecoveryResult(
            state=self.recovery.state,
            snapshot=snapshot,
        )

    def confirm_resume_not_delivered(
        self,
    ) -> RecoveryResult:
        """
        External evidence proves the uncertain
        resume never started.

        Retrying can now be considered safe.
        """

        snapshot = (
            self.recovery
            .confirm_resume_not_delivered()
        )

        return RecoveryResult(
            state=self.recovery.state,
            snapshot=snapshot,
        )

    def reset(self) -> None:
        self.recovery.reset()