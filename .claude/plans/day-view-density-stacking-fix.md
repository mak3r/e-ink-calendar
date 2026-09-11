# Day view: stop spreading cards apart, make busy-day sizing respect day_max_entries

Status: **approved** — ready for `persona/developer`. Follow-up to
[[day-view-light-day-scaling]] (`.claude/plans/day-view-light-day-scaling.md`,
implemented in #155/#158). **Supersedes that plan's §3.1 "busy-day exception"
and §3.2 "space-around" entirely** — §3.3 ("what does not scale") is
unaffected and still applies.

Mockups (before/after, both bugs): the device owner and I iterated on these
directly — see https://claude.ai/code/artifact/e6c6cf15-f4bd-44f2-9bf2-18c89190c921

---

## 1. Problem

Two issues surfaced from real device use of the shipped #155 behavior:

1. **Cards spread apart instead of stacking.** The "space-around" vertical
   distribution (old §3.2) puts equal slack before the first card, between
   every pair, and after the last. On a 2-event day this produces a large gap
   between the two cards, which reads as floating/disconnected rather than a
   list — not what "fill the space" was supposed to mean.
2. **`day_max_entries` doesn't visibly do anything until overflow actually
   triggers.** The busy-day path (old §3.1) hardcodes the fixed "compact"
   tier whenever `max_entries` has trimmed the list, regardless of what
   `max_entries` is configured to. A `day_max_entries=5` household's busiest
   possible day only ever has 4-5 cards, but still rendered at the tiny size
   tuned for a `day_max_entries=9` household's 8-9-card worst case — visibly
   under-filling the column. This is also why testing the same light day
   under `day_max_entries` values of 5, 7, and 9 produced identical renders:
   neither bug's code path consulted `max_entries` for sizing at all.

## 2. Decision

**Unify the render path.** Drop the light-day/busy-day branch entirely.
Every day, regardless of whether `max_entries` trimmed anything:

1. Compute `visible`/`overflow` exactly as today (unchanged) — trim to
   `max_entries - 1` plus an overflow row when the day has more groups than
   the cap.
2. Pick `tier = tier_for(len(visible))` — the *same* function and thresholds
   already defined for the light-day case (1-3 spacious, 4-6 comfortable,
   7-9 compact). No new tier table keyed on `max_entries` is needed: because
   `max_entries` bounds how large `len(visible)` can ever get, a smaller cap
   naturally lands on a bigger tier at its own worst case.
   - `max_entries=9` worst case: 8-9 visible → compact (today's exact
     numbers, unchanged — still pixel-identical to the original #127
     baseline).
   - `max_entries=5` worst case: 4-5 visible → comfortable — visibly bigger
     than before, which is the fix for problem 2.
3. Always stack top-down: first card immediately under the rule, each
   subsequent card offset by the previous card's height plus the tier's
   fixed `card_gap`. Never distribute leftover space — it stays blank below
   the last card (or below the overflow row), the same way blank space
   already behaves above the header and beside the reserved widget column.
   This removes the space-around formula and its "which tier fits" fallback
   loop from `day-view-light-day-scaling.md` §3.2 outright — the only
   fallback needed now is stepping down a tier (see §3 below).
4. Zero-visible-events day: unchanged from #155 — "No events" at the
   spacious tier's size, centered in the event column.

This also **simplifies the implementation**: `render()` no longer branches on
`if overflow:` for sizing purposes (only for whether to draw the overflow
row), `_draw_stacked` becomes the only card-drawing loop (the space-around
loop in `render()` is deleted), and there is exactly one tier-selection call
site instead of one hardcoded and one computed.

## 3. Safety net (simplified from the old §3.2)

If the tier's cards don't fit the available column height (e.g. a
pathologically long wrapped summary), step down one tier and retry; if
compact still doesn't fit, fold whatever doesn't fit into the overflow row —
the same fold-into-overflow mechanism `render()` already has from #127. No
"leftover"/slot arithmetic is needed anywhere anymore, since nothing is being
distributed.

## 4. Accepted tradeoff (confirmed with the device owner)

A day well under *any* cap renders identically regardless of what
`day_max_entries` is set to — e.g. a 2-event day looks the same whether the
cap is 5 or 9, since neither is close to being reached. Only the
busiest-day-for-that-cap scenario now differs by setting. The device owner
confirmed this is an acceptable starting point ("not what I originally
intended, but let's see how it goes for user testing") rather than a rule
that ties sizing to `max_entries` directly on light days too — revisit after
real usage if that turns out to matter.

## 5. Follow-on

- `persona/test-engineer`: #158's tests explicitly cover the space-around
  formula and the busy-day-forces-compact-tier behavior — both being removed
  here. Those tests need replacing, not just extending, with coverage for:
  tier selection applied uniformly (including a `max_entries=5` busy-day case
  landing on comfortable, and a `max_entries=9` busy-day case staying
  compact), top-down stacking with no distributed slack, and the
  step-down-a-tier safety net.
- `persona/docs`: `docs/architecture.md`'s existing sentence ("Card size,
  padding, and spacing also scale across three density tiers based on how
  many cards actually render... so a light day fills the panel instead of
  leaving dead space") remains accurate as written — it was already
  describing the intended behavior, not the old busy-day-hardcoded bug — so
  no change is required there. Flagged here for completeness per the
  Cross-Persona Completeness Check, not as an action item.
