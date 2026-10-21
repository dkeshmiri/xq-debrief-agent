
class PlaybackEventTracker:
    """
    Track one outstanding Echo utterance.

    This class observes Tavus events. It does not send
    audio, advance the debrief, or call the orchestrator.
    """

    STARTED = "conversation.replica.started_speaking"
    STOPPED = "conversation.replica.stopped_speaking"

    def __init__(self):
        self.utterance_id = None
        self.inference_id = None

    def arm(self, utterance_id: int) -> None:
        if self.utterance_id is not None:
            raise RuntimeError(
                "A playback utterance is already pending."
            )

        self.utterance_id = utterance_id
        self.inference_id = None

    def handle_event(self, event: dict) -> int | None:
        """
        Return our utterance ID only after its matching
        Tavus turn stops without an interruption.

        Otherwise return None.
        """

        if self.utterance_id is None:
            return None

        event_type = event.get("event_type")
        inference_id = event.get("inference_id")

        if not isinstance(inference_id, str) or not inference_id:
            return None

        if event_type == self.STARTED:
            if self.inference_id is None:
                self.inference_id = inference_id

            return None

        if event_type != self.STOPPED:
            return None

        if inference_id != self.inference_id:
            return None

        properties = event.get("properties")

        if not isinstance(properties, dict):
            return None

        # Only an explicit False means normal completion.
        if properties.get("interrupted") is not False:
            self.clear()
            return None

        completed_id = self.utterance_id
        self.clear()

        return completed_id

    def cancel(self) -> str | None:
        """
        Cancel the outstanding utterance.

        Return its Tavus inference ID, if known,
        so a delayed stop event can be recognized.
        """

        canceled_inference_id = self.inference_id

        self.clear()

        return canceled_inference_id

    def clear(self) -> None:
        self.utterance_id = None
        self.inference_id = None