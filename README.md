# XQ Family Debrief Agent

This directory contains the original debrief app plus voice interruption,
transcription, question dismissal, inactivity timeout, and playback recovery.
The `data`, `knowledge`, `narratives`, `templates`, and `static` directories are
required at runtime and were restored from the sibling `xq-family-debrief` project.

## Run

Run commands from this directory (the original data loaders use relative paths):

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open http://127.0.0.1:5000, select a person, and start a session. The call starts
muted; unmute in the call to interrupt narration and ask a question. Say
“never mind” or use the dismissal button to resume without generating an answer.

For a controlled demonstration, use **Pause and Enter Question Mode** in the
question card while the guide is narrating. The button waits for speech to stop,
then focuses the question field. Speak (with the call unmuted) or type a question,
or choose **Continue without a question** to resume the preserved narration.
The existing question inactivity timeout still applies.

The existing `.env` needs `OPENAI_API_KEY`, `TAVUS_API_KEY`, and `TAVUS_PAL_ID`.
Optional voice settings and behavior are in `VOICE_INPUT.md`.

## Test

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node --test tests/workspace.test.cjs tests/family.test.cjs
```

Tests use fake external services; they do not need a running Tavus conversation.
The app uses a single in-process session, so run one server process. Multiple
workers would have independent playback and voice state.

## Family comparisons

Open `/family` from the profile menu to compare two to four saved family members' DISC,
Driving Forces, and EQ facts, and optionally ask a guarded comparison question.
This workspace uses detached profile snapshots and leaves the individual debrief
and its inactivity timer intact. See [FAMILY_WORKSPACE.md](FAMILY_WORKSPACE.md) for
the integration boundary, stability checks, and the path to future family voice
sessions. The release 2 context prototype is available separately in
[experiments/family_context](experiments/family_context/README.md) and is not wired
into the app.

## Workplace coaching

Open `/business/`, `/business/debrief`, or `/business/team` for individual and
2–4-member workplace coaching. Import workplace reports at `/business/json-maker`.
The business experience has its own roster, drafts, and conversation state; it
shares the existing playback controls and keeps the question inactivity timeout.
It starts empty and does not copy household profiles. See
[BUSINESS_WORKSPACE.md](BUSINESS_WORKSPACE.md) for content selection, configuration,
the dedicated pilot option, and validation.

The two supplied `*.patch` files describe earlier versions. Changes are already
applied to the source; do not apply those patches again.

## Assessment JSON Maker

Open `/json-maker` to turn assessment PDFs into family-oriented persona JSON.
Missing facts can be entered manually and saved with PIN **2020**. See
`JSON_MAKER.md` for draft handling, source review, and API details.
