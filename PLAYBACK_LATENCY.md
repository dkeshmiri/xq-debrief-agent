# Playback latency investigation

Narration currently sends one sentence per completed Tavus Text Echo request
(`done: true`). The next sentence is submitted only after the previous matching,
non-interrupted stop event arrives. This preserves precise sentence resumption,
but places a transport/provider startup cycle between sentences.

There is no LLM call in the normal next-sentence path. The browser does not poll
to advance narration, and the question-mode timeout is not a sentence delay.
The global playback lock can add contention, and synchronous diagnostic printing
in the event callback is another possible local contributor under slow logging.

In a local 1,000-iteration benchmark, accepted stop-event handling through the
submission of the next sentence took approximately 0.037 ms median, 0.048 ms
p95, and 0.194 ms maximum. Transport was mocked and output captured; network,
provider work, real terminal I/O, and production contention were excluded.
The benchmark asserted that the cursor advanced and the next sentence was active.
These numbers are not a measurement of the audible gap in a live Tavus session.

## Measure a real session

After normal narration, GET `/api/playback/latency`. The last 100 narration
samples contain no speech text:

- `stop_event_to_submit_ms`: local delay from receipt of an accepted completion
  to submission of the next Echo, including lock wait and scheduling.
- `lock_wait_ms`: time from callback entry to acquiring the playback lock.
- `send_call_ms`: synchronous submission-call duration.
- `submit_to_start_event_ms`: elapsed time until the matching start event;
  includes transport, provider processing, and event delivery.
- `stop_to_start_event_ms`: combined server-observed transition interval.

Initial sentences have no preceding stop interval. Interrupted/resumed answers
are not part of this consecutive-narration measurement. Event timestamps do not
measure browser audio playout; use an audio recording to quantify audible gaps.
Pending measurements reset when the voice/session state resets.

## Recommendation

Keep Python. The measured local continuation path does not justify a rewrite.
Measure a real session before attributing the remaining delay to a specific
provider stage. If provider startup dominates, investigate bounded multi-sentence
utterances or supported streaming rather than accelerating local arithmetic.
Such a change needs new interruption and resumption semantics: a streamed turn
cannot be marked sentence-complete from a single turn-level completion event.
Do not queue untracked future speech or weaken stale-event checks to hide gaps.

If later profiling finds a genuinely CPU-heavy component, only that component
needs a native extension or separate service. The Flask UI, JSON import, family
repository, and debrief logic can remain Python. There is no universally fastest
language for an app dominated by external service latency.
