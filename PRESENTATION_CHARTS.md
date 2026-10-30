# Presentation charts

Open `/presentation` to use Al’s prepared narration and chapter-specific charts.
Choose **Showcase view** for larger charts and an in-page presenter inset. Choose
**Return to split view**, or press Escape, to restore the side-by-side layout.
This resizes the existing replica-only video without reconnecting the Daily call. It is
an in-page layout, not an operating-system always-on-top picture-in-picture window.
At widths of 900 pixels or less, the inset becomes a normal stacked player so
it cannot cover chart labels. On narrow phones the two DISC plots also stack.

DISC uses separate Natural and Adapted plots, with all four dimensions visible
and outlines marking the active chapter’s dimensions. Driving Forces use paired
cards with independent 0–100 scales. EQ shows five dimensions and three separate
composite summaries. The styling is XQ’s; the 50 reference line is not a norm,
and no normative ranges, rankings, or target scores are inferred.

The player uses Daily's headless call object and renders only the replica's
video/audio tracks, identified by its Tavus replica user ID or the server's PAL
participant IDs. Other attendees do not create tiles or play audio. Video uses
`object-fit: contain` to preserve the complete frame, with letterboxing when
needed. Camera and microphone capture remain off. Browser-blocked audio exposes
an “Enable presenter audio” button. Layout changes retain the same call object.

Colors follow the supplied TTI report examples: Knowledge red, Utility gold,
Surroundings purple, Others teal, Power black, Methodologies gray. EQ uses peach,
coral, orange, lavender, and purple for the five dimensions in report order.
Each Driving Forces pair shares a color; exact numeric labels remain visible.

Use “Preview chapter charts” to inspect every section before opening Tavus.
Charts advance with the chapter, including during autoplay. Missing scores say
“Not reported”; a reported zero remains zero. Charts use independent 0–100 bars,
not population percentiles or a combined assessment score.

To present another person, upload a complete Family or Workplace profile JSON
using the source chooser before starting the session. This validates the existing
profile format and builds concise factual narration and all 28 score bars from
the same profile. It does not reuse Al’s interpretations. No API generation is
needed. Uploads stay in server memory, shared by presentation viewers, and do not
modify the saved profiles. Restarting the server restores Al’s example. End a
session before changing sources; the recorded-example button restores the script.

For the recorded presentation, edit `content/presentation.json` for spoken text.
Each chapter’s optional `visual` selects `overview`, `disc_di`, `disc_sc`,
`forces_first`, `forces_second`, or `eq`. These bindings survive chapter reordering.
A chapter without a recognized binding displays “No chart is assigned”. The
reported numeric data lives in `content/presentation_profile.json`. Keep its
values consistent with the script when editing; there is no automatic extraction
from prose. Al’s chart data is a complete 28-score snapshot from his Workplace
profile, identified by `source_profile` in the chart data file. This supplements
the recorded narration without changing its words. Editing the Workplace profile
later does not automatically refresh this snapshot. Restart the server and reload
the page after file edits, or use the recorded-example button to reload these files.

`presentation_visuals.py` defines reusable chart groups and profile-based speech.
Presentation remains Tavus-based and subject to the existing 15-minute budget.
The browser draws charts locally without another chart library or network call.


## Amethyst and Acumen (ACI)

Choose **Presentation source → Amethyst · DISC / Driving Forces / ACI** before
starting. Al remains the default and can be restored with his button. Both split
and showcase views support ACI. World View and Self View show three clarity
columns each, exact blind-spot values, valuation arrows with text, the report's
rounded clarity average, and emotional bias distortion. Expand each panel's
**Problem solving and decision making** for all four additional reported scores
and numbered reference markers. Green is intrinsic, yellow extrinsic, blue
systemic. These are 0–100 scores, not percentiles. Unnumbered gauges, population
bands, and dial magnitudes are not inferred. ACI replaces EQ in this source only.

`content/presentations/amethyst.json` contains the single authoritative prepared
bundle: `presentation_version: 1`, `profile`, and `chapters`. Edit chapter `text`
for narration; `visual` binds to overview, disc_di, disc_sc, forces_first,
forces_second, aci_balance, aci_world, or aci_self. The ACI score schema is illustrated
in `profile.aci`: six dimension objects with clarity, blind_spot and bias
(over/mixed/under/null), plus world/self summaries and optional problem_solving.
Missing numeric fields or null display as Not reported; zero remains zero.
Numeric values must be finite and between 0 and 100. Arrows are categorical,
not numerical magnitudes. The existing persona schema is not extended.

The JSON uploader accepts this prepared bundle format in addition to existing
Family/Workplace persona JSONs. Prepared bundles preserve supplied narration;
ordinary personas still generate factual score narration. The API rejects invalid
scores, unknown chart bindings, and source changes while a session is active.
Source uploads remain in memory. Choosing a prepared source reloads its file;
restarting restores Al. Keep scripts within the displayed 15-minute budget.

The original STT sections, joined raw transcript, full cleaned transcript,
shorter presentation script, provenance, and editorial decisions are under
`content/presentation_sources/amethyst/`. The shorter adaptation is 1098 words;
the full cleaned transcript is preserved separately. Scores were verified against
the supplied PDF's pages 26, 39, 52–53, 55–56, and 60. No new assessment extraction
or STT service was added to the runtime app; this is a prepared presentation.


## Workforce AI investor presentation

Choose **Presentation source → Workforce AI · Investor presentation** before
starting Tavus. Eleven chapters adapt the supplied investor strategy PDF into a
15-minute presentation slot, emphasizing retention, applied training, motivation,
ongoing support, break-even math and measurable pilots. About 1,395 spoken words
leave setup/transition margin; playback duration is estimated, not guaranteed.
Al remains the default. All source changes are blocked during an active session.

`content/presentations/workforce-investor.json` is the authoritative script and
graphics source. It uses `presentation_version: 1`, `presentation_type: investor`,
`source`, `chapters` and `visuals`; no assessment profile is required. Chapters
bind to graphic keys via `visual`. Each graphic has `kind: investor`, `layout`
(cards, steps or bars), `title`, `note`, `source`, `takeaway` and `items`.
Cards/steps use label/value/detail text. Bar groups use label/unit/bars, with each
bar containing label and a finite nonnegative numeric value. Bar widths use a
zero baseline and the group's maximum; currency is not clamped to 0–100.

The JSON uploader also accepts this format. Strings render as text, not HTML;
unsupported layouts and invalid values are rejected before replacing the source.
The business graphic renderer is isolated in `static/investor-visuals.js` and
`.css`; the assessment schemas and runtime debrief engines are unchanged.

The graphics are adapted layouts, not screenshots of all 31 original slides.
Pricing, customer ROI examples and business forecasts are explicitly labeled as
proposals/scenarios. The presentation uses the later $49/user/month model and
does not add overlapping cost categories. It distinguishes subscription churn
from employee attrition and actual product functionality from the roadmap.
Full source mapping, script review copy, timing and calculation notes live in
`content/presentation_sources/workforce-investor/`.

The investor narrative follows Attention → Interest → Conviction → Desire → Close.
Q&A assumptions and calculation detail are kept in its EDITING_NOTES.txt; the
presentation focuses on the problem, solution, customer economics and invitation
to invest. Its ROI graphic uses the deck’s $1M–$2M capacity-value scenario against
a $588K annual subscription, with the scenario inputs stated in the speech.
