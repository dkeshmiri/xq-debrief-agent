# Voice input

The Daily backend receives PCM16 audio from the browser participant, detects
speech, interrupts tracked narration, and waits for Tavus to confirm the stop.
Transcripts use the same guardrails, reasoner, validation, and answer playback as
typed questions. Matching answer completion replays the interrupted sentence.

## Settings

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `XQ_STT_MODEL` | `gpt-4o-transcribe` | OpenAI transcription model |
| `XQ_VOICE_USER_NAME` | `XQ Family Member` | Exact Daily participant name to receive audio from; the bundled browser uses this automatically |
| `XQ_VAD_BACKEND` | `daily` | Native speech detector; `energy` is available for tests |
| `XQ_VAD_THRESHOLD` | `0.6` | Speech confidence threshold in (0, 1] |
| `XQ_VOICE_END_SILENCE_MS` | `700` | Positive multiple of 10 ms |
| `XQ_QUESTION_TIMEOUT_SECONDS` | `30` | Finite, non-negative inactivity timeout; 0 disables it |

Unknown participants are ignored before the PAL announces itself. Tavus protocol
messages also mark PAL participants, invalidate their queued voice work, and
exclude their audio. This name filter is routing, not participant authentication.
For a custom frontend, join with the `voice_user_name` returned by session start.
Use headphones or browser echo cancellation to avoid hearing the PAL through
the user's microphone. The bundled call starts muted.

## Question behavior

- Speech can interrupt tracked narration, including a short gap before its start
  event. Speech during an answer or without tracked narration is ignored.
- A transcript containing only dismissal/filler phrases resumes narration without
  asking the reasoner. “Never mind, what about my EQ?” remains a question.
- Filler-only voice and typed input leave question mode open.
- Inactivity resumes narration with a short transition. Speech, transcription,
  and an active upload defer the timer. A microphone that stops delivering frames
  is flushed with endpoint silence during the question timeout check.
- Failed transcription or reasoning allows a full timeout to retry. Typing in
  the bundled UI refreshes the timer while editing continues.
- Session reset and participant departure invalidate queued and in-flight voice
  work. Uploads are tied to their session and question turn; concurrent uploads
  are rejected. A bounded worker queue prevents unlimited audio backlog.

## Routes

| Route | Behavior |
| --- | --- |
| `POST /api/question` | Typed question, dismissal, or filler |
| `POST /api/question/dismiss` | Resume the interrupted sentence |
| `POST /api/question/keepalive` | Refresh an open question's timeout |
| `POST /api/voice/audio` | One recorded utterance; raw body with supported audio MIME type, maximum 25 MiB |
| `GET /api/status` | Playback phase, recovery state, timer, voice worker and participants |

Uploads support WAV, WebM, OGG, MP3, M4A, and FLAC. A successful upload returns
`transcript` and `voice_result`. If Tavus has not confirmed interruption, the
endpoint returns a conflict instead of treating the upload as a completed question.

## Recovery and lifecycle

Interrupted answers release answer ownership and preserve the narration position.
The next tracked narration request replays that sentence. Recovery clears after
successful resubmission. If a resume send raises, ownership stays reserved until
a matching Tavus start confirms delivery; never resend blindly. End the session
if delivery remains uncertain and no start event arrives.

Delayed Daily callbacks and renderers from disconnected calls are ignored. Daily
clients are released on disconnect. Session end and profile changes reset the
voice timer, streams, diagnostics, and recovery state.

## Validation

The tests cover simulated live audio, HTTP uploads, interruption/answer/resume,
timeout, repeated recovery, old-session transcripts, participant departure,
muted streams, upload limits, and late transport callbacks. Real microphone,
browser permission, acoustic echo, and network delivery still need a human call.
