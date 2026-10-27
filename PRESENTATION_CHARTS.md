# Presentation charts

Open `/presentation` to use Al’s prepared narration and chapter-specific charts.
Choose **Showcase view** for larger charts and an in-page presenter inset. Choose
**Return to split view**, or press Escape, to restore the side-by-side layout.
This resizes the existing Tavus iframe without moving or recreating it. It is
an in-page layout, not an operating-system always-on-top picture-in-picture window.
At widths of 900 pixels or less, the inset becomes a normal stacked player so
it cannot cover chart labels. On narrow phones the two DISC plots also stack.

DISC uses separate Natural and Adapted plots, with all four dimensions visible
and outlines marking the active chapter’s dimensions. Driving Forces use paired
cards with independent 0–100 scales. EQ shows five dimensions and three separate
composite summaries. The styling is XQ’s; the 50 reference line is not a norm,
and no normative ranges, rankings, or target scores are inferred.

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
