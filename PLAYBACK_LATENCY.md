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

## Logging and portability update — 2026-10-23

Roster paths inside this project are now saved relative to the project root.
Loading resolves those paths against the code location, not the shell's working
directory. Explicit absolute paths to external data remain supported. The copied
machine-specific roster entry has been corrected. Knowledge-directory loading
uses the same project-root convention. Startup and profile listing were verified
with the working directory set to `/`.

Playback and Tavus diagnostics use a bounded, nonblocking logging queue. Routine
diagnostics are DEBUG (off by default); warnings remain available through a
background listener. A full diagnostic queue drops records instead of delaying
playback. Speech text and incoming message payloads are no longer logged in the
normal playback diagnostics. No speech scheduling, completion, interruption,
recovery, or experimental Birth Order wiring changed.

### Controlled before/after test

Run: `.venv/bin/python -B scripts/benchmark_playback.py --output result.json`

The benchmark starts at TavusEventHandler.on_app_message and ends after the next
Echo has been submitted and the handler returns. Unlike the API's callback timer,
it includes logging before the app callback. It asserts exactly one next
submission, the expected sentence text, finalized Echo, and cursor/tracker state
on every iteration. Transport is mocked. Fast-output runs use a sink with no
added delay; the slow-output case deliberately sleeps 1 ms per stdout write.
These are local callback timings, not audible or provider measurements.

| Output scenario | Samples | Before median / p95 | After median / p95 |
| --- | ---: | ---: | ---: |
| Fast sink | 1,000 | 0.1224 / 0.2179 ms | 0.1009 / 0.1709 ms |
| Simulated slow sink | 100 | 24.7124 / 24.9360 ms | 0.0980 / 0.1757 ms |

Raw results: `benchmarks/playback_baseline.json` and
`benchmarks/playback_after.json`. Runs were sequential, not a randomized
statistical experiment. The fast-sink difference is small and subject to normal
host noise; maximum time did not improve (0.4618 to 5.1544 ms).
The slow-sink test demonstrates removal of output-induced blocking, not a claim
that the real terminal adds 25 ms. These results do not show elimination of the
reported 500–1,000+ ms audible gaps. A live audio recording plus server timings
is still needed to quantify those gaps.

Validation: 388 Python tests pass, including relocation/reload of a newly saved
profile, existing interruption/stale-event/recovery tests, and a deliberately
blocked logging consumer with a full queue. Startup from outside the repository
also passed. No live paid-provider session was run for this benchmark.
