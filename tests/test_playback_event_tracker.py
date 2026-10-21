
import unittest

from playback_event_tracker import PlaybackEventTracker


class TestPlaybackEventTracker(unittest.TestCase):

    def setUp(self):
        self.tracker = PlaybackEventTracker()

    def started(self, inference_id="inference-123"):
        return {
            "event_type": "conversation.replica.started_speaking",
            "inference_id": inference_id,
            "message_type": "conversation",
            "turn_idx": 0,
        }

    def stopped(
        self,
        inference_id="inference-123",
        interrupted=False,
    ):
        return {
            "event_type": "conversation.replica.stopped_speaking",
            "inference_id": inference_id,
            "message_type": "conversation",
            "properties": {
                "duration": 6.401,
                "interrupted": interrupted,
            },
            "turn_idx": 0,
        }

    def test_normal_completion_returns_our_utterance_id(self):
        self.tracker.arm(17)

        self.assertIsNone(
            self.tracker.handle_event(self.started())
        )

        self.assertEqual(
            self.tracker.handle_event(self.stopped()),
            17,
        )

        self.assertIsNone(self.tracker.utterance_id)
        self.assertIsNone(self.tracker.inference_id)

    def test_duplicate_stop_cannot_complete_twice(self):
        self.tracker.arm(17)
        self.tracker.handle_event(self.started())

        self.assertEqual(
            self.tracker.handle_event(self.stopped()),
            17,
        )

        self.assertIsNone(
            self.tracker.handle_event(self.stopped())
        )

    def test_interrupted_speech_does_not_complete(self):
        self.tracker.arm(17)
        self.tracker.handle_event(self.started())

        self.assertIsNone(
            self.tracker.handle_event(
                self.stopped(interrupted=True)
            )
        )

        self.assertIsNone(self.tracker.utterance_id)

    def test_unmatched_stop_does_not_complete(self):
        self.tracker.arm(17)
        self.tracker.handle_event(self.started())

        self.assertIsNone(
            self.tracker.handle_event(
                self.stopped(inference_id="other-inference")
            )
        )

        self.assertEqual(self.tracker.utterance_id, 17)

        self.assertEqual(
            self.tracker.handle_event(self.stopped()),
            17,
        )

    def test_stop_without_start_does_not_complete(self):
        self.tracker.arm(17)

        self.assertIsNone(
            self.tracker.handle_event(self.stopped())
        )

        self.assertEqual(self.tracker.utterance_id, 17)

    def test_missing_interruption_status_is_not_completion(self):
        self.tracker.arm(17)
        self.tracker.handle_event(self.started())

        event = self.stopped()
        del event["properties"]["interrupted"]

        self.assertIsNone(
            self.tracker.handle_event(event)
        )

        self.assertIsNone(self.tracker.utterance_id)

    def test_cannot_arm_two_utterances(self):
        self.tracker.arm(17)

        with self.assertRaises(RuntimeError):
            self.tracker.arm(18)

    def test_clear_discards_pending_utterance(self):
        self.tracker.arm(17)
        self.tracker.handle_event(self.started())

        self.tracker.clear()

        self.assertIsNone(
            self.tracker.handle_event(self.stopped())
        )

    def test_cancel_preserves_inference_id(self):
        tracker = PlaybackEventTracker()

        tracker.arm(8)

        tracker.handle_event({
            "event_type": tracker.STARTED,
            "inference_id": "tavus-speech-123",
        })

        canceled_id = tracker.cancel()

        self.assertEqual(
            canceled_id,
            "tavus-speech-123",
        )

        self.assertIsNone(
            tracker.utterance_id
        )

        self.assertIsNone(
            tracker.inference_id
        )

    def test_late_stop_cannot_complete_canceled_sentence(self):
        tracker = PlaybackEventTracker()

        tracker.arm(8)

        tracker.handle_event({
            "event_type": tracker.STARTED,
            "inference_id": "old-speech",
        })

        tracker.cancel()

        result = tracker.handle_event({
            "event_type": tracker.STOPPED,
            "inference_id": "old-speech",
            "properties": {
                "interrupted": False,
            },
        })

        self.assertIsNone(result)        

if __name__ == "__main__":
    unittest.main()