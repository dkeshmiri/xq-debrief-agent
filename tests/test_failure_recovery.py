import unittest

from failure_recovery import (
    FailureRecovery,
    PlaybackSnapshot,
    RecoveryReason,
    RecoveryState,
)


class FailureRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.recovery = FailureRecovery()

        self.snapshot = PlaybackSnapshot(
            section="DISC_NARRATIVE",
            sentence_index=6,
            utterance_id=10,
        )

    def test_starts_idle(self):
        self.assertEqual(
            self.recovery.state,
            RecoveryState.IDLE,
        )

        self.assertFalse(
            self.recovery.active
        )

        self.assertIsNone(
            self.recovery.record
        )

    def test_answer_interruption_preserves_position(self):
        self.recovery.begin_answer_interrupted(
            self.snapshot,
            answer_inference_id="answer-123",
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.ANSWER_INTERRUPTED,
        )

        self.assertTrue(
            self.recovery.active
        )

        self.assertEqual(
            self.recovery.record.reason,
            RecoveryReason.ANSWER_INTERRUPTED,
        )

        self.assertEqual(
            self.recovery.record.snapshot,
            self.snapshot,
        )

        self.assertEqual(
            self.recovery.record.answer_inference_id,
            "answer-123",
        )

    def test_interrupted_answer_becomes_ready_to_resume(self):
        self.recovery.begin_answer_interrupted(
            self.snapshot
        )

        recovered = (
            self.recovery
            .recover_from_answer_interruption()
        )

        self.assertEqual(
            recovered,
            self.snapshot,
        )

        self.assertEqual(
            recovered.sentence_index,
            6,
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.READY_TO_RESUME_NARRATION,
        )

    def test_uncertain_resume_does_not_allow_immediate_retry(self):
        self.recovery.begin_resume_delivery_uncertain(
            self.snapshot,
            resume_utterance_id=10,
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.RESUME_DELIVERY_UNCERTAIN,
        )

        self.assertNotEqual(
            self.recovery.state,
            RecoveryState.READY_TO_RETRY_RESUME,
        )

    def test_uncertain_resume_can_be_confirmed_started(self):
        self.recovery.begin_resume_delivery_uncertain(
            self.snapshot,
            resume_utterance_id=10,
        )

        recovered = (
            self.recovery
            .confirm_resume_delivery_started(
                "resume-inference-456"
            )
        )

        self.assertEqual(
            recovered,
            self.snapshot,
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.RESUME_DELIVERY_CONFIRMED,
        )

        self.assertEqual(
            self.recovery.record.resume_inference_id,
            "resume-inference-456",
        )

    def test_uncertain_resume_can_be_marked_not_delivered(self):
        self.recovery.begin_resume_delivery_uncertain(
            self.snapshot,
            resume_utterance_id=10,
        )

        recovered = (
            self.recovery
            .confirm_resume_not_delivered()
        )

        self.assertEqual(
            recovered.sentence_index,
            6,
        )

        self.assertEqual(
            self.recovery.state,
            RecoveryState.READY_TO_RETRY_RESUME,
        )

    def test_recovery_never_changes_snapshot(self):
        self.recovery.begin_answer_interrupted(
            self.snapshot
        )

        recovered = (
            self.recovery
            .recover_from_answer_interruption()
        )

        self.assertEqual(
            recovered.section,
            "DISC_NARRATIVE",
        )

        self.assertEqual(
            recovered.sentence_index,
            6,
        )

        self.assertEqual(
            recovered.utterance_id,
            10,
        )

    def test_second_recovery_cannot_start_while_active(self):
        self.recovery.begin_answer_interrupted(
            self.snapshot
        )

        with self.assertRaises(RuntimeError):
            self.recovery.begin_resume_delivery_uncertain(
                self.snapshot,
                resume_utterance_id=10,
            )

    def test_wrong_transition_is_rejected(self):
        self.recovery.begin_resume_delivery_uncertain(
            self.snapshot,
            resume_utterance_id=10,
        )

        with self.assertRaises(RuntimeError):
            self.recovery.recover_from_answer_interruption()

    def test_empty_confirmed_inference_id_is_rejected(self):
        self.recovery.begin_resume_delivery_uncertain(
            self.snapshot,
            resume_utterance_id=10,
        )

        with self.assertRaises(ValueError):
            self.recovery.confirm_resume_delivery_started(
                ""
            )

    def test_reset_clears_recovery(self):
        self.recovery.begin_answer_interrupted(
            self.snapshot
        )

        self.recovery.reset()

        self.assertEqual(
            self.recovery.state,
            RecoveryState.IDLE,
        )

        self.assertFalse(
            self.recovery.active
        )

        self.assertIsNone(
            self.recovery.record
        )


if __name__ == "__main__":
    unittest.main()