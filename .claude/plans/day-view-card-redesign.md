# Day view redesign: bigger type, card-style entries, calendar key

Status: **approved** — ready for `persona/developer`. Scopes to the day view
(`render/day_view.py`) only; week/month views are unaffected and keep their
current layout until a follow-up plan covers them.

Design mockup (before/after, three density options):
https://claude.ai/code/artifact/34c243a6-05d6-45a3-bfd9-886730715f42

---

## 1. Problem

The day view's current rendering (screenshot from the live device, Friday 11
September 2026) has four usability issues:

1. Text is rendered at PIL's built-in bitmap default (`layout_common.base_font`,
   a deterministic ~10px font) — legible up close but small for a display meant
   to be read from across a room.
2. The same event, booked identically across more than one configured
   calendar, produces one full row per calendar (`_on_day` + summary rows are
   never deduplicated) — three rows in the screenshot are all "all day — Gus
   12:30 dismissal", differing only in swatch color.
3. Each event's calendar is indicated only by a small color swatch; nothing on
   screen maps a color back to a calendar's name.
4. The list uses the full panel width for what is often a short list, leaving
   the rest of the 800×480 panel empty.

## 2. Decision

Redesign `day_view.render()`'s visual language; keep `render/palette.py`'s
six-color constraint and the existing no-antialiasing text-blitting approach
in `layout_common.py` unchanged in spirit — only the font asset and the sizes/
layout change.

### 2.1 Font

Replace `ImageFont.load_default()` with a bundled TrueType font — **DejaVu
Sans** (regular + bold), permissively licensed (Bitstream Vera-derived, safe to
vendor). Keep the existing `_ink_box`/1-bit-mask rendering path in
`layout_common.py` so text stays palette-pure with no anti-alias fringing;
only the font file and point sizes change. Vendor the font file(s) under the
package (e.g. `eink_calendar/render/assets/fonts/`) with its license file
alongside — do not depend on system fonts being present on the Pi.

Target sizes, tuned against the "9 entries, compact type" mockup and to be
verified for legibility on the physical panel at final review:

| Element | Current | Target |
|---|---|---|
| Day name ("Friday") | scale=3 of ~10px font (~30px) | ~40–44px bold |
| Date line | ~10px | ~16–18px |
| Event time / "ALL DAY" label | ~10px | ~14–15px |
| Event summary | ~10px | ~15–16px |

### 2.2 Deduplication

Before laying out rows, group today's events by
`(summary, start, end, all_day)` — **ignoring** `calendar_id` and `color`.
Each group becomes one card. Collect the distinct `color` values in the group,
in first-seen order (capped at the 4 `ACCENT_COLORS`, which is already the
ceiling for distinct calendar colors).

### 2.3 Calendar color key

A compact legend row — small colored square + calendar label, one pair per
distinct color present among *today's* events — right-aligned in the header
band (top-right, same row as the day name). Calendar labels come from
`AccountConfig`/`CalendarSpec.label` (see `docs/architecture.md`'s config
schema) — `day_view.render()` will need those threaded in from
`renderer.render()` alongside the event list, since `Event` itself only
carries `calendar_id`/`color`, not the human label. This is the one signature
change that ripples beyond `day_view.py` — `renderer.render()` and its caller
in `app.py` need to pass a `color -> label` mapping (or the full calendar
config) down.

### 2.4 Card layout

- Event list occupies the **left 3/4 of the panel width** (from `MARGIN` to
  `~0.75 * width`); the right quarter is left blank for now — no border, no
  divider, no placeholder text on the actual device. A future widget (e.g.
  weather) claims that space in a separate plan/issue; this change only stops
  the event column from spanning full width.
- Each event is a rounded-rectangle card: solid black 2px border, rounded
  corners, sized to the 3/4-width column.
- The card's left edge carries a colored accent stripe. For a single-calendar
  event, the stripe is solid. For a deduplicated/merged event, the stripe is
  split into equal horizontal bands, one per distinct source color (from
  §2.2).
- All-day events show a small-caps "ALL DAY" label instead of a numeric time.

### 2.5 Header spacing

Fix a spacing defect found in mockup iteration: the horizontal rule under the
date must sit close under the date text (underscore-like) rather than
centered between the date and the first event card — i.e. a small gap above
the rule, a larger gap below it before the event list starts. Verify the
existing `header_bottom` computation in `day_view.py` doesn't reintroduce the
tight/overlapping gap once font sizes change.

### 2.6 Configurable entry cap

Add `view.day_max_entries: int` to `ViewConfig` (`config.py`), validated to
the inclusive range **5–9**, default **9** (the density selected after
reviewing the mockups). This keeps the constant out of `render/day_view.py`
so it can be tuned per household without a code change, and sets up real
usability testing before this is ever exposed as an end-user-facing setting.

After deduplication (§2.2), if the day has more groups than the configured
cap, render `day_max_entries - 1` cards followed by an overflow row — never
silently drop events off the bottom of the list. The device's refresh is slow
and there is no touch input, so the overflow row should be glanceable rather
than plain text: a small bordered band, split into equal segments — one per
distinct color among the *hidden* events only (not all of today's events) —
followed by the `+N more` count, where `N` is the number of hidden groups.
This mirrors the split-stripe treatment already used on deduplicated cards
(§2.4), so the visual language is consistent top to bottom.

## 3. Out of scope

- The actual weather (or other) widget for the reserved right quarter —
  tracked separately once someone wants to build it.
- Week/month view visual changes.
- Exposing `day_max_entries` as an end-user-facing runtime setting (a settings
  UI) — for now it's a config file value read once at startup, same as every
  other `ViewConfig` field.

## 4. Follow-on

Once implemented and merged, `docs/architecture.md`'s config schema table and
example YAML need the new `view.day_max_entries` key — normal `persona/docs`
follow-up per the handoff rules, not blocking this issue.
