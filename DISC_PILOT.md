# XQ DISC pilot

Choose **Take the DISC pilot** on the product menu, or open `/pilot/disc`.
The option is enabled by default. Set `XQ_DISC_PILOT_ENABLED=0` and restart
to hide it and return 404 for every pilot endpoint.

The pilot is independent of Family, Workplace, saved personas, and prepared
presentations. It never selects or writes a persona, creates a debrief session,
or invokes the existing narrative classifiers. Birth Order remains unwired.

## Instrument and scores

`disc_pilot_scoring.py` owns the immutable `xq-disc-frequency-v1` item bank,
strict response validation, deterministic scoring, and report text. There are
24 statements (six per dimension), answered in Everyday and At work contexts.
Both contexts refer to the past three months. This implements the frequency
rating candidate from the roadmap; it does not reuse the forced-ranking v3
prototype's scores or impose its constant-sum constraint.

Answers: 0 Never, 1 Rarely, 2 Sometimes, 3 Often, 4 Very often.
Index = sum of six answers / 6 × 25, rounded half up for display and speech.
Exact integer totals and item counts remain in the report. Comparisons use
these totals, not rounded indices. Each dimension is independent. Feedback
describes the average response using the original anchors, including
“between sometimes and often,” without high/low trait bands, population
percentiles, type assignments, capability judgments, or stress inferences.
There is no compass projection: all four dimensions remain visible.

This instrument still needs participant research, reliability/validity
evaluation, and calibration before introducing population comparisons.
The participant interface uses direct behavioral feedback rather than
disclaimers. Changes to items, response options, or scoring require a new
version so stored answers cannot silently acquire a different meaning.

## Data and voice

Answers and current page are saved in `sessionStorage`, scoped to the browser
tab. Start again clears that draft. No participant name is collected and no
answers or reports are stored server-side. Download JSON includes the item
bank, response meanings, raw answers, totals, scores, and exact narration.
It is a pilot report format, not an imported-assessment persona file.

Graphs and narration consume the same server-generated report. Audio requests
submit the original answers; the server recomputes the section text rather
than accepting arbitrary client text or scores. Kokoro is instantiated only
when Listen is selected, with its own queue/worker separate from main debrief
playback. One pilot clip may be generated at a time. Stopping cancels browser
playback/request consumption; an in-flight synthesis may finish on the server.
The existing bounded Kokoro disk cache stores generated clips locally.
CPU capacity is shared across the app, so concurrent synthesis can still
compete for resources. Questionnaire and report calculations require no API.

## Verification

Run `.venv/bin/python -m unittest discover -s tests -p 'test_disc_pilot.py'`.
Tests cover score anchors, independent dimensions, rounding, both comparison
directions, equal scores, order invariance, malformed/incomplete submissions,
feature gating, narration/audio identity, failure retry, and timeout backpressure.
Use the product/startup/playback regression suites when changing registration.
