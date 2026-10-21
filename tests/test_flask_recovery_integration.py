import unittest
from unittest.mock import MagicMock, patch

import app

from failure_recovery import PlaybackSnapshot, RecoveryState
from playback_event_tracker import PlaybackEventTracker


class FlaskRecoveryIntegrationTests(
    unittest.TestCase
):

    def setUp(self):
        self.original_index = (
            app.orchestrator.cursor.sentence_index
        )

    def tearDown(self):
        app.playback_tracker.clear()
        app.answer_playback_tracker.clear()

        app.retired_inference_ids.clear()

        app.failure_recovery.reset()

    def test_interrupted_answer_uses_recovery_not_normal_completion(
        self,
    ):
        """
        If Tavus reports that answer playback was interrupted:

        - recovery handles the failure
        - normal answer_finished() must NOT run
        - narration must NOT automatically resume
        """

        event = {
            "event_type":
                "conversation.replica.stopped_speaking",

            "inference_id":
                "answer-inference",

            "properties": {
                "interrupted": True,
            },
        }

        app.answer_playback_tracker.utterance_id = 1
        app.answer_playback_tracker.inference_id = (
            "answer-inference"
        )

        with (
            patch.object(
                app,
                "recovery_controller",
            ) as recovery,
            patch.object(
                app.orchestrator,
                "answer_finished",
            ) as answer_finished,
            patch.object(
                app,
                "speak_text",
            ) as speak_text,
        ):
            app.handle_tavus_playback_event(
                event
            )

        recovery.handle_answer_interrupted.assert_called_once()

        answer_finished.assert_not_called()

        speak_text.assert_not_called()

        self.assertEqual(
            app.orchestrator.cursor.sentence_index,
            self.original_index,
        )
    
    
    def test_resume_submission_error_enters_uncertain_recovery_without_resend(
        self,
    ):
        """
        If answer completion succeeds but submission of
        the resumed narration raises:

        - recovery records uncertain delivery
        - narration ownership remains intact
        - no second Echo is attempted
        """

        answer_stop = {
            "event_type":
                "conversation.replica.stopped_speaking",

            "inference_id":
                "answer-inference",

            "properties": {
                "interrupted": False,
            },
        }

        app.playback_tracker.clear()
        app.answer_playback_tracker.arm(1)

        resumed_turn = MagicMock()
        resumed_turn.utterance_id = 99
        resumed_turn.text = (
            "To continue where we left off..."
        )

        with (
            patch.object(
                app.orchestrator,
                "answer_finished",
                return_value=resumed_turn,
            ),
            patch.object(
                app,
                "PlaybackCoordinator",
            ) as coordinator_class,
            patch.object(
                app,
                "speak_text",
                side_effect=RuntimeError(
                    "Echo submission uncertain"
                ),
            ) as speak_text,
            patch.object(
                app,
                "recovery_controller",
            ) as recovery,
        ):
            coordinator = (
                coordinator_class.return_value
            )

            coordinator.register_utterance.side_effect = (
                lambda utterance_id:
                    app.playback_tracker.arm(
                        utterance_id
                    )
            )

            app.handle_tavus_playback_event({
                "event_type":
                    PlaybackEventTracker.STARTED,

                "inference_id":
                    "answer-inference",
            })

            app.handle_tavus_playback_event(
                answer_stop
            )

        recovery.handle_resume_submission_error.assert_called_once()

        self.assertEqual(
            speak_text.call_count,
            1,
        )

        self.assertEqual(
            app.playback_tracker.utterance_id,
            99,
        )

        self.assertEqual(
            app.orchestrator.cursor.sentence_index,
            self.original_index,
        )


        coordinator.register_utterance.assert_called_once_with(
            99
        )

    def test_uncertain_resume_started_confirms_delivery_without_duplicate_echo(
        self,
    ):
        """
        If an uncertain resume later produces a Tavus
        STARTED event:

        - recovery marks the delivery as confirmed
        - the existing narration tracker owns the turn
        - no duplicate Echo is submitted
        """

        start_event = {
            "event_type":
                "conversation.replica.started_speaking",

            "inference_id":
                "resume-inference",

            "properties": {},
        }

        app.playback_tracker.utterance_id = 99

        with (
            patch.object(
                app,
                "recovery_controller",
            ) as recovery,
            patch.object(
                app,
                "speak_text",
            ) as speak_text,
        ):
            app.failure_recovery.begin_resume_delivery_uncertain(
                PlaybackSnapshot(None, self.original_index, 99),
                resume_utterance_id=99,
            )

            app.handle_tavus_playback_event(
                start_event
            )

        recovery.confirm_resume_started.assert_called_once_with(
            inference_id="resume-inference"
        )

        speak_text.assert_not_called()

        self.assertEqual(
            app.playback_tracker.utterance_id,
            99,
        )


if __name__ == "__main__":
    unittest.main()