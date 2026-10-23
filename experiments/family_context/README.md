# Release 2: standalone context prototype

This package has no production imports, routes, UI, model calls, or persistence.
It cannot alter assessments. It prepares optional, confirmed reports about
upbringing for local inspection; it does not generate psychological traits or
claim to validate a birth-order framework. The supplied example is synthetic.

Run from the repository root:

```sh
.venv/bin/python -m experiments.family_context experiments/family_context/example.json
.venv/bin/python -m experiments.family_context experiments/family_context/example.json --enable-experiment --birth-order
.venv/bin/python -m experiments.family_context experiments/family_context/example.json --enable-experiment --gender-role-experiences
.venv/bin/python -m unittest discover -s experiments/family_context/tests -v
```

The first command returns an empty, disabled context. The master flag and an
explicit discussion option must both be enabled. The two options are independent.
Unselected people and unconfirmed reports are excluded. Missing information stays
missing; no rank, category, traits, sex, or gender is inferred. A parent's upbringing
group is distinct from their children's. Multiple births and social upbringing
positions can be recorded without inventing chronological ranks.

Experiences are untrusted text and must never become instructions if a future
reasoner consumes them. Assessments and score adjustments are not accepted fields.
User confirmation identifies the report's source; it does not establish causation.

Before wiring this into release 1: review age-appropriate source material and
consent/data handling, test the content library and contextual response validator
in isolation, add explicit request-level opt-in with a server kill switch, and
prove no demographic trait attribution, score rewriting, stale-context leakage,
or playback changes. The production group API currently rejects experimental
options and does not import this package. There is no hidden activation flag.
