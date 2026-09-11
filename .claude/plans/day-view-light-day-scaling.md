# Day view: scale cards on light days instead of leaving dead space

Status: **approved** — ready for `persona/developer`. Follow-up to
[[day-view-card-redesign]] (`.claude/plans/day-view-card-redesign.md`), which
this does not revise except where noted in §2. Addresses issue #150.

---

## 1. Problem

`view.day_max_entries` (5-9, default 9) works exactly as designed — it is
purely an overflow cap. A device owner read "fill the space" into it and was
confused when changing it between 9/7/5 produced identical renders on a
2-event day: with only 2 events, all three cap values are no-ops by
definition, since the cap only ever removes cards, never adds size.

The real gap: the original design (§2.4 of the card-redesign plan) sized
cards for exactly one case — 8 cards + an overflow row, the worst case at the
`max_entries=9` default — and used those fixed constants regardless of how
many events actually render. A 2-event day draws two compact cards flush
under the header and leaves roughly 300px of blank white panel below them,
which reads as unfinished/broken even though it is rendering correctly.

## 2. Options weighed

| Option | Verdict |
|---|---|
| **A. Keep fixed compact sizing always** | Rejected — this is the status quo the device owner is reacting to; does not address the complaint. |
| **B. Scale card height/padding only, font size fixed** | Rejected as the primary fix — a taller box around unchanged small text reads as awkward padding, not "filled." (Still used as one ingredient of C, not on its own.) |
| **C. Discrete density tiers: font size, internal padding, and inter-card spacing all scale together, keyed off how many cards actually render** | **Chosen.** Directly answers "cards should fill the space, larger summary text" from the report. Discrete tiers (not continuous interpolation) keep the sizing testable and bound the sizing math to 3 known cases instead of an unbounded function of event count. |
| D. Make card size a config value like `day_max_entries` | Rejected — this is a rendering/aesthetic decision the device shouldn't need a human to tune per day; unlike the entries cap (a genuine usability trade-off worth exposing per §2.6 of the redesign plan), card density should just track how much content there is. |
| E. Scale the whole page (day name, date, calendar key) along with cards | Rejected — the header should stay visually constant across every render so a family member cycling through days has a stable reading anchor; only the event-card content and spacing should respond to how light or busy the day is. |

## 3. Decision

### 3.1 Density tiers

Tier is selected by `len(visible)` — the number of cards actually drawn
*after* the existing `max_entries` overflow logic runs (i.e. this is
orthogonal to, and runs after, the overflow-cap decision from
`day-view-card-redesign.md` §2.6; it does not change when the overflow row
appears, only how the cards above it are sized). Tiers are keyed to absolute
count, not to `max_entries`, because a mostly-empty panel looks the same
regardless of what the cap is configured to.

| Tier | `len(visible)` | Scale | `_FONT_LABEL` | `_FONT_SUMMARY` | `_CARD_PAD` | `_STRIPE_W` | `_CORNER_RADIUS` | base `_CARD_GAP` |
|---|---|---|---|---|---|---|---|---|
| compact (today's sizing, unchanged) | 7-9 | 1.0× | 14 | 15 | 5 | 10 | 6 | 5 |
| comfortable | 4-6 | 1.3× | 18 | 20 | 7 | 13 | 8 | 7 |
| spacious | 1-3 | 1.6× | 22 | 24 | 8 | 16 | 10 | 8 |

`_BORDER_W` (2px) stays constant across tiers — a thicker border at the
spacious tier is a fine implementation nicety but not required. The
**compact tier's numbers are exactly today's constants**, so the existing
8-cards-plus-overflow fit test (the `max_entries=9` worst case) is unaffected
by this change — that case always lands in the compact tier by definition
(7-9 visible cards).

Zero-visible-events day: render the existing "No events" text at the
spacious tier's summary font size, centered (both axes) in the event column
(the left 3/4 of the panel — see §3.3), rather than left-anchored under the
rule as today.

### 3.2 Vertical distribution ("space-around")

Within the tier's card sizing, spread the visible cards down the available
column using the same distribution CSS calls `space-around`: equal slack
before the first card, between every pair of cards, and after the last one.

```
available_h = (height - MARGIN) - (rule_y + RULE_GAP_BELOW)
block_h      = sum(card_h for each visible card at this tier)
             + base_gap * (len(visible) - 1)
leftover     = max(0, available_h - block_h)
slot         = leftover / (len(visible) + 1)

first_card_y = rule_y + RULE_GAP_BELOW + slot
gap_between  = base_gap + slot
```

This is what makes a single event on an otherwise empty day render as one
enlarged card roughly centered in the column, rather than pinned to the top
with a dead zone below — without needing special-case code for `n == 1`.

**Safety net:** if `leftover` would be negative at the selected tier (should
not happen in practice given the tier boundaries above, but a long wrapped
summary could in principle push a card taller than assumed), fall back one
tier more compact and recompute; if still negative at the compact tier, that
is the existing "doesn't fit" case `render()` already handles by folding the
offending card and everything after it into the overflow row
(`day-view-card-redesign.md`'s existing safety-net logic) — no new failure
mode is introduced.

### 3.3 What does *not* scale

- Day name, date line, horizontal rule, and calendar color key stay at their
  current fixed sizes and position on every render, busy or light — this is
  the stable reading anchor referenced in Option E above.
- The event column's width stays fixed at the left 3/4 of the panel
  (`_COLUMN_FRACTION = 0.75`) on every tier. The reserved right quarter for a
  future widget (`day-view-card-redesign.md` §2.4) does not change size or
  appearance based on how many events are on the left — this keeps that
  reserved region's contract stable for whoever eventually builds a widget
  into it, independent of this change.
- The overflow row (when it appears) keeps its own fixed sizing regardless of
  tier — it only ever appears at the compact tier by construction (it takes
  ≥`max_entries` groups to trigger it, and `max_entries` tops out at 9, which
  is within the compact tier's 7-9 range).

## 4. Out of scope

- Any change to `view.day_max_entries` itself or its overflow-row behavior.
- Config exposure of tier thresholds or scale factors (see Option D above).
- Week/month view scaling — day view only, same scoping as the parent plan.

## 5. Follow-on

- `persona/docs`: `docs/architecture.md`'s description of `day_view.py` and
  `view.day_max_entries` (currently only documents the cap, not card sizing)
  needs a short addition once implemented.
- `persona/test-engineer`: new coverage for tier selection at the boundaries
  (3→4 and 6→7 visible cards) and the space-around distribution math,
  alongside the existing day-view render tests.
