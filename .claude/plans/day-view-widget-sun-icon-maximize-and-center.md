# Sunrise/sunset: maximize icon and time size, center within each half

Status: **not implemented as written** — the comment posted on #203
carrying this design did not reach the merged implementation (#205 shipped
the earlier, narrower `day-view-widget-sun-icon-width-match` spec instead).
Superseded by [[day-view-widget-sun-icon-final-sizing]]
(`.claude/plans/day-view-widget-sun-icon-final-sizing.md`), which restates
this plan's requirements as a standalone issue instead of a comment, and
adds a triangle-proportion correction found once the (partial) result
shipped. Kept for history.

Originally: **Supersedes**
[[day-view-widget-sun-icon-width-match]] (`.claude/plans/day-view-widget-sun-icon-width-match.md`)
before that plan's issue (#203) was implemented — matching the *current*
fixed-size text ("Sunrise"/"06:34" at today's `_FONT_WIDGET_LABEL`/
`_FONT_TIME_VALUE`) still leaves visible whitespace on the right side of
each half of the dawn/dusk widget. The device owner asked to go further:
size everything to fill the available space, and center it.

## Decision

In `_draw_dawn_dusk_widget()`, for each half of the widget (`half_w` wide):

1. **Grow the time value's font size** (currently the fixed
   `_FONT_TIME_VALUE = 14`) to the largest size whose rendered `%H:%M` text
   still fits within the available half-width (`half_w` minus padding on
   both sides — content must not touch the border or the vertical midline
   between the two halves). This replaces a fixed constant with a
   fits-to-width search; reuse the "grow, check if it fits, step back one"
   pattern already used elsewhere in this file for tier fallback, applied
   here to font point size instead of a discrete tier.
2. **Size the icon to match** that chosen time-value width (same idea as
   the now-superseded #203, just fed by the new, larger, fits-to-width time
   font instead of the old fixed one).
3. The "Sunrise"/"Sunset" label can grow modestly too for visual harmony,
   but doesn't need to be forced to the same aggressive fill target as the
   icon/time value — it's secondary text above the number, not the primary
   thing being maximized.
4. **Center the whole icon + label + time-value block** horizontally within
   each half (`half_w`), rather than left-aligning it flush to
   `x0 + _WIDGET_PAD` — equal whitespace on both sides of the block, not
   all of it bunched on one side.
5. Use one shared icon/time-value size across **both** halves (the smaller
   of what fits Sunrise's and Sunset's own text, or just compute each
   independently and take the max — either way, both icons must end up the
   same size as each other, matching the existing #203 requirement that
   carries forward unchanged).

**Downstream layout check (unchanged from #203):** verify the taller
icon/text stack still fits inside `_WIDGET_DAWN_DUSK_H` (76px); grow the
constant if it doesn't. This trades a few pixels of the weather widget's
available height, which is acceptable (same tradeoff already noted in the
superseded plan).

## Cross-Persona Completeness Check

- **Test coverage**: yes — this changes #203's not-yet-implemented behavior
  before it shipped; the (also not-yet-written) #204 test issue should
  target this final version, not the superseded one.
- **Docs / Security / QA / CI**: not applicable.
