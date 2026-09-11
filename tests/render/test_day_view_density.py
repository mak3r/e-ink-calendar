"""Regression coverage for #151: day-view light-day density tiers.

See ``.claude/plans/day-view-light-day-scaling.md`` for the design this
implements. Covers the tier-selection boundaries, the "space-around"
vertical-distribution math for a light day, the busy-day worst case staying
pixel-equivalent to the original fixed compact sizing, and the safety-net
fallback for a card too tall to fit even at the compact tier.
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


def test_busy_day_worst_case_uses_fixed_compact_stacking_with_no_slack():
    """max_entries=9 worst case (8 visible + overflow): compact tier, cards
    top-anchored immediately after the rule with the fixed 5px gap — the
    original algorithm, not space-around."""
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


def test_light_day_space_around_gaps_are_equal():
    """A 2-event (spacious-tier) day spreads its cards with equal ``slot``
    slack per the plan's §3.2 formula: leading and trailing gaps are pure
    ``slot``, and the inter-card gap is the tier's base ``card_gap`` plus
    that same ``slot`` (``gap_between = base_gap + slot``)."""
    when = datetime(2026, 9, 9, tzinfo=timezone.utc).date()
    image = day_view.render(_events(2), when, RESOLUTION)
    start_y, column_right = _start_y_and_column_right(image.width)

    rows = _ink_rows(image, start_y - 5, image.height, MARGIN, column_right)
    bands = _bands(rows)
    assert len(bands) == 2, bands

    bottom_bound = image.height - MARGIN
    leading = bands[0][0] - start_y
    between = bands[1][0] - bands[0][1] - 1
    trailing = (bottom_bound - 1) - bands[1][1]

    assert leading > 0 and between > 0 and trailing > 0, (leading, between, trailing)
    assert abs(leading - trailing) <= 2, (leading, trailing)
    slot = (leading + trailing) / 2
    assert abs(between - (slot + day_view._TIER_SPACIOUS.card_gap)) <= 2, (between, slot)


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
