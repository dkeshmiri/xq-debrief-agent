
import unittest
from unittest.mock import patch

import app as app_module


class TestFlaskSentencePlayback(unittest.TestCase):

    def setUp(self):
        self.client = app_module.app.test_client()

    def test_sends_only_first_sentence(self):
        narrative = (
            "Samuel's DISC pattern is Persuader. "
            "His natural D score is 72. "
            "His family interactions may reflect this."
        )

        with (
            patch.object(
                app_module.tavus,
                "connected",
                True,
            ),
            patch.object(
                app_module.engine,
                "get_current_content",
                return_value=narrative,
            ),
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
                "/api/debrief/sentence/test"
            )

        self.assertEqual(response.status_code, 200)

        speak.assert_called_once_with(
            "Samuel's DISC pattern is Persuader."
        )

        data = response.get_json()

        self.assertEqual(
            data["sentence_count"],
            3,
        )

        self.assertEqual(
            data["spoken"],
            "Samuel's DISC pattern is Persuader.",
        )

    def test_rejects_disconnected_tavus(self):
        with (
            patch.object(
                app_module.tavus,
                "connected",
                False,
            ),
            patch.object(
                app_module,
                "speak_text",
            ) as speak,
        ):
            response = self.client.post(
                "/api/debrief/sentence/test"
            )

        self.assertEqual(response.status_code, 409)
        speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()