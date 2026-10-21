import unittest
from types import SimpleNamespace

from failure_recovery import (
    FailureRecovery,
    RecoveryState,
)
from recovery_controller import (
    RecoveryController,
)


class FakeTracker:
    def __init__(
        self,
        *,
        utterance_id=None,
        inference_id=None,
    ):
        self.utterance_id = utterance_id
        self.inference_id = inference_id
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1
        self.utterance_id = None
        self.inference_id = None


class FakeSection:
    def __init__(self, value):
        self.value = value


class FakeCursor:
    def __init__(self):
        self.section = FakeSection(
            "DISC_NARRATIVE"
        )

        self.sentence_index = 6

        self.active_utterance = (
            SimpleNamespace(
                id=10
            )
        )


class FakeOrchestrator:
    def __init__(self):
        self.cursor = FakeCursor()
        self.recover_calls = 0

    def recover_from_interrupted_answer(self):
        self.recover_calls += 1


class RecoveryControllerTests(
    unittest.TestCase
):

    def setUp(self):
        self.recovery = FailureRecovery()

        self.controller = (
            RecoveryController(
                self.recovery
            )
        )

        self.orchestrator = (
            FakeOrchestrator()
        )

    def test_snapshot_reads_cursor_without_modifying_it(
        self,
    ):
        snapshot = (
            self.controller
            .snapshot_from_orchestrator(
                self.orchestrator
            )
        )

        self.assertEqual(
            snapshot.section,
            "DISC_NARRATIVE",
        )

        self.assertEqual(
            snapshot.sentence_index,
            6,
        )

        self.assertEqual(
            snapshot.utterance_id,
            10,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .sentence_index,
            6,
        )

    def test_answer_interruption_clears_only_answer_tracker(
        self,
    ):
        answer_tracker = FakeTracker(
            utterance_id=1,
            inference_id="answer-123",
        )

        narration_tracker = FakeTracker(
            utterance_id=10,
            inference_id=None,
        )

        result = (
            self.controller
            .handle_answer_interrupted(
                orchestrator=(
                    self.orchestrator
                ),
                answer_tracker=(
                    answer_tracker
                ),
            )
        )

        self.assertEqual(
            result.state,
            RecoveryState
            .READY_TO_RESUME_NARRATION,
        )

        self.assertEqual(
            result.snapshot.sentence_index,
            6,
        )

        self.assertEqual(
            answer_tracker.clear_calls,
            1,
        )

        self.assertIsNone(
            answer_tracker.utterance_id
        )

        self.assertEqual(
            narration_tracker.utterance_id,
            10,
        )

        self.assertEqual(
            narration_tracker.clear_calls,
            0,
        )

        self.assertEqual(
            self.orchestrator
            .recover_calls,
            1,
        )

    def test_answer_interruption_does_not_advance_cursor(
        self,
    ):
        tracker = FakeTracker(
            utterance_id=1,
            inference_id="answer-123",
        )

        before = (
            self.orchestrator.cursor
            .sentence_index
        )

        self.controller.handle_answer_interrupted(
            orchestrator=self.orchestrator,
            answer_tracker=tracker,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .sentence_index,
            before,
        )

    def test_resume_submission_error_keeps_narration_ownership(
        self,
    ):
        narration_tracker = FakeTracker(
            utterance_id=10,
            inference_id=None,
        )

        result = (
            self.controller
            .handle_resume_submission_error(
                orchestrator=(
                    self.orchestrator
                ),
                narration_tracker=(
                    narration_tracker
                ),
            )
        )

        self.assertEqual(
            result.state,
            RecoveryState
            .RESUME_DELIVERY_UNCERTAIN,
        )

        self.assertEqual(
            narration_tracker
            .utterance_id,
            10,
        )

        self.assertEqual(
            narration_tracker
            .clear_calls,
            0,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .sentence_index,
            6,
        )

    def test_resume_submission_error_requires_ownership(
        self,
    ):
        narration_tracker = FakeTracker(
            utterance_id=None,
        )

        with self.assertRaises(
            RuntimeError
        ):
            self.controller.handle_resume_submission_error(
                orchestrator=(
                    self.orchestrator
                ),
                narration_tracker=(
                    narration_tracker
                ),
            )

    def test_confirm_resume_started_transitions_without_clearing_position(
        self,
    ):
        narration_tracker = FakeTracker(
            utterance_id=10,
        )

        self.controller.handle_resume_submission_error(
            orchestrator=self.orchestrator,
            narration_tracker=narration_tracker,
        )

        result = (
            self.controller
            .confirm_resume_started(
                inference_id=(
                    "resume-456"
                )
            )
        )

        self.assertEqual(
            result.state,
            RecoveryState
            .RESUME_DELIVERY_CONFIRMED,
        )

        self.assertEqual(
            result.snapshot.sentence_index,
            6,
        )

        self.assertEqual(
            narration_tracker
            .utterance_id,
            10,
        )

    def test_confirm_resume_not_delivered_allows_retry(
        self,
    ):
        narration_tracker = FakeTracker(
            utterance_id=10,
        )

        self.controller.handle_resume_submission_error(
            orchestrator=self.orchestrator,
            narration_tracker=narration_tracker,
        )

        result = (
            self.controller
            .confirm_resume_not_delivered()
        )

        self.assertEqual(
            result.state,
            RecoveryState
            .READY_TO_RETRY_RESUME,
        )

        self.assertEqual(
            result.snapshot.sentence_index,
            6,
        )

    def test_reset_returns_recovery_to_idle(
        self,
    ):
        narration_tracker = FakeTracker(
            utterance_id=10,
        )

        self.controller.handle_resume_submission_error(
            orchestrator=self.orchestrator,
            narration_tracker=narration_tracker,
        )

        self.controller.reset()

        self.assertEqual(
            self.recovery.state,
            RecoveryState.IDLE,
        )


if __name__ == "__main__":
    unittest.main()