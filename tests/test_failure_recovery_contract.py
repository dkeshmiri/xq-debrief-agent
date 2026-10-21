import unittest

from failure_recovery import (
    FailureRecovery,
    PlaybackSnapshot,
    RecoveryState,
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


class FakeCursor:
    def __init__(
        self,
        *,
        section="DISC_NARRATIVE",
        sentence_index=6,
        utterance_id=10,
    ):
        self.section = section
        self.sentence_index = sentence_index
        self.active_utterance_id = utterance_id

        self.complete_calls = 0

    def complete(self):
        self.complete_calls += 1
        self.sentence_index += 1


class FakeOrchestrator:
    def __init__(self):
        self.cursor = FakeCursor()
        self.phase = "answering"

        self.answer_finished_calls = 0
        self.exit_question_calls = 0

    def answer_finished(self):
        self.answer_finished_calls += 1
        self.phase = "narrating"

    def exit_question_mode(self):
        self.exit_question_calls += 1
        self.phase = "narrating"


class FailureRecoveryContractTests(
    unittest.TestCase
):

    def setUp(self):
        self.recovery = FailureRecovery()

        self.orchestrator = (
            FakeOrchestrator()
        )

        self.answer_tracker = FakeTracker(
            utterance_id=1,
            inference_id="answer-123",
        )

        self.narration_tracker = FakeTracker(
            utterance_id=10,
            inference_id=None,
        )

    def snapshot(self):
        return PlaybackSnapshot(
            section=self.orchestrator.cursor.section,
            sentence_index=(
                self.orchestrator.cursor
                .sentence_index
            ),
            utterance_id=(
                self.orchestrator.cursor
                .active_utterance_id
            ),
        )

    def test_answer_interruption_can_clear_answer_ownership_without_advancing_cursor(
        self,
    ):
        before = self.snapshot()

        self.recovery.begin_answer_interrupted(
            before,
            answer_inference_id=(
                self.answer_tracker
                .inference_id
            ),
        )

        recovered = (
            self.recovery
            .recover_from_answer_interruption()
        )

        self.answer_tracker.clear()
        self.orchestrator.exit_question_mode()

        after = self.snapshot()

        self.assertEqual(
            recovered,
            before,
        )

        self.assertEqual(
            after,
            before,
        )

        self.assertEqual(
            self.answer_tracker.clear_calls,
            1,
        )

        self.assertIsNone(
            self.answer_tracker.utterance_id
        )

        self.assertIsNone(
            self.answer_tracker.inference_id
        )

        self.assertEqual(
            self.orchestrator.phase,
            "narrating",
        )

        self.assertEqual(
            self.orchestrator.cursor.complete_calls,
            0,
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            6,
        )

    def test_answer_recovery_does_not_complete_narration_sentence(
        self,
    ):
        before_index = (
            self.orchestrator.cursor
            .sentence_index
        )

        self.recovery.begin_answer_interrupted(
            self.snapshot()
        )

        self.recovery.recover_from_answer_interruption()

        self.answer_tracker.clear()
        self.orchestrator.exit_question_mode()

        self.assertEqual(
            self.orchestrator.cursor
            .sentence_index,
            before_index,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .complete_calls,
            0,
        )

    def test_uncertain_resume_keeps_narration_ownership(
        self,
    ):
        before = self.snapshot()

        self.recovery.begin_resume_delivery_uncertain(
            before,
            resume_utterance_id=(
                self.narration_tracker
                .utterance_id
            ),
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.RESUME_DELIVERY_UNCERTAIN,
        )

        self.assertEqual(
            self.narration_tracker
            .utterance_id,
            10,
        )

        self.assertEqual(
            self.narration_tracker
            .clear_calls,
            0,
        )

        self.assertEqual(
            self.snapshot(),
            before,
        )

    def test_uncertain_resume_must_not_retry_before_resolution(
        self,
    ):
        self.recovery.begin_resume_delivery_uncertain(
            self.snapshot(),
            resume_utterance_id=10,
        )

        can_retry = (
            self.recovery.state
            == RecoveryState.READY_TO_RETRY_RESUME
        )

        self.assertFalse(
            can_retry
        )

        self.assertEqual(
            self.narration_tracker
            .utterance_id,
            10,
        )

    def test_confirmed_started_keeps_existing_narration_ownership(
        self,
    ):
        before = self.snapshot()

        self.recovery.begin_resume_delivery_uncertain(
            before,
            resume_utterance_id=10,
        )

        recovered = (
            self.recovery
            .confirm_resume_delivery_started(
                "resume-456"
            )
        )

        self.assertEqual(
            recovered,
            before,
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.RESUME_DELIVERY_CONFIRMED,
        )

        self.assertEqual(
            self.narration_tracker
            .utterance_id,
            10,
        )

        self.assertEqual(
            self.narration_tracker
            .clear_calls,
            0,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .complete_calls,
            0,
        )

    def test_confirmed_not_delivered_allows_retry_but_does_not_advance_cursor(
        self,
    ):
        before = self.snapshot()

        self.recovery.begin_resume_delivery_uncertain(
            before,
            resume_utterance_id=10,
        )

        recovered = (
            self.recovery
            .confirm_resume_not_delivered()
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.READY_TO_RETRY_RESUME,
        )

        self.assertEqual(
            recovered,
            before,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .sentence_index,
            6,
        )

        self.assertEqual(
            self.orchestrator.cursor
            .complete_calls,
            0,
        )

    def test_recovery_never_calls_normal_answer_completion_path(
        self,
    ):
        self.recovery.begin_answer_interrupted(
            self.snapshot()
        )

        self.recovery.recover_from_answer_interruption()

        self.answer_tracker.clear()
        self.orchestrator.exit_question_mode()

        self.assertEqual(
            self.orchestrator
            .answer_finished_calls,
            0,
        )

    def test_recovery_never_clears_narration_tracker_during_answer_recovery(
        self,
    ):
        self.recovery.begin_answer_interrupted(
            self.snapshot()
        )

        self.recovery.recover_from_answer_interruption()

        self.answer_tracker.clear()
        self.orchestrator.exit_question_mode()

        self.assertEqual(
            self.narration_tracker
            .utterance_id,
            10,
        )

        self.assertEqual(
            self.narration_tracker
            .clear_calls,
            0,
        )


if __name__ == "__main__":
    unittest.main()