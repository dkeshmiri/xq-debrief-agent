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

The existing `.env` needs `OPENAI_API_KEY`, `TAVUS_API_KEY`, and `TAVUS_PAL_ID`.
Optional voice settings and behavior are in `VOICE_INPUT.md`.

## Test

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

Tests use fake external services; they do not need a running Tavus conversation.
The app uses a single in-process session, so run one server process. Multiple
workers would have independent playback and voice state.

The two supplied `*.patch` files describe earlier versions. Changes are already
applied to the source; do not apply those patches again.

## Assessment JSON Maker

Open `/json-maker` to turn assessment PDFs into family-oriented persona JSON.
Missing facts can be entered manually and saved with PIN **2020**. See
`JSON_MAKER.md` for draft handling, source review, and API details.
