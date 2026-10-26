# Local speech and the XQ robot

Family and Workplace now default to local Kokoro-82M speech. Tavus Presentation
Mode remains separate. Restart the app after updating.

## Setup on another machine

Install Python 3.12 or 3.13, then run `python3.12 scripts/setup_kokoro.py` from the
project. This creates `.venv-kokoro` and downloads the official ONNX model and
voice pack to `models/kokoro`. These large files and the runtime are git-ignored.
The main application can keep using its existing Python environment, including
Python 3.14. No model downloads happen during conversations.

The persistent speech worker starts loading when the conversation page opens.
Warm-up explicitly loads the model, even when the greeting is already cached.
Its default voice is `af_heart` (American
English). Set `XQ_KOKORO_VOICE` to another installed voice to change it.
`XQ_KOKORO_PYTHON` can point to an alternative compatible Python executable.
`XQ_KOKORO_THREADS` controls CPU inference threads (default up to 4, capped by
available logical CPUs). Four outperformed two and eight on this laptop.
`XQ_PLAYBACK_PROVIDER=tavus` restores the previous debrief transport if needed.
Presentation Mode always uses Tavus regardless of that setting.

## Behavior

- Idle: quiet float and occasional blink.
- Talking: mouth movement follows the audio's measured amplitude.
- Listening: question mode is open. The microphone remains off until the
  operator chooses **Record a question**; choose **Stop and send question** to
  upload it. Recording automatically stops at 60 seconds.
- Thinking: a question/transcription API request is underway.

Reduced-motion preferences disable animation while retaining text labels.
Typed questions remain available. Voice transcription and question reasoning
still require internet, as does JSON Maker. Saved-profile narration needs no
cloud speech service. Record only after pausing into question mode; automatic
Daily microphone interruption belongs to the optional Tavus transport.

The application pre-synthesizes two upcoming sentences, caches up to sixteen
clips in memory, and stores up to 256 MB of generated audio in `.cache/kokoro`.
Cached clips bypass the synthesis queue. New foreground speech cancels unused
queued lookahead so questions/resumption do not wait behind it. In-flight
inference cannot be preempted. Interrupting or ending also cancels queued lookahead.
These local clips contain spoken profile information; delete that folder to clear
them. Cache keys include the text, voice, and model, so edits generate fresh audio.
It advances only after the browser acknowledges actual playback
completion. Interruptions preserve the current sentence. Session and utterance
IDs reject stale completions; ending a session stops browser audio. A failed
synthesis or browser audio error requires ending and restarting the session.

## Prepare an investor demonstration

The initial CPU configuration synthesized more slowly than speech playback.
Thread tuning brought one representative 4.3-second clip from 5.80 seconds down
to 4.18 seconds (three uncached trials per configuration). This is only a small
benchmark and leaves little headroom; long or complex speech can still lag. Generate
the chosen profile's deterministic narration ahead of time:

```
.venv/bin/python scripts/prepare_local_voice.py data/personas/samuel.json
```

For Workplace, supply its profile path and add `--experience business`.
This can take several minutes but uses no speech API. The next debrief reuses the
cached clips. New question answers and resumption phrases may still need fresh
synthesis. Changing profile text or the configured voice requires preparation
again. This is a latency mitigation, not a promise of instant uncached speech.

Reproduce the CPU comparison with `.venv-kokoro/bin/python scripts/profile_kokoro.py`,
setting `XQ_KOKORO_THREADS` to the desired thread count. Raw measurements are in
`benchmarks/kokoro_threads_2.json`, `kokoro_threads_4.json`, and `kokoro_threads_8.json`.
At measurement time, Linux reported a power-saving CPU preference, turbo disabled,
and a 1.3 GHz maximum. No system power settings were changed. Testing a performance
power profile is a separate next step, with heat and battery tradeoffs.

## Components

Kokoro-82M weights: Apache-2.0; kokoro-onnx wrapper: MIT. The phonemizer includes
eSpeak NG, which has its own GPL license. Review bundled runtime and voice/model
licenses when packaging a distribution. The robot is original SVG/CSS in this
repository, with no external avatar assets or CDN dependencies.

Sources: https://huggingface.co/hexgrad/Kokoro-82M and
https://github.com/thewh1teagle/kokoro-onnx.
