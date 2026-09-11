"""Regression coverage for #151/#160: day-view density tiers and stacking.

#151 introduced density tiers plus a "space-around" distribution that spread
cards apart; #160 replaced that with plain top-down stacking (fixed gap only,
no distributed slack) and unified tier selection so it applies identically
whether or not ``max_entries`` trimmed the list. See
``.claude/plans/day-view-density-stacking-fix.md`` (supersedes
``day-view-light-day-scaling.md`` §3.1/§3.2). Covers the tier-selection
boundaries, top-down stacking with a fixed gap on a light day, a lower
``max_entries``'s own worst case landing on a bigger tier (not hardcoded
compact), the ``max_entries=9`` worst case staying pixel-equivalent to the
original fixed compact sizing, and the safety-net fallback for a card too
tall to fit even at the compact tier.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone

from eink_calendar.calendar_source.models import Event
from eink_calendar.render import day_view
from eink_calendar.render.layout_common import MARGIN, text_size, vendored_font

RESOLUTION = (800, 480)


def _events(n: int) -> list[Event]:
    day = datetime(2026, 9, 9, tzinfo=timezone.utc)
    events = []
    for i in range(n):
        start = day.replace(hour=6 + i)
        events.append(
            Event(
                id=str(i),
                summary=f"Event {i}",
                start=start,
                end=start + timedelta(minutes=30),
                all_day=False,
                calendar_id="primary",
                color="red",
            )
        )
    return events


def _ink_rows(image, y_lo, y_hi, x_lo, x_hi):
    """y values in ``[y_lo, y_hi)`` with at least one black pixel in the x band."""
    px = image.load()
    return [
        y
        for y in range(y_lo, y_hi)
        if any(px[x, y] == (0, 0, 0) for x in range(x_lo, x_hi))
    ]


def _bands(rows):
    """Collapse a sorted row list into ``(top, bottom)`` contiguous bands."""
    bands = []
    for y in rows:
        if bands and y == bands[-1][1] + 1:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


def _start_y_and_column_right(width: int) -> tuple[int, int]:
    """Replicate ``day_view.render``'s header geometry to locate the rule
    and the top of the card column, without duplicating font-size constants."""
    day_font = vendored_font(bold=True, size=day_view._FONT_DAY_NAME)
    date_font = vendored_font(size=day_view._FONT_DATE)
    day_name_h = text_size("A", font=day_font)[1]
    date_h = text_size("A", font=date_font)[1]
    rule_y = MARGIN + day_name_h + day_view._DATE_TOP_GAP + date_h + day_view._RULE_GAP_ABOVE
    start_y = rule_y + day_view._RULE_GAP_BELOW
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    return start_y, column_right


def test_tier_boundary_spacious_to_comfortable():
    assert day_view._tier_for(3) is day_view._TIER_SPACIOUS
    assert day_view._tier_for(4) is day_view._TIER_COMFORTABLE


def test_tier_boundary_comfortable_to_compact():
    assert day_view._tier_for(6) is day_view._TIER_COMFORTABLE
    assert day_view._tier_for(7) is day_view._TIER_COMPACT


def test_compact_tier_matches_original_pre_151_constants():
    """The compact tier must equal the exact numbers day_view used before
    density tiers existed, so the worst case renders unchanged."""
    tier = day_view._TIER_COMPACT
    assert (tier.font_label, tier.font_summary, tier.card_pad, tier.stripe_w, tier.corner_radius, tier.card_gap) == (
        14, 15, 5, 10, 6, 5,
    )


def test_busy_day_worst_case_stays_pixel_equivalent_to_original_compact_tier():
    """max_entries=9 worst case (8 visible + overflow) must still land on the
    compact tier and stack top-down with the fixed 5px gap, unchanged since
    #127/#151, now arrived at via the same unified path every day uses."""
    when = datetime(2026, 9, 9, tzinfo=timezone.utc).date()
    image = day_view.render(_events(12), when, RESOLUTION)
    start_y, column_right = _start_y_and_column_right(image.width)

    rows = _ink_rows(image, start_y - 5, image.height, MARGIN, column_right)
    bands = _bands(rows)

    # 8 visible cards + 1 overflow row.
    assert len(bands) == 9, f"expected 8 cards + overflow row, got {len(bands)} bands: {bands}"
    assert bands[0][0] - start_y <= 1, "first card should start right at the rule, no leading slack"

    gaps = [b2[0] - b1[1] - 1 for b1, b2 in itertools.pairwise(bands)]
    assert all(abs(g - day_view._TIER_COMPACT.card_gap) <= 1 for g in gaps), gaps


