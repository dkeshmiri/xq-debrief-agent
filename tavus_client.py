from typing import Any, Callable

from daily import (
    CallClient,
    Daily,
    EventHandler,
)

import os
import requests

class TavusEventHandler(EventHandler):
    """
    Minimal Daily/Tavus event handler.

    This is intentionally diagnostic only.
    Tavus does not perform XQ reasoning.
    """

    def __init__(
        self,
        tavus_client,
    ) -> None:
        super().__init__()
        self.tavus_client = tavus_client
        self.generation = tavus_client._connection_generation

    def on_call_state_updated(
        self,
        state: str,
    ) -> None:
        if self.generation != self.tavus_client._connection_generation:
            return

        print()
        print(
            "[DAILY CALL STATE]",
            state,
        )

        if state == "joined":
            self.tavus_client.connected = True

            print(
                "[TAVUS] Backend Daily client "
                "is fully joined."
            )

        elif state == "left":
            self.tavus_client.connected = False

        elif state == "error":
            self.tavus_client.connected = False

    def on_error(
        self,
        message: str,
    ) -> None:
        print()
        print("[DAILY ERROR]")
        print(message)

    def on_app_message(
        self,
        message: Any,
        sender: str,
    ) -> None:
        if self.generation != self.tavus_client._connection_generation:
            return

        print()
        print("[TAVUS APP MESSAGE]")
        print("Sender:", sender)
        print("Message:", message)
        # Forward canonical replica events only; aliases would double-count playback.
        if not isinstance(message, dict):
            return

        # Tavus protocol messages come from the PAL.
        # Never treat its audio as the user's voice.
        if message.get("message_type") in (
            "conversation",
            "system",
        ):
            self.tavus_client.mark_pal_participant(
                sender
            )

        event_type = message.get("event_type")

        playback_events = {
            "conversation.replica.started_speaking",
            "conversation.replica.stopped_speaking",
        }

        if event_type not in playback_events:
            return

        callback = self.tavus_client.on_playback_event

        if callback is not None:
            callback(message)

    def on_participant_joined(
        self,
        participant: Any,
    ) -> None:
        if self.generation != self.tavus_client._connection_generation:
            return
        self.tavus_client.listen_to_participant(
            participant
        )

    def on_participant_left(
        self,
        participant: Any,
        reason: str,
    ) -> None:
        if self.generation != self.tavus_client._connection_generation:
            return
        self.tavus_client.stop_listening(
            participant.get("id")
        )

