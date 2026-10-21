import unittest
from unittest.mock import MagicMock, patch

import app


class TestFlaskInterruption(unittest.TestCase):

    def setUp(self):
        self.tracker = app.PlaybackEventTracker()
        self.tracker.arm(8)

        self.tracker.handle_event({
            "event_type": self.tracker.STARTED,
            "inference_id": "speech-123",
        })

        self.fake_orchestrator = MagicMock()
        self.fake_orchestrator.cursor.sentence_index = 7

        self.patches = [
            patch.object(app, "retired_inference_ids", set()),
            patch.object(
                app,
                "playback_tracker",
                self.tracker,
            ),
            patch.object(
                app,
                "orchestrator",
                self.fake_orchestrator,
            ),
            patch.object(
                app,
                "interruption_pending",
                True,
            ),
            patch.object(
                app,
                "interrupted_inference_id",
                "speech-123",
            ),
        ]

        for item in self.patches:
            item.start()

        self.addCleanup(self.stop_patches)

    def stop_patches(self):
        for item in reversed(self.patches):
            item.stop()

    def test_matching_stop_acknowledges_interruption(self):
        app.handle_tavus_playback_event({
            "event_type": self.tracker.STOPPED,
            "inference_id": "speech-123",
            "properties": {
                "interrupted": True,
            },
        })

        self.fake_orchestrator.interrupt.assert_called_once()

        self.assertFalse(
            app.interruption_pending
        )

        self.assertIsNone(
            app.interrupted_inference_id
        )

        self.assertIsNone(
            self.tracker.utterance_id
        )

    def test_unrelated_stop_does_not_interrupt(self):
        app.handle_tavus_playback_event({
            "event_type": self.tracker.STOPPED,
            "inference_id": "different-speech",
            "properties": {
                "interrupted": False,
            },
        })

        self.fake_orchestrator.interrupt.assert_not_called()

        self.assertTrue(
            app.interruption_pending
        )

        self.assertEqual(
            self.tracker.utterance_id,
            8,
        )

    def test_interruption_preserves_sentence_index(self):
        original_index = (
            self.fake_orchestrator.cursor.sentence_index
        )

        app.handle_tavus_playback_event({
            "event_type": self.tracker.STOPPED,
            "inference_id": "speech-123",
            "properties": {
                "interrupted": False,
            },
        })

        self.assertEqual(
            self.fake_orchestrator.cursor.sentence_index,
            original_index,
        )

    def test_playback_routes_blocked_during_interruption(self):
        client = app.app.test_client()

        routes = [
            "/api/debrief/next",
            "/api/debrief/speak",
            "/api/debrief/repeat",
            "/api/debrief/restart",
            "/api/debrief/tracked/next",
            "/api/question",
        ]

        for route in routes:
            with self.subTest(route=route):
                response = client.post(
                    route,
                    json={
                        "question": "What does my DISC score mean?"
                    },
                )

                self.assertEqual(
                    response.status_code,
                    409,
                )

                self.assertIn(
                    "interruption",
                    response.get_json()["error"].lower(),
                )

                self.assertTrue(
                    app.interruption_pending
                )

                self.assertEqual(
                    self.tracker.utterance_id,
                    8,
                )

                self.fake_orchestrator.interrupt.assert_not_called()
