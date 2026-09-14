# Day view widget column: key overflow fix, cloud rebuild, sunrise/sunset redesign

Status: **approved** — ready for `persona/developer`. Sixth-through-eighth
rounds of feedback on the shipped widget column, developed live against the
mockup at https://claude.ai/code/artifact/9ec445cb-77a5-4c26-b4fb-d705762f9724
and two device-owner-provided reference sketches for the sunrise/sunset
triangle placement and the cloud shape.

---

## 1. Calendar key overflows past the calendar/widget boundary

`render/day_view.py`: the key is anchored to `widget_left - _KEY_RIGHT_GAP`
(= `column_right + 12 - 6` = `column_right + 6`) — 6px *past* the boundary
the header rule now correctly stops at (`column_right`, fixed in #191). The
key's own layout math (`x = right_edge - total_w` in `_draw_calendar_key()`)
is otherwise correct; it just needs the same anchor as the rule.

**Fix:** pass `column_right` as the key's right edge, matching the rule's
endpoint, instead of `widget_left - _KEY_RIGHT_GAP`.

## 2. Sunrise/sunset icon: eliminate the reserved arrow band, straddle the horizon, and grow

Current design (`_draw_sun_icon()`, #185): the triangle lives in a band
*below* the horizon line — `band_top = horizon_y + 3` for rising,
`band_bottom = y + size` for setting, each producing its own apex/base pair
from a shared value (this part of the design is already sound — both
directions are derived from one shared reference, not two independently
computed ones, so it doesn't have the kind of connection bug a naive
implementation could introduce).

Per the device owner's reference sketch, redesign so the triangle
**straddles the horizon line directly** (roughly half above, half below)
instead of living in a separate zone underneath it — freeing that band's
space to make both the dome and the triangle bigger within the same icon
footprint, while keeping the same "one shared band, apex/base swapped"
construction so both directions stay guaranteed-symmetric:

```python
band_center = horizon_y + 3   # a few px below dead-center, per final tuning
band_top = band_center - tri_half_w
band_bottom = band_center + tri_half_w
apex_y, base_y = (band_top, band_bottom) if rising else (band_bottom, band_top)
```

Also grow the icon within its existing `_ICON_SIZE`, via the *fraction*
constants rather than `_ICON_SIZE` itself (which is shared with the moon
icon — growing it would enlarge that too, which isn't part of this ask):

- Dome radius: `r = size * 0.3` → roughly `size * 0.36`.
- Triangle half-width: `tri_half_w = size * 0.22` → roughly `size * 0.26`
  (keep `tri_h = tri_half_w * 2`, preserving the base≈height proportion
  from #185).

Exact fractions are a starting point — tune visually against
`scripts/render_once.py` output, same as every prior icon-sizing pass in
this series.

## 3. Cloud icon: rebuild as three layered circles plus one erase oval

Current `_draw_cloud()`: three circles at varying scale (`0.1/0.35/0.55`
x-offsets, radius scaled `1.0/1.2/1.0`) plus a flat `rounded_rectangle`
"base" spanning `0.05`-`0.95` of the width — wider on the left than the
leftmost circle, which is why it visibly pokes out past the puffs.

Per the device owner's exact reference recipe, replace this entirely:

1. **Three circles of similar size**, white-filled with a 2px black
   outline, drawn **left, then center, then right** — relying on plain
   draw-order (each later circle's outline paints over the earlier ones'
   in the overlap zone) rather than any z-index-equivalent trick. Roughly:
   left circle centered around `(0.30*size, 0.55*size)` radius
   `~0.28*size`; center circle `(0.55*size, 0.35*size)` radius
   `~0.32*size` (bigger/higher, forming the peak); right circle
   `(0.75*size, 0.55*size)` radius `~0.28*size`.
2. **One additional ellipse drawn last**, white-filled **and
   white-outlined** (invisible against the white background on its own),
   sized to cover only the internal seams where the three circles cross
   each other — a horizontal band in the middle, e.g. roughly
   `x: 0.20*size–0.85*size, y: 0.48*size–0.62*size`. This must stay well
   above the circles' own bottom edges (~`0.67*size`–`0.83*size` at the
   proportions above) — extending it down to meet those edges erases the
   true outer silhouette there instead of just the seams, producing a
   "clipped flat bottom" look (this exact mistake was made and caught
   during mockup iteration — worth calling out so it isn't repeated).
3. **No separate flat base rectangle.** The cloud is entirely the union of
   the three circles (plus the seam-cleanup ellipse); this is a visible
   change from the current flat-bottomed cloud shape.

This single shape becomes what every cloud-based condition icon (partly
sunny, partly cloudy, cloudy, rain, snow) builds on — `_condition_name()`'s
vocabulary and `_draw_condition_icon()`'s per-condition accents (sun peeking
behind for partly-sunny/partly-cloudy, raindrops, snowflakes) are unchanged;
only the cloud primitive they all call changes.

Exact circle/ellipse proportions above are a starting point (worked out
against a description of the device owner's reference sketch, not
pixel-level access to it) — tune visually against a rendered output,
comparing to the reference image if it's more convenient to check directly
on the device/Mac dev loop than from this issue's text.

## 4. Cross-Persona Completeness Check

- **Test coverage**: yes — all three are visual/layout changes with no
  guarding tests → `persona/test-engineer` companion.
- **Docs / Security / QA / CI**: not applicable — no new documented
  behavior, no new data, no new dependency.
