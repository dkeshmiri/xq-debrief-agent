
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from playback_coordinator import PlaybackCoordinator
from playback_event_tracker import PlaybackEventTracker


class TestPlaybackCoordinator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = Mock()

        # Simulate the orchestrator's active sentence.
        self.orchestrator.cursor.active_utterance = (
            SimpleNamespace(id=17)
        )

        self.orchestrator.narration_finished.return_value = True

        self.tracker = PlaybackEventTracker()

        self.coordinator = PlaybackCoordinator(
            orchestrator=self.orchestrator,
            tracker=self.tracker,
        )

    def started(self, inference_id="inference-123"):
        return {
            "event_type": "conversation.replica.started_speaking",
            "inference_id": inference_id,
        }

    def stopped(
        self,
        inference_id="inference-123",
        interrupted=False,
    ):
        return {
            "event_type": "conversation.replica.stopped_speaking",
            "inference_id": inference_id,
            "properties": {
                "interrupted": interrupted,
            },
        }

    def test_matching_completion_advances_once(self):
        self.coordinator.register_utterance(17)

        self.assertFalse(
            self.coordinator.handle_playback_event(
                self.started()
            )
        )

        self.orchestrator.narration_finished.assert_not_called()

        self.assertTrue(
            self.coordinator.handle_playback_event(
                self.stopped()
            )
        )

        self.orchestrator.narration_finished.assert_called_once_with(
            17
        )

    def test_duplicate_stop_does_not_advance_twice(self):
        self.coordinator.register_utterance(17)

        self.coordinator.handle_playback_event(self.started())
        self.coordinator.handle_playback_event(self.stopped())

        self.assertFalse(
            self.coordinator.handle_playback_event(
                self.stopped()
            )
        )

        self.orchestrator.narration_finished.assert_called_once_with(
            17
        )

    def test_interrupted_stop_does_not_advance(self):
        self.coordinator.register_utterance(17)

        self.coordinator.handle_playback_event(self.started())

        self.assertFalse(
            self.coordinator.handle_playback_event(
                self.stopped(interrupted=True)
            )
        )

        self.orchestrator.narration_finished.assert_not_called()

    def test_unrelated_stop_does_not_advance(self):
        self.coordinator.register_utterance(17)

        self.coordinator.handle_playback_event(self.started())

        self.assertFalse(
            self.coordinator.handle_playback_event(
                self.stopped(inference_id="another-inference")
            )
        )

        self.orchestrator.narration_finished.assert_not_called()

        # The original speaking turn can still complete.
        self.assertTrue(
            self.coordinator.handle_playback_event(
                self.stopped()
            )
        )

        self.orchestrator.narration_finished.assert_called_once_with(
            17
        )

    def test_rejects_wrong_utterance_id(self):
        with self.assertRaises(RuntimeError):
            self.coordinator.register_utterance(18)

        self.assertIsNone(self.tracker.utterance_id)

    def test_rejects_registration_without_active_sentence(self):
        self.orchestrator.cursor.active_utterance = None

        with self.assertRaises(RuntimeError):
            self.coordinator.register_utterance(17)

        self.assertIsNone(self.tracker.utterance_id)

    def test_rejects_second_pending_registration(self):
        self.coordinator.register_utterance(17)

        with self.assertRaises(RuntimeError):
            self.coordinator.register_utterance(17)

        self.assertEqual(self.tracker.utterance_id, 17)

    def test_stale_completion_cannot_force_cursor_forward(self):
        self.coordinator.register_utterance(17)

        self.coordinator.handle_playback_event(self.started())

        # Simulate the real orchestrator rejecting a completion
        # because its utterance was interrupted or invalidated.
        self.orchestrator.narration_finished.return_value = False

        self.assertFalse(
            self.coordinator.handle_playback_event(
                self.stopped()
            )
        )

        self.orchestrator.narration_finished.assert_called_once_with(
            17
        )


if __name__ == "__main__":
    unittest.main()