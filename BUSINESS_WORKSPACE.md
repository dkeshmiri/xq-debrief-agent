# Workplace coaching workspace

The normal app now includes these entry points:

- `/business/`: workplace profiles and assessment import navigation.
- `/business/debrief`: individual communication and leadership coaching.
- `/business/team`: assessment comparisons for 2–4 selected colleagues.
- `/business/json-maker`: PDF extraction, review, workplace language generation,
  and saving to the workplace roster.

The family profile menu also links to Workplace coaching. Business starts empty;
family profiles are never automatically copied or relabeled. Import reviewed
workplace assessments and supply a workplace role such as Team lead or Designer.
The original scores, labels, and reported clusters are retained.

## Shared implementation, separate state

`workspace_experience.py` selects the content explicitly; family remains the
default for existing callers. Business has independently editable templates,
narrative libraries, knowledge applications, and reasoning instructions under
`templates/business/` and `content/business/`.

The same browser controllers and playback endpoints serve both experiences.
`data-api-base="/business"` scopes all business browser requests and navigation.
Draft restoration uses a different session-storage key. Business feedback,
leadership, meeting, and handoff questions can resolve to integrated assessment
context without requiring the user to type an assessment name.

`workspace_host.py` lazily loads another instance of the existing Flask app under
`/business`. It gives that instance its own module globals, repository, engine,
orchestrator, playback lock/trackers, voice pipeline, timeout watchdog, activity,
and conversation ID. It does not change process environment or switch a global
family/business mode while a call is running. Both applications use the same
implementation rather than copied playback code. The native Daily SDK is
initialized once per process while each workspace creates its own call client.

The main app retains its original family roster and profile directory. The business
instance uses `data/business/roster.json`, `data/business/personas/`, and
`data/business/assessment_drafts/`; these runtime files are git-ignored. An empty
business roster has no fabricated assessment and cannot start playback. Its first
saved profile establishes the default roster member. Selecting a profile creates
the actual business debrief engine.

Business-generated profiles have `experience: "business"`. Business profile loading
and publication reject family profiles; the family save callback rejects business
profiles. Filename selection is constrained to each workspace's own roster.
Existing JSON field names such as `family_role`, `value_to_family`, and
`family_applications` remain compatibility keys; in a business-scoped profile they
hold workplace roles, team contributions, and workplace applications. Those
internal names do not appear as family labels in the business UI.

## Narration, reasoning, and imports

Both deterministic narration and Q&A score wording select the business content
pack. This includes every measured DISC dimension, Driving Force, EQ dimension,
and composite range. Numeric classifiers and calculation logic are shared.
The extraction stage continues to preserve original report facts; the language
stage uses workplace instructions instead of converting work examples into
household advice. Stored report findings remain distinct from suggested coaching
applications.

Business prompts focus on feedback, handoffs, meetings, shared priorities,
leadership communication, and conflict repair. They prohibit fabricated colleagues,
demographic trait inference, diagnoses, performance predictions, and promotion or
hiring suitability judgments. Assessment facts remain separate from cautious
applications. The experimental birth-order module remains disconnected.

## Configuration and dedicated pilot option

Run `.venv/bin/python app.py` as usual and open
`http://127.0.0.1:5000/business/`.

Optional settings:

- `XQ_BUSINESS_DATA_DIR`: separate workplace runtime storage directory.
- `XQ_BUSINESS_TAVUS_PAL_ID`: a dedicated workplace guide; otherwise the configured
  `TAVUS_PAL_ID` is used for the existing Echo-based delivery.
- `XQ_BUSINESS_VOICE_USER_NAME`: browser participant name, defaulting to
  `XQ Workplace Participant`.
- The existing `XQ_QUESTION_TIMEOUT_SECONDS` applies to both experiences; its
  default remains 30 seconds.

For a separate process, run `.venv/bin/python business_app.py` and open
`http://127.0.0.1:5001/business/`. `XQ_BUSINESS_PORT` changes that port. This is an
alternative deployment, not an additional writer to the same roster: use one
process per workspace data directory. Business and family session ownership is
still in-process; adding multiple workers requires a shared session design.

These entry points preserve the facilitated-prototype access model. Namespaced
application state and storage do not introduce employee authentication, tenant
permissions, or manager access policies. Those are separate requirements before
an organizational rollout beyond a controlled pilot.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/workspace.test.cjs tests/family.test.cjs
.venv/bin/python -m unittest discover -s experiments/family_context/tests -v
```

Business tests cover empty-roster entry points, namespaced routes, separate state,
profile and draft separation, import/generate/publish, exact scores and wording
bands, all business library text values, ordinary workplace coaching questions,
four-person group context, shared SDK initialization, and manual pause → question
→ answer → resume while a family session is retained. Provider calls are simulated.
Live Tavus delivery and real model output still require a configured smoke test.

## Second-person perspective

The JSON maker uses the OpenAI Responses API twice: once to extract factual report
content, then to generate participant-facing language. Extraction preserves names,
labels, scores, citations, and source findings. Language generation in both
workspaces uses the shared `narrative_perspective.py` contract: every sentence and
list item addresses the assessed participant as you/your. Communication guidance
is phrased as what you can request from others, rather than addressing a colleague
about you. References to colleagues remain distinct from the participant.

The application checks generated language before assembling a profile. It retries
once on a perspective failure, then rejects the generation without saving or
changing reviewed facts. Individual live Q&A uses the same instructions and a
bounded retry; failed answers are replaced with a second-person retry message
before speech. These are deterministic wording checks, not a guarantee of complete
semantic understanding. Provider calls in automated tests are simulated.

Workplace narration libraries and legacy score-summary headings address you
directly. When older workplace profiles are loaded, explicit participant names
and singular gendered references in descriptive prose are adapted in memory;
identity, numeric facts, saved JSON, and source evidence remain unchanged. Older
communication do/don't source guidance remains input data for the reasoner to
paraphrase under the new output contract. Team comparisons retain named-member
attribution because they discuss multiple selected people rather than conducting
an individual debrief.
