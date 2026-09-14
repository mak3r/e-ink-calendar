# Day view widget column: triangle, font, and label polish (round 4)

Status: **approved** — ready for `persona/developer`. Fourth round of
direct feedback on the shipped widget column
([[day-view-widget-column]], [[day-view-widget-column-fixes]] — #166-#180).
All four items below were traced to a precise cause in the merged code
before being written up, per the mockup iteration at
https://claude.ai/code/artifact/9ec445cb-77a5-4c26-b4fb-d705762f9724.

---

## 1. Sunrise/sunset triangles are too elongated

`render/day_view.py::_draw_sun_icon()`: `tri_half_w = size * 0.16` (≈4.5px
half-width, ≈9px base) stretched across a ≈12.4px-tall band
(`band_bottom - band_top`) — a base:height ratio of roughly 0.73, which
reads as a spike rather than a clean triangle.

**Fix:** widen `tri_half_w` to roughly `size * 0.22` (≈6.2px half-width,
≈12.3px base) so base ≈ height, and stop letting the triangle's height
stretch to fill whatever vertical band happens to be available — target a
fixed, proportionate height instead.

## 2. Weather-period labels aren't bold

`_draw_weather_widget()`: `forecast_label_font = vendored_font(size=_FONT_FORECAST_LABEL)`
is missing `bold=True` — every other label/value font in this widget
column passes it; this is the one call site that doesn't.

**Fix:** add `bold=True`.

## 3. "This Afternoon" → "Afternoon"

`weather_source/fetch.py`: `_FORECAST_HOURS = (("This Afternoon", 15), ("Tonight", 21))`.
For consistency with "Morning" and "Tonight" (both single words), change
the label to `"Afternoon"`.

## 4. Sunrise/sunset time values are too large and crowd the widget border

`_draw_dawn_dusk_widget()` reuses the shared `_FONT_WIDGET_VALUE = 18`
(bold) for the sunrise/sunset time values. That constant is sized for
other, wider contexts in this widget column — each half of the dawn/dusk
widget only gets half of an already-narrow column, and at 18pt with
24-hour values ("20:43") the text runs into (or past) the widget's border.

**Fix:** the original `day-view-card-redesign.md`-era design (#167) had a
dedicated, smaller `_FONT_TIME_VALUE` (14pt) specifically for this narrow
context, sized down from the shared value font on purpose. That dedicated
constant should exist again (or `_FONT_WIDGET_VALUE`'s use here should be
resized) rather than reusing the generic, wider-context font size.

## 5. Out of scope / explicitly not addressed here

The sunrise/sunset values still showing an evening/morning swap in the
device screenshot that prompted this round is **not** a code issue — the
merged fix (`ad1ebd2`/`cf4a52e`, closing #177) was read directly and is
correct: `compute_solar_lunar()` takes `tz_name`, all three call sites pass
`config.refresh.timezone`, and astral's `sun()` accepts a plain
timezone-name string for `tzinfo`. The device owner's render most likely
came from a checkout or cache that predated that merge. No action item
here; revisit only if it persists after a fresh `git pull` and a
non-cached render.

## 6. Cross-Persona Completeness Check

- **Test coverage**: yes — three of the four are real regressions with no
  test guarding them → `persona/test-engineer` companion.
- **Docs**: no — these are pixel/font-size corrections to already-documented
  behavior, not a change to what's documented.
- **Security / QA / CI**: not applicable — no new data, no new dependency,
  no acceptance-criteria overlap.
