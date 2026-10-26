"""Offline stop-event-to-next-Echo benchmark. Transport and speech synthesis are mocked."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from conversation_orchestrator import ConversationOrchestrator
from debrief_state import DebriefState
from playback_event_tracker import PlaybackEventTracker
from tavus_client import TavusEventHandler

class OutputSink(io.StringIO):
    def __init__(self, delay):
        super().__init__()
        self.delay = delay
    def write(self, text):
        if self.delay:
            time.sleep(self.delay)
        return len(text)

def measure(iterations, delay):
    engine = Mock()
    engine.get_current_state.return_value = DebriefState.DISC_NARRATIVE
    engine.get_current_content.return_value = "First benchmark sentence. Second benchmark sentence."
    app.engine = engine
    app.tavus.connected = True
    app.tavus.conversation_id = "benchmark"
    app.active_tavus_conversation_id = "benchmark"
    app.tavus.call_client = Mock()
    app.tavus.mark_pal_participant = Mock()
    handler = TavusEventHandler(app.tavus)
    samples = []
    sink = OutputSink(delay)
    with contextlib.redirect_stdout(sink):
        for index in range(iterations):
            app.orchestrator = ConversationOrchestrator(engine)
            app.playback_tracker = PlaybackEventTracker()
            app.answer_playback_tracker = PlaybackEventTracker()
            app.retired_inference_ids.clear()
            app.untracked_playback_active = False
            app.untracked_inference_id = None
            app.interruption_pending = False
            app.voice_interrupt_requested_at = None
            with app.playback_lock:
                app.submit_next_tracked_sentence()
            event = {"message_type": "conversation", "conversation_id": "benchmark",
                     "inference_id": f"turn-{index}", "event_type": PlaybackEventTracker.STARTED}
            handler.on_app_message(event, "pal")
            app.tavus.call_client.send_app_message.reset_mock()
            event.update(event_type=PlaybackEventTracker.STOPPED, properties={"interrupted": False})
            start = time.perf_counter()
            handler.on_app_message(event, "pal")
            samples.append((time.perf_counter()-start)*1000)
            assert app.orchestrator.cursor.sentence_index == 1
            assert app.playback_tracker.utterance_id is not None
            app.tavus.call_client.send_app_message.assert_called_once()
            sent = app.tavus.call_client.send_app_message.call_args.args[0]
            assert sent["properties"]["text"] == "Second benchmark sentence."
            assert sent["properties"]["done"] is True
    ordered = sorted(samples)
    return {"iterations":iterations, "stdout_write_delay_ms":delay*1000,
            "median_ms":round(statistics.median(samples),4),
            "p95_ms":round(ordered[int(.95*(len(ordered)-1))],4),
            "max_ms":round(max(samples),4)}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    results = {"scope":"Full inbound callback through next Echo submission; mocked transport, no provider or audible timing.",
               "normal_output":measure(1000, 0), "slow_output":measure(100, .001)}
    args.output.write_text(json.dumps(results, indent=2)+"\n")
    print(json.dumps(results, indent=2))

