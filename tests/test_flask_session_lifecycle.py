
import unittest
from unittest.mock import patch

import app as app_module

from playback_event_tracker import PlaybackEventTracker


class TestFlaskSessionLifecycle(unittest.TestCase):

    def setUp(self):
        self.client = app_module.app.test_client()

        # Keep the real app's global state intact after each test.
        self.original_conversation_id = (
            app_module.active_tavus_conversation_id
        )
        self.original_tracker = app_module.playback_tracker

        app_module.active_tavus_conversation_id = (
            "test-conversation-123"
        )

        app_module.playback_tracker = PlaybackEventTracker()
        app_module.playback_tracker.arm(17)

    def tearDown(self):
        app_module.active_tavus_conversation_id = (
            self.original_conversation_id
        )
        app_module.playback_tracker = self.original_tracker

    def test_failed_shutdown_preserves_session_state(self):
        # Simulate Tavus reporting a shutdown failure.
        # No network request is made.
        with patch.object(
            app_module.tavus,
            "end_conversation",
            side_effect=RuntimeError("Simulated Tavus failure"),
        ) as end_call:

            response = self.client.post("/api/session/end")

        end_call.assert_called_once_with()

        self.assertEqual(response.status_code, 500)

        # Flask must not claim the session ended successfully.
        self.assertEqual(
            app_module.active_tavus_conversation_id,
            "test-conversation-123",
        )

        # Don't discard an outstanding playback association
        # when shutdown has not been confirmed.
        self.assertEqual(
            app_module.playback_tracker.utterance_id,
            17,
        )



    def test_successful_shutdown_clears_session_state(self):
        with patch.object(
            app_module.tavus,
            "end_conversation",
        ) as end_call:
            response = self.client.post("/api/session/end")

        end_call.assert_called_once_with()

        self.assertEqual(response.status_code, 200)

        self.assertIsNone(
            app_module.active_tavus_conversation_id
        )

        self.assertIsNone(
            app_module.playback_tracker.utterance_id
        )

        self.assertIsNone(
            app_module.playback_tracker.inference_id
        )

    def test_shutdown_can_be_retried_after_failure(self):
        with patch.object(
            app_module.tavus,
            "end_conversation",
            side_effect=[
                RuntimeError("Simulated Tavus failure"),
                None,
            ],
        ) as end_call:

            first_response = self.client.post(
                "/api/session/end"
            )

            self.assertEqual(
                first_response.status_code,
                500,
            )

            self.assertEqual(
                app_module.active_tavus_conversation_id,
                "test-conversation-123",
            )

            self.assertEqual(
                app_module.playback_tracker.utterance_id,
                17,
            )

            second_response = self.client.post(
                "/api/session/end"
            )

        self.assertEqual(end_call.call_count, 2)

        self.assertEqual(
            second_response.status_code,
            200,
        )

        self.assertIsNone(
            app_module.active_tavus_conversation_id
        )

        self.assertIsNone(
            app_module.playback_tracker.utterance_id
        )



    def test_selecting_person_creates_fresh_playback_state(self):
        # Persona selection is prohibited during an active Tavus session.
        # Clear the simulated session established by setUp().
        app_module.active_tavus_conversation_id = None

        previous_engine = app_module.engine
        previous_orchestrator = app_module.orchestrator
        previous_tracker = app_module.playback_tracker

        # The selected file must match an available persona.
        available = app_module.get_available_personas()
        self.assertTrue(available)

        filename = available[0]["file"]

        try:
            response = self.client.post(
                "/api/person/select",
                json={"file": filename},
            )

            self.assertEqual(response.status_code, 200)

            self.assertIsNot(
                app_module.engine,
                previous_engine,
            )

            self.assertIsNot(
                app_module.orchestrator,
                previous_orchestrator,
            )

            self.assertIsNot(
                app_module.playback_tracker,
                previous_tracker,
            )

            self.assertIs(
                app_module.orchestrator.engine,
                app_module.engine,
            )

            self.assertIsNone(
                app_module.playback_tracker.utterance_id
            )

        finally:
            # Restore the original application objects.
            app_module.engine = previous_engine
            app_module.orchestrator = previous_orchestrator
            app_module.playback_tracker = previous_tracker

if __name__ == "__main__":
    unittest.main()