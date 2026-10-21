
import unittest
from unittest.mock import patch

import app as app_module

from debrief_state import DebriefState
from playback_event_tracker import PlaybackEventTracker


class TestPlaybackOwnership(unittest.TestCase):

    def setUp(self):
        self.client = app_module.app.test_client()

    def test_old_next_cannot_advance_during_tracked_speech(self):
        tracker = PlaybackEventTracker()
        tracker.arm(17)

        # Simulate an active tracked sentence. The old Next
        # route must neither advance the engine nor send Echo.
        with (
            patch.object(
                app_module,
                "playback_tracker",
                tracker,
            ),
            patch.object(
                app_module.engine,
                "get_current_state",
                return_value=DebriefState.DISC_NARRATIVE,
            ),
            patch.object(
                app_module.engine,
                "advance",
            ) as advance,
            patch.object(
                app_module,
                "speak_text",
            ) as speak,
            patch.object(
                app_module,
                "current_payload",
                return_value={},
            ),
        ):
            response = self.client.post(
                "/api/debrief/next"
            )

        print("HTTP Status:", response.status_code)
        print ("Error Response:", response.get_json())
        self.assertEqual(response.status_code, 409)
        advance.assert_not_called()
        speak.assert_not_called()

        # The tracked sentence must still be pending.
        self.assertEqual(tracker.utterance_id, 17)

    def test_old_routes_cannot_run_during_tracked_speech(self):
        tracker = PlaybackEventTracker()
        tracker.arm(17)

        requests = [
            ("/api/debrief/speak", None),
            ("/api/debrief/repeat", None),
            ("/api/debrief/restart", None),
            (
                "/api/question",
                {"question": "What is my D score?"},
            ),
        ]

        with (
            patch.object(
                app_module,
                "playback_tracker",
                tracker,
            ),
            patch.object(
                app_module,
                "speak_text",
            ) as speak,
            patch.object(
                app_module.engine,
                "advance",
            ) as advance,
            patch.object(
                app_module.engine,
                "reset",
            ) as reset,
            patch.object(
                app_module.engine,
                "enter_question_mode",
            ) as enter_question,
            patch.object(
                app_module.engine,
                "answer_question",
            ) as answer_question,
        ):
            for route, json_body in requests:
                response = self.client.post(
                    route,
                    json=json_body,
                )

                self.assertEqual(
                    response.status_code,
                    409,
                    msg=f"{route} was not blocked",
                )

        speak.assert_not_called()
        advance.assert_not_called()
        reset.assert_not_called()
        enter_question.assert_not_called()
        answer_question.assert_not_called()

        self.assertEqual(
            tracker.utterance_id,
            17,
        )

    def test_tracked_playback_cannot_start_during_untracked_speech(self):
        app_module.active_tavus_conversation_id = (
            "test-conversation-123"
        )

        with (
            patch.object(
                app_module.tavus,
                "connected",
                True,
            ),
            patch.object(
                app_module,
                "untracked_playback_active",
                True,
            ),
            patch.object(
                app_module,
                "speak_text",
            ) as speak,
        ):
            response = self.client.post(
                "/api/debrief/tracked/next"
            )

        self.assertEqual(
            response.status_code,
            409,
        )

        speak.assert_not_called()

if __name__ == "__main__":
    unittest.main()