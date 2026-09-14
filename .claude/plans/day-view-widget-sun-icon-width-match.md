# Sunrise/sunset icon: size to match the text column's width

Status: **approved** — ready for `persona/developer`. Ninth round of
feedback on the shipped widget column, following
[[day-view-widget-icon-redesign-round2]] (#196-#198).

## Problem

`_draw_sun_icon()` always renders at the fixed `_ICON_SIZE` (28px, shared
with the moon icon) regardless of how wide the "Sunrise"/"Sunset" labels and
their `%H:%M` time values render in `_draw_dawn_dusk_widget()`. On the real
device, that text is noticeably wider than the icon, leaving unused
horizontal space on either side of it — the device owner wants the icon
sized to fill that same width instead.

## Decision

Give `_draw_sun_icon()` a `size` parameter (instead of always reading the
module-level `_ICON_SIZE`), and have `_draw_dawn_dusk_widget()` compute a
size at render time from the actual text it's drawing:

```python
icon_size = max(
    text_size("Sunrise", font=label_font)[0],
    text_size("Sunset", font=label_font)[0],
    text_size(weather.sunrise.strftime("%H:%M"), font=time_font)[0],
    text_size(weather.sunset.strftime("%H:%M"), font=time_font)[0],
)
```

Use one shared value (the max across both columns) for both the rising and
setting icon, rather than sizing each independently — so the two icons stay
the same size as each other even if "Sunrise" and "Sunset" happen to render
at slightly different pixel widths.

Do **not** touch `_ICON_SIZE` itself — it's shared with the moon icon, which
isn't part of this change. `_draw_sun_icon()`'s internal proportions (dome
radius, triangle half-width, band placement — all tuned in #197) stay as
fractions of whatever `size` it's given; only the value passed in changes.

**Downstream layout check:** `_WIDGET_DAWN_DUSK_H` (currently 76px, fixed)
was sized around the old fixed icon height. A wider icon is also taller
(the dome scales with it), so verify the icon + label + value stack still
fits inside that height without overflowing the widget's rounded-rectangle
border — increase the constant if not. This trades a few pixels of the
weather widget's available height (it fills whatever's left after the two
fixed-height widgets above it), which is an acceptable, minor effect.

## Cross-Persona Completeness Check

- **Test coverage**: yes — new sizing behavior, no existing test covers it
  → `persona/test-engineer` companion.
- **Docs / Security / QA / CI**: not applicable.