def test_light_day_cards_stack_top_down_with_fixed_gap():
    """Regression guard for #160 bug 1: cards must not spread apart with
    distributed slack — they stack immediately under the rule with only the
    tier's fixed gap between them, leaving any leftover space blank below."""
    when = datetime(2026, 9, 9, tzinfo=timezone.utc).date()
    image = day_view.render(_events(2), when, RESOLUTION)
    start_y, column_right = _start_y_and_column_right(image.width)

    rows = _ink_rows(image, start_y - 5, image.height, MARGIN, column_right)
    bands = _bands(rows)
    assert len(bands) == 2, bands

    leading = bands[0][0] - start_y
    gap = bands[1][0] - bands[0][1] - 1
    assert leading <= 1, f"cards should stack immediately under the rule, got a {leading}px leading gap"
    assert abs(gap - day_view._TIER_SPACIOUS.card_gap) <= 1, gap


def test_lower_max_entries_worst_case_lands_on_a_bigger_tier():
    """Regression guard for #160 bug 2: a household's own configured
    ``max_entries`` worst case must size by how many cards actually render,
    not hardcode the compact tier meant for the default of 9."""
    when = datetime(2026, 9, 9, tzinfo=timezone.utc).date()
    image = day_view.render(_events(6), when, RESOLUTION, max_entries=5)
    start_y, column_right = _start_y_and_column_right(image.width)

    rows = _ink_rows(image, start_y - 5, image.height, MARGIN, column_right)
    bands = _bands(rows)

    # 4 visible cards (max_entries=5 -> cap of 4 before the overflow row) + 1 overflow row.
    assert len(bands) == 5, f"expected 4 cards + overflow row, got {len(bands)} bands: {bands}"

    gaps = [b2[0] - b1[1] - 1 for b1, b2 in itertools.pairwise(bands)]
    assert all(abs(g - day_view._TIER_COMFORTABLE.card_gap) <= 1 for g in gaps), (
        gaps, "expected comfortable-tier spacing, not compact"
    )


def test_pathological_long_summary_folds_into_overflow_via_safety_net():
    """A single event whose summary wraps into far more lines than any tier's
    assumed card height can hold must fold into the overflow row rather than
    drawing (or clipping) an oversized card."""
    day = datetime(2026, 9, 9, tzinfo=timezone.utc)
    huge_summary = "word " * 400
    event = Event(
        id="a",
        summary=huge_summary,
        start=day.replace(hour=9),
        end=day.replace(hour=9, minute=30),
        all_day=False,
        calendar_id="primary",
        color="red",
    )
    image = day_view.render([event], day.date(), RESOLUTION)
    start_y, column_right = _start_y_and_column_right(image.width)

    rows = _ink_rows(image, start_y - 5, image.height, MARGIN, column_right)
    bands = _bands(rows)

    assert len(bands) == 1, f"expected the oversized card to fold into one overflow band: {bands}"
    band_h = bands[0][1] - bands[0][0] + 1
    assert band_h < 60, f"expected a small overflow row, got a {band_h}px band (safety net didn't trigger)"
    assert bands[0][0] - start_y <= 1, "overflow row should sit at the top, not after a failed full-size card"
