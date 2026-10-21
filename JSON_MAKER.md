# Assessment JSON Maker

Open `/json-maker` from the debrief console. The workflow is:

1. Choose up to three PDFs for the **same person** and enter their family role.
2. Extract and review names, date, Natural/Adapted DISC, twelve Driving Forces,
   cluster memberships, and all eight EQ values. Source page references and
   comprehensive report-section findings are available below the score fields.
3. Correct or enter missing facts by hand. Enter PIN **2020** and click **Save
   changes**. Scores must be 0–100; age is optional. A blank means unknown, not 0.
4. Confirm the saved review, generate family-oriented language, and download JSON.

The PIN is checked on the server. Generation reads the saved review, never
client-supplied replacement scores. Each save records changed fields, previous
values, new values, timestamp, and revision. The PIN itself is not stored or
logged. Stale revisions are rejected to prevent one window overwriting another.
The last draft in the current browser tab is restored on reload. **Reload saved
review** discards unsaved edits.

If required facts are missing, generation produces an explicitly labeled
`.draft.json` with nulls. It is **not valid for the debrief engine**. Complete the
missing facts and regenerate for a schema-validated persona. Missing age is
omitted because the existing schema makes it optional. The supplied Talent
Insights sample has no EQ section; its EQ values must not be guessed.

The final persona has the Samuel JSON structure. Scores, style, role, identity,
and metadata are assembled from reviewed facts in Python; the language model
only supplies family-oriented narrative fields. Source findings outside that
structure (such as behavioral hierarchy and time wasters) remain available in
**Download reviewed extraction** rather than being discarded or changing the
persona schema. New application IDs are generated for person and assessment.
Nothing is added to the family roster or overwrites existing personas automatically.

## Configuration and storage

- Uses the existing `OPENAI_API_KEY` on the server.
- `XQ_IMPORT_MODEL` defaults to `gpt-5.6`, matching the existing reasoner.
- `XQ_IMPORT_OVERRIDE_PIN` defaults to `2020`; set it to change the operator PIN.
- Extracted reviews and override history are saved under `data/assessment_drafts/`,
  excluded from Git. They contain personal assessment data; PDFs are not saved.
- The API sends the complete selected PDFs with chart images, then reviewed
  extraction findings for language generation. Responses use `store=False`.
- Combined PDF limit: 24 MiB. Requests have a 180-second provider timeout and do
  not automatically retry paid requests. The app remains a single-process local
  operator tool. The override PIN is an editing gate, not user authentication.

## API

- `POST /api/assessments/extract`: multipart `reports` and `family_role`; returns
  `draft_id`, `revision`, extraction, warnings, and missing fields.
- `GET /api/assessments/<draft_id>`: retrieve the saved review and override history.
- `POST /api/assessments/<draft_id>/override`: JSON containing `revision`, `facts`,
  `family_role`, and `pin`. Incorrect PIN: 403; stale revision: 409.
- `POST /api/assessments/generate`: JSON containing `draft_id`, `revision`, and
  `reviewed: true`; returns `persona`, `ready_for_debrief`, and `missing_fields`.

The implementation follows OpenAI's [PDF input](https://developers.openai.com/api/docs/guides/file-inputs)
and [structured output](https://developers.openai.com/api/docs/guides/structured-outputs)
contracts. Uploaded documents and filenames are treated as source data, not
instructions. Human review is still required for extraction accuracy.
