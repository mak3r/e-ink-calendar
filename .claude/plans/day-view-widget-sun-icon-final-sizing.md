# Sunrise/sunset: fill available width, shrink the triangle, center both columns

Status: **approved** — ready for `persona/developer`. The merged #205 PR
implemented the *original* #203 description (icon sized to match the
current fixed-size text) — the maximize-and-center comment posted on #203
before it merged
([[day-view-widget-sun-icon-maximize-and-center]]) did not make it into
the implementation. Filing this as a clean, standalone spec instead of a
comment on an already-closed issue, now combined with a new round of
device-owner feedback on the shipped result.

Reference: https://github.com/mak3r/e-ink-calendar/issues/203#issuecomment-5668048921
(the comment whose content this plan restates and extends — treat *this*
document as authoritative, not that comment, since it also captures the
triangle-size correction below.)

## What's currently shipped (per #205)

```python
time_font = vendored_font(bold=True, size=_FONT_TIME_VALUE)  # fixed, 14pt
icon_size = max(
    text_size("Sunrise", font=label_font)[0],
    text_size("Sunset", font=label_font)[0],
    text_size(weather.sunrise.strftime("%H:%M"), font=time_font)[0],
    text_size(weather.sunset.strftime("%H:%M"), font=time_font)[0],
)
_draw_sun_icon(draw, x0 + _WIDGET_PAD, y0 + _WIDGET_PAD, icon_size, rising=True)
# ... left-aligned to x0 + _WIDGET_PAD / x0 + half_w + _WIDGET_PAD // 2
```

`_draw_sun_icon()` draws the dome at `r = size * 0.36` and the triangle at
`tri_half_w = size * 0.26` (so triangle width = `0.52 * size`, height =
`2 * tri_half_w = 0.52 * size` too — from #197's base≈height rule).

## Problems with the shipped result

1. **`_FONT_TIME_VALUE` is still fixed** — the icon grew to match *that*
   fixed size's text width, but the text itself never grew, so there's
   still whitespace on the right of each half.
2. **Still left-aligned** — no centering was applied.
3. **New from this round: the triangle is now too large.** #197's
   `tri_half_w = size * 0.26` was tuned by eye against the old, much
   smaller fixed `_ICON_SIZE` (28px). Now that `size` is driven by text
   width (likely 40-60+px), that same *fraction* produces a triangle that
   reads as oversized relative to the dome, even though the ratio itself
   didn't change — a fraction tuned at one scale doesn't necessarily still
   look right at a much larger one. Shrink it.

## Decision

In `_draw_dawn_dusk_widget()`:

1. **Grow the time value's font size** to the largest size whose rendered
   `%H:%M` text still fits within the available half-width (`half_w` minus
   padding on both sides — must not touch the border or the vertical
   midline between the two halves). Reuse the "grow, check it fits, step
   back one" pattern already used elsewhere in this file for tier fallback,
   applied here to font point size instead of a discrete tier. The
   "Sunrise"/"Sunset" label can grow modestly too but doesn't need to hit
   the same aggressive target.
2. **Size the icon to match** the new, larger time-value width (same
   `icon_size` computation as #205, just fed by the fits-to-width font).
3. **Center the whole icon + label + time-value block** horizontally
   within each half (`half_w`), instead of left-aligning it flush to
   `x0 + _WIDGET_PAD`.
4. **Shrink the triangle relative to the dome.** In `_draw_sun_icon()`,
   reduce `tri_half_w` from `size * 0.26` to roughly `size * 0.18`–`0.20`.
   Keep the dome radius (`r = size * 0.36`) and the horizon-straddle band
   construction unchanged — only the triangle's own proportion shrinks.
   Verify by eye at the actual (now much larger) rendered size, not just by
   the ratio on paper.

**Downstream layout check (carried over, still applies):** verify the
icon/text stack still fits inside `_WIDGET_DAWN_DUSK_H` (76px); grow the
constant if it doesn't.

## Cross-Persona Completeness Check

- **Test coverage**: yes — this is new sizing/centering/proportion behavior
  replacing what #205's own tests currently assert (those need updating,
  not just extending, since the fixed-`_FONT_TIME_VALUE` and
  left-alignment assumptions they likely encode are exactly what's
  changing) → `persona/test-engineer` companion.
- **Docs / Security / QA / CI**: not applicable.
