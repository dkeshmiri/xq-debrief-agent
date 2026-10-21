
import threading
import unittest
from unittest.mock import patch

import app


class TestSessionStartRace(unittest.TestCase):

    def test_second_start_rejected_while_first_is_connecting(self):
        first_started = threading.Event()
        release_first = threading.Event()
        calls = []
        first_result = {}

        def fake_create():
            calls.append("create")

            if len(calls) == 1:
                first_started.set()
                if not release_first.wait(timeout=5):
                    raise TimeoutError("Test connection timed out.")

            return {
                "conversation_id": f"test-{len(calls)}",
                "conversation_url": "https://example.test/room",
            }

        def first_request():
            with app.app.test_client() as client:
                first_result["response"] = client.post(
                    "/api/session/start"
                )

        with (
            patch.object(app, "active_tavus_conversation_id", None),
            patch.object(app, "session_ending", False),
            patch.object(app, "session_starting", False, create=True),
            patch.object(
                app.tavus,
                "create_conversation",
                side_effect=fake_create,
            ),
            patch.object(
                app,
                "wait_for_tavus_connection",
                return_value=True,
            ),
            patch.object(
                app,
                "current_payload",
                return_value={},
            ),
        ):
            worker = threading.Thread(target=first_request)
            worker.start()

            try:
                self.assertTrue(
                    first_started.wait(timeout=3),
                    "First request never started.",
                )

                with app.app.test_client() as client:
                    second = client.post("/api/session/start")

                self.assertEqual(second.status_code, 409)
                self.assertEqual(len(calls), 1)

            finally:
                release_first.set()
                worker.join(timeout=5)

            self.assertFalse(worker.is_alive())
            self.assertEqual(
                first_result["response"].status_code,
                200,
            )

    def test_profile_switch_blocked_while_session_starts(self):
        with (
            patch.object(app, "session_starting", True),
            patch.object(app, "session_ending", False),
            patch.object(
                app,
                "active_tavus_conversation_id",
                None,
            ),
        ):
            with app.app.test_client() as client:
                response = client.post(
                    "/api/person/select",
                    json={"file": "jennifer.json"},
                )

            self.assertEqual(
                response.status_code,
                409,
            )

            self.assertTrue(
                app.session_starting
            )

def test_failed_start_releases_starting_flag_but_keeps_created_session_reserved(self):
    with (
        patch.object(
            app,
            "active_tavus_conversation_id",
            None,
        ),
        patch.object(
            app,
            "session_starting",
            False,
        ),
        patch.object(
            app,
            "session_ending",
            False,
        ),
        patch.object(
            app.tavus,
            "create_conversation",
            return_value={
                "conversation_id": "created-session",
                "conversation_url": "https://example.test/room",
            },
        ),
        patch.object(
            app,
            "wait_for_tavus_connection",
            side_effect=RuntimeError(
                "Backend connection failed."
            ),
        ),
    ):
        with app.app.test_client() as client:
            response = client.post(
                "/api/session/start"
            )

        self.assertEqual(
            response.status_code,
            500,
        )

        self.assertFalse(
            app.session_starting
        )

        self.assertEqual(
            app.active_tavus_conversation_id,
            "created-session",
        )

        with app.app.test_client() as client:
            second = client.post(
                "/api/session/start"
            )

        self.assertEqual(
            second.status_code,
            409,
        )