# Score wording and speech coverage

These cutoffs are the application's existing **wording bands**, not validated
TTI population norms, percentiles, diagnoses, or revised assessment scoring.
This audit retains the cutoffs and completes the language selected by them.
Source scores, reported style names, and cluster membership are unchanged.

| Domain | Wording bands on the 0–100 scale |
| --- | --- |
| DISC and Driving Forces | Very low: 0 ≤ score < 30; low: 30 ≤ score < 40; moderate: 40 ≤ score < 60; high: 60 ≤ score < 70; very high: 70 ≤ score ≤ 100 |
| EQ dimensions and composites | Lower: 0 ≤ score < 50; developing: 50 ≤ score < 60; moderate: 60 ≤ score < 70; high: 70 ≤ score < 80; very high: 80 ≤ score ≤ 100 |

## Covered measurements

- DISC: Dominance, Influence, Steadiness, Compliance; both natural and adapted
  scores. An adapted result in the same band references the same description;
  a different band receives its own description. Adjustment does not prove cause.
- Driving Forces: Intellectual, Instinctive, Resourceful, Selfless, Harmonious,
  Objective, Altruistic, Intentional, Commanding, Collaborative, Structured,
  Receptive. All twelve are narrated, including situational and indifferent
  cluster members. Moderate scores no longer select high-score wording.
- EQ: Self-Awareness, Self-Regulation, Motivation, Social Awareness, Social
  Regulation, Self Composite, Others Composite, Total EQ. Composites have their
  own range-specific interpretation rather than only a generic definition.

There are 120 dimension/band entries, reused for 140 measured-profile/band
combinations when natural and adapted DISC are counted separately. Each entry
includes a family application and a qualification or watchout. Low preferences
are not moral defects; a low force does not establish a high opposing force.
EQ composites do not imply that every constituent dimension has the same score.
Unknown values remain unknown; zero is a measured score and has a valid band.

Unrecognized or compound DISC styles retain the report's name. The renderer
falls back to the actual dimension scores rather than rejecting the profile or
inventing a mapping to a supported style label.

## One source for language

The JSON narrative libraries supply deterministic narration. `score_wording.py`
selects those same entries for individual questions, comparison questions, and
the JSON Maker's family-language request. Their prompts require matching-score
interpretations and the same range policy. Generated answers can paraphrase;
prompt instructions do not guarantee verbatim language from an LLM.

The speech path is engine narrative → sentence splitter → playback cursor and
coordinator → Tavus Text Echo. Automated tests exercise complete narratives at
every band, including low endpoints and decimal boundaries, and reconstruct the
submitted speech to assert exact equality with the original narrative. The
transport is mocked: this verifies text delivery and completion tracking, not
provider pronunciation, network delivery, or audible playback in a live session.

Tests also verify every tenth of a point from 0 through 100, complete and distinct
entries for each dimension, invalid-value rejection, compound style fallback,
nonprimary force narration, composites, and shared question-context language.
