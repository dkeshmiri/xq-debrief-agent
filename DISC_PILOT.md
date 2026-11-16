# XQ DISC pilot

Choose **Behavior frequency** (`/pilot/disc`), **Scenario ranking**
(`/pilot/disc/scenarios`), or **Hybrid assessment** (`/pilot/disc/hybrid`)
on the product menu. Each page also links to the other options.
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

## Scenario ranking instrument

`disc_scenario_scoring.py` implements `xq-disc-scenario-v2`: 16 Natural and
16 Adapted groups, 32 total. `content/disc_scenarios_v2.json` retains 16
situations from the original bank, each paired with distinct workplace wording
for both its Adapted stem and all four alternatives. The pairs preserve the
DISC option mappings and cover decisions, change, collaboration, learning,
support, prioritization, and follow-through. Source metadata remains with the
bank. Participants rank four alternatives for Natural preferences and Adapted behavior in their
current work role over the past three months. Every group must contain all
four option identities exactly once. Display order rotates across groups and
contexts; scoring always follows identities, never screen positions.

Rank weights are 3, 1, -1, -3. The index is
`50 + 50 * raw_total / (3 * group_count)`. Exact totals sum to zero per context;
unrounded indices sum to 200. With 16 groups the raw range is −48 to +48
and the normalization denominator is 48. Display/speech round half up independently, so
rounded sums can differ from 200. First/last counts accompany raw totals.

These indices describe relative preference across alternatives. Graphs and
narration use relative-emphasis language rather than frequency anchors or
imported-assessment bands. Equal totals retain ties, including all-four ties.
Changes between contexts compare exact totals; no stress or capability is
inferred. Population comparisons would require further measurement research.

The instruments have separate version IDs, tab storage keys, API paths,
and download filenames. Existing frequency answers remain compatible.
The shared route factory recomputes each instrument's own report for speech.
Existing debrief sessions, profile files, and presentation modes are untouched.

Scenario controls support click or keyboard activation, undo, clear, review,
and refresh/resume, including partial rankings. All four individual scores
remain visible. No compass or automatic style-category assignment is added.

Run `.venv/bin/python -m unittest discover -s tests -p 'test_disc_scenarios.py'`
for known rankings, normalization, ties, rounding, malformed answers, version
isolation, feature gating, and spoken/visible report agreement.

Version 2 rejects version 1 submissions and starts a fresh questionnaire when
an old draft is present. The original `disc_scenarios_v1.json` is retained for
historical reference; existing downloaded reports are not rewritten. Frequency
pilot versioning and its 48 ratings are unchanged. The questionnaire export
includes both wordings so answers retain their context for later analysis.

Distinct wording is intended to reduce obvious repetition; its effect on
response bias and the equivalence of the paired forms still require participant
research. No claim of improved measurement validity is made by the math tests.

## Hybrid instrument

`disc_hybrid_scoring.py` owns `xq-disc-hybrid-v1`. Its separate frozen bank,
`content/disc_hybrid_v1.json`, includes four paired situations (decisions,
change, joining a group, and responsibility) with distinct workplace wording.
Participants complete four Natural and four Adapted situations: 32 independent
frequency ratings and eight first-approach choices in total. Natural concerns
usual everyday behavior; Adapted concerns actual current-role behavior. Both
refer to the past three months. Each situation asks how often each of its four
behaviors is used, then which approach the participant would start with.

Each dimension receives four ratings per context. Its score is
`25 * sum(ratings) / 4`, rounded half up for graphs and speech; exact totals and
counts are retained. Each dimension has its own 0–100 scale. All four can reach
100 together. For example, D ratings `[4,4,4,4]` produce 100 and C ratings
`[4,4,4,3]` produce 94, even when D is selected first in every situation.

First choices contribute counts out of four and a separate summary, with ties
preserved. They have **zero numerical effect** on frequency scores. The report
combines these two views descriptively rather than applying an uncalibrated
blend or treating preference order as behavioral intensity. Graphs label the
frequency scale and show first-choice counts separately. Narration states both
using the same server report; audio is recomputed from the submitted answers.
No high/low trait bands, population percentiles, or TTI score equivalence is
introduced. This short form still needs participant research and calibration;
unit tests verify the arithmetic and integration, not psychometric accuracy.

The shared pilot gate covers all hybrid routes. Drafts use
`xq-disc-hybrid-pilot`, exports use `xq-disc-hybrid-report.json`, and submissions
require the hybrid version and complete answers. Existing instruments and
debriefs retain their own scoring. New scoring or wording requires a new
instrument version.

Run `.venv/bin/python -m unittest discover -s tests -p 'test_disc_hybrid.py'`
for independent score anchors, simultaneous high scores, first-choice isolation,
ties, rounding, malformed submissions, gating, and report/audio agreement.
