"""Bounded narration timings, measured on one monotonic clock. No speech text."""
from collections import deque
from time import monotonic


class PlaybackLatency:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.samples = deque(maxlen=100)
        self.pending = None

    def reset_pending(self):
        self.pending = None

    def submitted(self, utterance_id, stopped_at=None, handler_entered_at=None):
        now = self.clock()
        self.pending = {"utterance_id": utterance_id, "submitted_at": now,
                        "stopped_at": stopped_at,
                        "lock_wait_ms": None if handler_entered_at is None else
                        round((handler_entered_at - stopped_at) * 1000, 3)}

    def sent(self, utterance_id):
        if self.pending and self.pending["utterance_id"] == utterance_id:
            self.pending["send_call_ms"] = round((self.clock() - self.pending["submitted_at"]) * 1000, 3)

    def started(self, utterance_id):
        if not self.pending or self.pending["utterance_id"] != utterance_id:
            return
        now = self.clock()
        pending = self.pending
        stopped = pending["stopped_at"]
        self.samples.append({
            "utterance_id": utterance_id,
            "stop_event_to_submit_ms": None if stopped is None else round((pending["submitted_at"] - stopped) * 1000, 3),
            "submit_to_start_event_ms": round((now - pending["submitted_at"]) * 1000, 3),
            "stop_to_start_event_ms": None if stopped is None else round((now - stopped) * 1000, 3),
            "send_call_ms": pending.get("send_call_ms"),
            "lock_wait_ms": pending["lock_wait_ms"],
        })
        self.pending = None

    def snapshot(self):
        return {"samples": list(self.samples), "pending": self.pending is not None,
                "note": "Server event timings, not measured audible gaps. Submission-to-start includes transport, provider processing and event delivery."}
