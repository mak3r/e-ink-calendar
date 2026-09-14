# Sunrise/sunset: tighten the icon-to-text gap

Status: **approved** — ready for `persona/developer`. Small follow-up to
[[day-view-widget-sun-icon-final-sizing]] (#209/#211), confirmed directly by
the device owner editing `_draw_dawn_dusk_widget()` in their own checkout
and testing the result with `scripts/render_once.py`.

## Decision

In `_draw_dawn_dusk_widget()`, change:

```python
ink_gap, value_gap = 14, 8
```

to:

```python
ink_gap, value_gap = 4, 2
```

Because the icon+label+value block is vertically centered as one unit
(`margin = (frame_h - content_h) / 2`), shrinking these two gaps has a
compounding effect beyond just tightening the icon-to-label and
label-to-value spacing directly: shrinking `content_h` increases `margin`,
which pushes the icon further down while the text ends up higher relative
to the bottom — exactly the "bring the time values up and the sun images
down" the device owner asked for, from two number changes rather than
four.

No other change — icon size (`_DAWN_DUSK_ICON_SIZE`), the time-value
fits-to-width sizing, and the horizontal centering are all already correct
and untouched by this.

## Cross-Persona Completeness Check

- **Test coverage**: yes — #211's tests (`tests/render/test_day_view_icon_sizing.py`
  and related) were written against the old `ink_gap=14, value_gap=8`
  values and likely assert positions computed from them → `persona/test-engineer`
  companion to update those two constants in the test fixtures/assertions.
- **Docs / Security / QA / CI**: not applicable.
