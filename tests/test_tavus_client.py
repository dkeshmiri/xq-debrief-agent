
import unittest
from unittest.mock import Mock
from unittest.mock import MagicMock

from tavus_client import TavusClient, TavusEventHandler


class TestTavusClient(unittest.TestCase):

    def setUp(self):
        self.client = TavusClient()

        # Simulate an already-connected Daily client.
        # No real network connection is made.
        self.client.call_client = Mock()
        self.client.connected = True
        self.client.conversation_id = "test-conversation-123"

    def test_echo_sends_exactly_once(self):
        self.client.speak(
            "Samuel's natural D score is 72."
        )

        self.client.call_client.send_app_message.assert_called_once()

        interaction = (
            self.client.call_client
            .send_app_message.call_args.args[0]
        )

        self.assertEqual(
            interaction["event_type"],
            "conversation.echo",
        )

        self.assertEqual(
            interaction["conversation_id"],
            "test-conversation-123",
        )

        self.assertEqual(
            interaction["properties"]["text"],
            "Samuel's natural D score is 72.",
        )

        self.assertTrue(
            interaction["properties"]["done"]
        )

    def test_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            self.client.speak("   ")

        self.client.call_client.send_app_message.assert_not_called()

    def test_rejects_disconnected_client(self):
        self.client.connected = False

        with self.assertRaises(RuntimeError):
            self.client.speak("Hello.")

        self.client.call_client.send_app_message.assert_not_called()

    
    def test_replica_playback_events_reach_callback(self):
        received = []

        self.client.on_playback_event = received.append

        handler = TavusEventHandler(self.client)

        started = {
            "event_type": "conversation.replica.started_speaking",
            "inference_id": "inference-123",
        }

        stopped = {
            "event_type": "conversation.replica.stopped_speaking",
            "inference_id": "inference-123",
            "properties": {"interrupted": False},
        }

        handler.on_app_message(started, "tavus")
        handler.on_app_message(stopped, "tavus")

        self.assertEqual(received, [started, stopped])

    def test_playback_aliases_do_not_duplicate_events(self):
        received = []

        self.client.on_playback_event = received.append

        handler = TavusEventHandler(self.client)

        events = [
            {
                "event_type": "conversation.replica.started_speaking",
                "inference_id": "inference-123",
            },
            {
                "event_type": "conversation.pal.started_speaking",
                "inference_id": "inference-123",
            },
            {
                "event_type": "conversation.started_speaking",
                "inference_id": "inference-123",
                "properties": {"role": "replica"},
            },
        ]

        for event in events:
            handler.on_app_message(event, "tavus")

        self.assertEqual(len(received), 1)

        self.assertEqual(
            received[0]["event_type"],
            "conversation.replica.started_speaking",
        )

    def test_interrupt_sends_correct_message(self):
        client = TavusClient()

        client.connected = True
        client.conversation_id = "test-conversation"

        fake_call = MagicMock()
        client.call_client = fake_call

        client.interrupt()

        fake_call.send_app_message.assert_called_once_with({
            "message_type": "conversation",
            "event_type": "conversation.interrupt",
            "conversation_id": "test-conversation",
        })

if __name__ == "__main__":
    unittest.main()

class TestVoiceTransportLifecycle(unittest.TestCase):
    def test_late_events_from_disconnected_client_are_ignored(self):
        client = TavusClient()
        client.call_client = Mock()
        handler = TavusEventHandler(client)
        transport = client.call_client
        client.disconnect()
        transport.release.assert_called_once()
        client.call_client = Mock()
        client.connected = True
        client.on_playback_event = Mock()
        handler.on_call_state_updated("left")
        handler.on_participant_joined({"id": "old", "info": {"userName": client.voice_user_name}})
        handler.on_app_message({"event_type": "conversation.replica.started_speaking"}, "old")
        self.assertTrue(client.connected)
        client.call_client.set_audio_renderer.assert_not_called()
        client.on_playback_event.assert_not_called()

    def test_late_renderer_from_previous_call_is_ignored(self):
        client = TavusClient()
        client.call_client = Mock()
        client.on_user_audio = Mock()
        client.listen_to_participant({"id": "user", "info": {"userName": client.voice_user_name}})
        renderer = client.call_client.set_audio_renderer.call_args.args[1]
        client.call_client = Mock()
        renderer("user", Mock(), "microphone")
        client.on_user_audio.assert_not_called()