class TavusClient:
    """
    Transport adapter between XQ and a Tavus Echo PAL.

    Responsibilities:
        - join a Tavus conversation
        - send approved text through Echo Mode
        - leave the conversation

    This class contains no assessment logic.
    """

    def __init__(self) -> None:
        self.call_client: CallClient | None = None

        self.conversation_id: str | None = None

        self.conversation_url: str | None = None

        self.connected = False

        self.on_playback_event: (
            Callable[[dict[str, Any]], None] | None
        ) = None

        self._daily_initialized = False
        self._connection_generation = 0

        # Voice input: PCM16 mono 16 kHz from the user.
        self.on_user_audio: (
            Callable[[str, bytes, int, int], None] | None
        ) = None

        self.on_user_audio_closed: (
            Callable[[str], None] | None
        ) = None

        # The bundled browser joins with this name. Unknown participants
        # are ignored even before the PAL announces its identity.
        self.voice_user_name = (
            os.getenv("XQ_VOICE_USER_NAME") or "XQ Family Member"
        )

        self.pal_participant_ids: set[str] = set()
        self.listening_participant_ids: set[str] = set()

        self.api_key = os.getenv("TAVUS_API_KEY")

        self.pal_id = os.getenv("TAVUS_PAL_ID")

    def create_conversation(
        self,
        conversation_name: str = "XQ Family Debrief",
    ) -> dict[str, Any]:
        """
        Create a fresh Tavus conversation for the configured PAL.

        Returns the conversation payload from Tavus and
        automatically joins the resulting Daily room.
        """

        if not self.api_key:
            raise RuntimeError(
                "TAVUS_API_KEY is not configured."
            )

        if not self.pal_id:
            raise RuntimeError(
                "TAVUS_PAL_ID is not configured."
            )

        response = requests.post(
            "https://tavusapi.com/v2/conversations",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
            },
            json={
                "pal_id": self.pal_id,
                "conversation_name": conversation_name,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        conversation_id = data.get(
            "conversation_id"
        )

        conversation_url = data.get(
            "conversation_url"
        )

        if not conversation_id:
            raise RuntimeError(
                "Tavus response did not include "
                "conversation_id."
            )

        if not conversation_url:
            raise RuntimeError(
                "Tavus response did not include "
                "conversation_url."
            )

        self.connect(
            conversation_url=conversation_url,
            conversation_id=conversation_id,
        )

        return data

    def connect(
        self,
        conversation_url: str,
        conversation_id: str,
    ) -> None:
        """
        Join an existing Tavus/Daily conversation.
        """

        cleaned_url = conversation_url.strip()
        cleaned_id = conversation_id.strip()

        if not cleaned_url:
            raise ValueError(
                "conversation_url cannot be empty."
            )

        if not cleaned_id:
            raise ValueError(
                "conversation_id cannot be empty."
            )

        if self.connected:
            raise RuntimeError(
                "TavusClient is already connected."
            )

        if not self._daily_initialized:
            Daily.init()
            self._daily_initialized = True

        self._connection_generation += 1
        handler = TavusEventHandler(self)

        self.call_client = CallClient(
            event_handler=handler
        )

        self.conversation_url = cleaned_url
        self.conversation_id = cleaned_id

        print()
        print("[TAVUS]")
        print("Joining conversation...")

        self.call_client.join(
            cleaned_url
        )

        print(
            "[TAVUS] Waiting for Daily join confirmation..."
        )

        print("[TAVUS] Join request sent.")

    def speak(
        self,
        text: str,
    ) -> None:
        """
        Send final approved text to Tavus Text Echo.
        """

        if not self.connected:
            raise RuntimeError(
                "TavusClient is not connected."
            )

        if self.call_client is None:
            raise RuntimeError(
                "Tavus call client is unavailable."
            )

        if self.conversation_id is None:
            raise RuntimeError(
                "Tavus conversation ID is unavailable."
            )

        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError(
                "Cannot send empty text to Tavus."
            )

        interaction = {
            "message_type": "conversation",
            "event_type": "conversation.echo",
            "conversation_id": (
                self.conversation_id
            ),
            "properties": {
                "modality": "text",
                "text": cleaned_text,
                "done": True,
            },
        }

        print()
        print("[TAVUS ECHO ABOUT TO SEND]")
        print(interaction)

        self.call_client.send_app_message(
            interaction
        )

        print("[TAVUS ECHO SENT]")

    def interrupt(self) -> None:
        """
        Interrupt the avatar's current speech
        without ending the conversation.
        """

        if not self.connected:
            raise RuntimeError(
                "TavusClient is not connected."
            )

        if self.call_client is None:
            raise RuntimeError(
                "Tavus call client is unavailable."
            )

        if self.conversation_id is None:
            raise RuntimeError(
                "Tavus conversation ID is unavailable."
            )

        interaction = {
            "message_type": "conversation",
            "event_type": "conversation.interrupt",
            "conversation_id": self.conversation_id,
        }

        print()
        print("[TAVUS INTERRUPT ABOUT TO SEND]")
        print(interaction)

        self.call_client.send_app_message(
            interaction
        )

        print("[TAVUS INTERRUPT SENT]")

    def end_conversation(self) -> None:
        """
        End the active Tavus conversation remotely,
        then disconnect the local Daily client.
        """

        if not self.api_key:
            raise RuntimeError(
                "TAVUS_API_KEY is not configured."
            )

        if not self.conversation_id:
            self.disconnect()
            return

        response = requests.post(
            f"https://tavusapi.com/v2/conversations/{self.conversation_id}/end",
            headers={
                "x-api-key": self.api_key,
            },
            timeout=30,
        )

        response.raise_for_status()

        self.disconnect()

    def disconnect(self) -> None:
        """
        Leave the active Tavus conversation.
        """

        self._connection_generation += 1
        call_client = self.call_client
        self.call_client = None

        if call_client is not None:
            try:
                call_client.leave()
            finally:
                call_client.release()

        self.connected = False
        self.conversation_id = None
        self.conversation_url = None

        for participant_id in tuple(
            self.listening_participant_ids
        ):
            self.stop_listening(participant_id)

        self.pal_participant_ids.clear()

        print()
        print("[TAVUS] Disconnected.")

    def status(self) -> dict[str, Any]:
        """
        Return transport status for Flask/UI diagnostics.
        """

        return {
            "connected": self.connected,
            "conversation_id_set": (
                self.conversation_id is not None
            ),
            "conversation_url_set": (
                self.conversation_url is not None
            ),
            "voice_listening_participants": sorted(
                self.listening_participant_ids
            ),
            "pal_participants": sorted(
                self.pal_participant_ids
            ),
        }

    # =====================================================
    # VOICE INPUT
    # =====================================================

    def listen_to_existing_participants(self) -> None:
        """
        Attach audio to participants who joined before
        the backend client did.

        Call from an application thread, not from a
        Daily event callback.
        """

        if self.call_client is None:
            raise RuntimeError(
                "Tavus call client is unavailable."
            )

        for key, participant in (
            self.call_client.participants().items()
        ):
            if key == "local":
                continue

            self.listen_to_participant(participant)

    def listen_to_participant(
        self,
        participant: Any,
    ) -> None:
        """
        Start receiving a remote participant's microphone,
        unless it is the PAL or not the configured user.
        """

        if self.call_client is None:
            return

        participant_id = participant.get("id")
        info = participant.get("info") or {}
        user_name = info.get("userName")

        if not participant_id or info.get("isLocal"):
            return

        if participant_id in self.pal_participant_ids:
            return

        if participant_id in self.listening_participant_ids:
            return

        if (
            self.voice_user_name is not None
            and user_name != self.voice_user_name
        ):
            print(
                "[XQ VOICE] Not listening to participant "
                f"{participant_id} (userName={user_name!r}); "
                "XQ_VOICE_USER_NAME is "
                f"{self.voice_user_name!r}."
            )
            return

        call_client = self.call_client
        call_client.set_audio_renderer(
            participant_id,
            lambda pid, audio, source: self._on_current_audio(
                call_client, pid, audio, source
            ),
            audio_source="microphone",
            sample_rate=16000,
            callback_interval_ms=20,
        )

        self.listening_participant_ids.add(participant_id)

        print(
            "[XQ VOICE] Listening to participant "
            f"{participant_id} (userName={user_name!r})."
        )

    def mark_pal_participant(
        self,
        participant_id: str,
    ) -> None:
        if (
            not participant_id
            or participant_id in self.pal_participant_ids
        ):
            return

        self.pal_participant_ids.add(participant_id)

        print(
            "[XQ VOICE] Participant "
            f"{participant_id} identified as the PAL."
        )

        self.stop_listening(participant_id)

    def stop_listening(
        self,
        participant_id: str | None,
    ) -> None:
        """
        Ignore a participant's audio from now on.

        The Daily renderer may still deliver frames;
        _on_participant_audio drops them.
        """

        if participant_id not in self.listening_participant_ids:
            return

        self.listening_participant_ids.discard(participant_id)

        callback = self.on_user_audio_closed

        if callback is not None:
            callback(participant_id)

    def _on_current_audio(self, call_client, participant_id, audio_data, audio_source):
        if call_client is self.call_client:
            self._on_participant_audio(participant_id, audio_data, audio_source)

    def _on_participant_audio(
        self,
        participant_id: str,
        audio_data: Any,
        audio_source: str,
    ) -> None:
        if participant_id not in self.listening_participant_ids:
            return

        callback = self.on_user_audio

        if callback is None:
            return

        callback(
            participant_id,
            audio_data.audio_frames,
            audio_data.sample_rate,
            audio_data.num_channels,
        )