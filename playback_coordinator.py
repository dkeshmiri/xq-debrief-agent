
from conversation_orchestrator import ConversationOrchestrator
from playback_event_tracker import PlaybackEventTracker


class PlaybackCoordinator:
    """
    Connect Tavus playback events to the XQ orchestrator.

    The application submits the next Echo after this coordinator accepts
    completion. This class only tracks state; it does not perform transport.
    """

    def __init__(
        self,
        orchestrator: ConversationOrchestrator,
        tracker: PlaybackEventTracker,
    ) -> None:
        self.orchestrator = orchestrator
        self.tracker = tracker

    def register_utterance(self, utterance_id: int) -> None:
        """
        Register the narration utterance expected to play.
        """

        active = self.orchestrator.cursor.active_utterance

        if active is None:
            raise RuntimeError(
                "No narration utterance is active."
            )

        if active.id != utterance_id:
            raise RuntimeError(
                "Utterance ID does not match active narration."
            )

        self.tracker.arm(utterance_id)

    def handle_playback_event(self, event: dict) -> bool:
        """
        Return True only when a matching narration
        utterance has completed successfully.
        """

        completed_id = self.tracker.handle_event(event)

        if completed_id is None:
            return False

        return self.orchestrator.narration_finished(
            completed_id
        )
