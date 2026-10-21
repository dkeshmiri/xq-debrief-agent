import unittest

from playback_event_tracker import PlaybackEventTracker


class TestAnswerPlayback(unittest.TestCase):

    def test_answer_completes_independently(self):
        narration = PlaybackEventTracker()
        answer = PlaybackEventTracker()

        narration.arm(8)

        narration.handle_event({
            "event_type": narration.STARTED,
            "inference_id": "narration-123",
        })

        # Simulate confirmed cancellation.
        canceled_id = narration.cancel()

        self.assertEqual(
            canceled_id,
            "narration-123",
        )

        # The answer uses its own tracker.
        answer.arm(1)

        answer.handle_event({
            "event_type": answer.STARTED,
            "inference_id": "answer-456",
        })

        # A delayed stop from narration must not
        # complete the answer.
        stale_result = answer.handle_event({
            "event_type": answer.STOPPED,
            "inference_id": "narration-123",
            "properties": {
                "interrupted": True,
            },
        })

        self.assertIsNone(stale_result)
        self.assertEqual(answer.utterance_id, 1)

        # The actual answer finishes normally.
        completed = answer.handle_event({
            "event_type": answer.STOPPED,
            "inference_id": "answer-456",
            "properties": {
                "interrupted": False,
            },
        })

        self.assertEqual(completed, 1)
        self.assertIsNone(answer.utterance_id)
        self.assertIsNone(narration.utterance_id)