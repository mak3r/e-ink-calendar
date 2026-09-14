# Day view widget column: rule length and weather-row spacing (round 5)

Status: **approved** — ready for `persona/developer`. Fifth round of direct
feedback on the shipped widget column
([[day-view-widget-column]], [[day-view-widget-column-fixes]],
[[day-view-widget-icon-font-fixes]] — #166-#189). Both items traced to a
precise cause in the merged code, per
https://claude.ai/code/artifact/9ec445cb-77a5-4c26-b4fb-d705762f9724.

---

## 1. Horizontal rule spills past the event column into the widget gap

`render/day_view.py`: `column_right` is the event column's true right edge
(the 75% boundary event cards are drawn against). `widget_left =
column_right + _WIDGET_GAP` (12px further right — the gap before the
widget column starts). The header rule is drawn to `widget_left`, not
`column_right`:

```python
draw.line([(MARGIN, rule_y), (widget_left, rule_y)], fill=color("black"))
```

So the rule extends 12px past where the event cards actually end, into the
gap before the widgets — which is what reads as "spilling into the widgets
section." **Fix:** draw to `column_right` instead of `widget_left`.

## 2. Weather-widget forecast rows are packed at the top

`_draw_weather_widget()` uses small fixed gaps — a flat `pad` (8px) after
H/L, and `_FORECAST_ROW_GAP = 6` between each of the three period rows —
so all three rows (Morning/Afternoon/Tonight) pack near the top of the
widget and leave the widget's actual remaining height unused below. This
is the same "packed instead of spread" shape as the bug already fixed once
for the event-card list ([[day-view-density-stacking-fix]]).

**Fix:** distribute the gap after H/L and the three forecast rows with
equal slack (space-around) across whatever height is actually available in
the weather widget box, mirroring the existing space-around logic already
used elsewhere in this file for card stacking — same algorithm, applied to
a different set of rows. Additionally, bump the period label and
temperature fonts up slightly from their current sizes
(`_FONT_FORECAST_LABEL = 13`, `_FONT_FORECAST_TEMP = 24`) now that there's
more visual room to use.

## 3. Cross-Persona Completeness Check

- **Test coverage**: yes — both are layout regressions with no test
  guarding them → `persona/test-engineer` companion.
- **Docs / Security / QA / CI**: not applicable — pure layout correction,
  no new documented behavior, no new data, no new dependency.
