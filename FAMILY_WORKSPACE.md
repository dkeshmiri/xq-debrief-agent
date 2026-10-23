# Family workspace integration

Open `/family`, or choose **Explore family comparisons** from the profile menu.
The conversation sidebar opens this workspace in a new tab to keep an ongoing
video call connected. Select two to four enabled profiles to compare their saved DISC,
Driving Forces, and EQ facts. Optionally ask a question naming one or more assessment domains.

## Release 1: group comparison

The family UI selects 2–4 distinct enabled profiles and shows each person's
original scores in its own table column. Roles are labels, not fixed slots. The
roster can contain more than four people; the cap applies to the active comparison.
No synthetic Son or Daughter profiles are added to the real roster. Add their
validated assessments through the existing import workflow. Confirm age and
instrument suitability before comparing minors' reports with adult reports.

- `POST /api/family/group/compare` accepts `person_ids` (2–4 IDs). It returns
  member identities, per-person assessment tables, and all deterministic pairs.
- `POST /api/family/group/question` accepts those IDs plus `question`. It performs
  at most one model request, with approved knowledge and each member's score
  wording included once. Four members yield six local pair packets, not six
  model requests. Only the explicitly requested assessment domains are supplied.
- Generated observations name their member IDs. Unknown references, omitted
  selected members, malformed output, and violations of the existing pair
  response validators are rejected. Pair and group reasoning share one semaphore.
- Experimental request options are rejected. Birth-order and gender-role metadata
  do not enter the production model context, even if present in a persona record.

`family_group.py` is deterministic; `family_group_reasoner.py` handles bounded
structured interpretation. The existing two-person endpoints remain compatible.
The app's single-person narration and timeout behavior are unchanged.

## Integration boundary

The web app already uses `FamilyRepository` for the roster. The console's
`ComparisonEngine`, `ComparisonReasoner`, context builder, and response validator
already implement two-person comparisons. The family workspace reuses these
components through an independent Flask blueprint in `family_routes.py`.

- `GET /api/family` returns enabled member identities, without file paths.
- `POST /api/family/compare` accepts `person_a_id` and `person_b_id` and returns a
  deterministic assessment comparison. No model request is made.
- `POST /api/family/question` accepts the same IDs and a `question`. It uses the
  existing domain routing, approved comparison context, and response validation.
  Rejected or incomplete answers return 422; unavailable reasoning returns 503.

The integration callbacks in `app.py` copy selected profiles while holding the
existing playback lock. That lock is released before comparison reasoning or
any model request. A comparison never changes the active person, debrief engine,
orchestrator, sentence cursor, voice generation, playback trackers, or question
inactivity deadline. Generated family answers are text only.

The reasoner is created only on an explicit family-question request. The model
client has a 30-second timeout and automatic retries disabled. One family model
request per process is allowed at a time; overlapping requests return 409.
Assessment facts remain available after reasoning failure. There is no separate
family database, roster copy, or automatic background generation to maintain.

Selecting another person clears displayed results and requires a new comparison,
so an answer cannot remain labeled as belonging to a different selection. All output
is inserted as text, and the tables use captions and row/column headings.

## Stability checks

`tests/test_family_routes.py` covers exact facts, invalid/disabled selections,
detached profile snapshots, response rejection, service recovery, concurrent
requests, and preservation of an active debrief and its timeout. In particular,
family reasoning must not hold the playback lock or prevent activity polling.
`tests/family.test.cjs` covers selection, stale-result clearing, question binding,
and failed/duplicate requests.

The manual pause button uses the existing `/api/debrief/interrupt` route. The
browser waits for the matching stop acknowledgement before focusing the question
field. The manual-route integration test in `tests/test_voice_input.py` verifies
that no microphone event is needed, unrelated or stale events cannot advance the
cursor, question mode opens after acknowledgement, the inactivity timer remains
armed, and answering resumes the preserved sentence. External Tavus and model
services are simulated in these tests; they do not replace a live-call smoke test.

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/workspace.test.cjs tests/family.test.cjs
.venv/bin/python -m unittest discover -s experiments/family_context/tests -v
```

## Release 2: present, standalone, disconnected

The prototype lives in `experiments/family_context/` and has its own schema,
explicit local runner, synthetic example, documentation, and tests. Production
code does not import it; there are no app routes, UI switches, hidden activation
settings, or hooks into scoring or prompts. Its master switch and independent
birth-order/gender-role opt-ins apply only to the standalone runner.

It validates optional confirmed upbringing reports and prepares neutral discussion
prompts. It does not generate traits, claim causal explanations, adjust scores,
or call a model. See `experiments/family_context/README.md` for local test commands
and the checks required before considering production wiring.

## Next integration stage

Keep family questions outside the single-person playback orchestrator until we
introduce an explicit session-owned comparison context: all selected person IDs, detached
profiles, and a generation ID bound to each answer. Only then should family audio
share interruption, timeout, answer completion, stale-event rejection, and recovery
handling. Add lifecycle tests for each of those paths before enabling family voice
playback. Avoid changing `engine.persona` or the repository's active person to
answer a comparison question.

The current app still owns one in-process conversation. The family semaphore is
also process-local; deploying multiple workers requires shared session ownership
and request coordination as a separate change.
