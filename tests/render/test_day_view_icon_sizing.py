"""Coverage for #209/#210: dawn/dusk widget final sizing (time font fills
the available width, icon is a fixed size, both columns are centered, and
the triangle is shrunk relative to the dome).

Supersedes an earlier revision of this file written for #203/#204/#205:
that revision assumed the icon's size was derived from the label/time text
width and that both columns were left-aligned at ``x0 + _WIDGET_PAD`` --
#209's approved spec (see the issue's HANDOFF comment) replaced both of
those with a fixed ``_DAWN_DUSK_ICON_SIZE`` and centered columns, so this
file tests the current behavior rather than extending the old one.

Note: #210's originally-filed acceptance criteria described the icon as
still being sized to the (now wider) text -- "re-pointed at the
fits-to-width font". The approved spec that actually shipped (#209's
HANDOFF) instead made the icon a fixed constant, independent of the time
text's width, for the documented reason that 1:1 text-matching breaks down
once the time font is genuinely maximized. This file tests what's
actually merged.

#219 added a cap (``_FONT_TIME_VALUE_MAX``) on the fits-to-width time
font's growth, a scale/offset pair (``_DAWN_DUSK_ARROW_SCALE``,
``_DAWN_DUSK_ARROW_OFFSET_Y``) on the rising/setting triangle, and an
``_MOON_ICON_OFFSET_X`` nudge on the moon icon -- ``_dawn_dusk_layout``
below and the triangle/moon-icon assertions are updated to replicate
those, rather than the pre-#219 formulas.
"""

from __future__ import annotations

from datetime import datetime, timezone

from eink_calendar.render import day_view
from eink_calendar.render.layout_common import (
    MARGIN,
    line_height,
    text_size,
    vendored_font,
)
from eink_calendar.weather_source.models import WeatherSnapshot

_SUNRISE = datetime(2026, 9, 9, 6, 33, tzinfo=timezone.utc)
_SUNSET = datetime(2026, 9, 9, 19, 11, tzinfo=timezone.utc)
_NARROW_WIDTH = 650  # half_w=71 -- room for the fixed 56px icon, tight for text
_WIDE_WIDTH = 1200  # half_w=140 -- plenty of room for the time font to grow


def _dawn_dusk_layout(width: int) -> tuple[int, int, int, float, float, int]:
    """Replicates ``_draw_dawn_dusk_widget``'s own formulas: the
    fits-to-width time font (grow, check it fits, step back one), the
    fixed icon size, and the vertical centering-by-ink-extent math -- so
    tests can predict exact pixel positions instead of just re-deriving
    the source's own conclusion. Returns (widget_left, half_w, icon_size,
    icon_top, horizon_y, time_size)."""
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    widget_right = width - MARGIN
    half_w = (widget_right - widget_left) // 2

    available_w = half_w - 2 * day_view._WIDGET_PAD
    time_size = day_view._FONT_TIME_VALUE
    while time_size < day_view._FONT_TIME_VALUE_MAX:
        candidate = vendored_font(bold=True, size=time_size + 1)
        widest = max(
            text_size(_SUNRISE.strftime("%H:%M"), font=candidate)[0],
            text_size(_SUNSET.strftime("%H:%M"), font=candidate)[0],
        )
        if widest > available_w:
            break
        time_size += 1
    time_font = vendored_font(bold=True, size=time_size)
    label_font = vendored_font(size=day_view._FONT_WIDGET_LABEL)

    icon_size = day_view._DAWN_DUSK_ICON_SIZE
    dome_top_offset = icon_size * 0.09
    ink_bottom_offset = icon_size * 0.655
    label_h = line_height(label_font)
    value_h = line_height(time_font)
    ink_gap, value_gap = 4, 2  # tightened per #214
    content_h = (ink_bottom_offset - dome_top_offset) + ink_gap + label_h + value_gap + value_h
    margin = (day_view._WIDGET_DAWN_DUSK_H - content_h) / 2
    icon_top = MARGIN + margin - dome_top_offset
    horizon_y = icon_top + icon_size * 0.45
    return widget_left, half_w, icon_size, icon_top, horizon_y, time_size


def _horizon_run_length(image, x0: int, horizon_y: int) -> int:
    """Length of the icon's horizontal horizon line starting at ``x0`` --
    the line is drawn ``size`` px wide, so its pixel run length reveals
    the actual rendered icon size."""
    px = image.load()
    x = x0
    while px[x, horizon_y] == (0, 0, 0):
        x += 1
    return x - x0


def _render(width: int):
    snapshot = WeatherSnapshot(weather=None, sunrise=_SUNRISE, sunset=_SUNSET, moon_phase="Full Moon")
    return day_view.render([], _SUNRISE.date(), (width, 480), weather=snapshot)


def test_time_font_grows_to_the_cap_on_a_wide_panel():
    """On a panel this wide, the old fits-to-width loop would keep growing
    past the size that used to cap it -- #219's ``_FONT_TIME_VALUE_MAX``
    stops it there instead, even though a still-larger size would render
    within the available width."""
    _widget_left, half_w, _icon_size, _icon_top, _horizon_y, time_size = _dawn_dusk_layout(_WIDE_WIDTH)
    assert time_size == day_view._FONT_TIME_VALUE_MAX, (
        f"expected growth to stop at _FONT_TIME_VALUE_MAX "
        f"({day_view._FONT_TIME_VALUE_MAX}pt), got {time_size}pt"
    )

    available_w = half_w - 2 * day_view._WIDGET_PAD
    time_font = vendored_font(bold=True, size=time_size)
    rendered_w = text_size(_SUNRISE.strftime("%H:%M"), font=time_font)[0]
    assert rendered_w <= available_w, (
        f"chosen size {time_size}pt renders {rendered_w}px, wider than the "
        f"{available_w}px available"
    )

    # Confirm the cap is actually binding on this fixture -- i.e. without
    # it, growth would have continued past the max, so this result isn't
    # just incidentally the same as the old fits-to-width limit.
    one_bigger = vendored_font(bold=True, size=time_size + 1)
    bigger_w = text_size(_SUNRISE.strftime("%H:%M"), font=one_bigger)[0]
    assert bigger_w <= available_w, (
        "fixture doesn't actually exercise the cap -- the next size up "
        f"({time_size + 1}pt, {bigger_w}px) wouldn't fit in {available_w}px "
        "anyway, so this result would be the same with or without "
        "_FONT_TIME_VALUE_MAX"
    )


def test_time_font_is_smaller_on_a_narrower_panel():
    """The fits-to-width formula must respond to the space actually
    available, not just always grow to some large fixed size."""
    _wl, _hw, _isz, _it, _hy, narrow_size = _dawn_dusk_layout(_NARROW_WIDTH)
    _wl, _hw, _isz, _it, _hy, wide_size = _dawn_dusk_layout(_WIDE_WIDTH)
    assert narrow_size < wide_size, (
        f"narrow-panel size ({narrow_size}pt) should be smaller than the "
        f"wide-panel size ({wide_size}pt) -- font doesn't look width-fitted"
    )


def test_icon_size_is_fixed_regardless_of_how_wide_the_time_font_grows():
    """Since #209, the icon's size no longer scales with the time text's
    width (unlike #203/#205) -- it's the fixed ``_DAWN_DUSK_ICON_SIZE``
    whether the panel is narrow or wide."""
    for width in (_NARROW_WIDTH, _WIDE_WIDTH):
        widget_left, half_w, icon_size, _icon_top, horizon_y, _time_size = _dawn_dusk_layout(width)
        image = _render(width)

        cx_sunrise = widget_left + half_w / 2
        x0 = round(cx_sunrise - icon_size / 2)
        run = _horizon_run_length(image, x0, round(horizon_y))
        assert abs(run - 1 - day_view._DAWN_DUSK_ICON_SIZE) <= 1, (
            f"width={width}: icon horizon-line run ({run}px) doesn't match "
            f"the fixed _DAWN_DUSK_ICON_SIZE ({day_view._DAWN_DUSK_ICON_SIZE}px)"
        )


def test_columns_are_centered_within_their_half_width_not_left_aligned():
    """#205 left-aligned each column's icon at ``x0 + _WIDGET_PAD`` -- #209
    centers the whole icon+label+value block within its half instead. This
    predicts the icon's position from the *centered* formula and confirms
    real ink appears there; if the code still left-aligned, this would
    fail because the line would start much further left."""
    width = _WIDE_WIDTH
    widget_left, half_w, icon_size, _icon_top, horizon_y, _time_size = _dawn_dusk_layout(width)
    image = _render(width)
    hy = round(horizon_y)

    cx_sunrise = widget_left + half_w / 2
    cx_sunset = widget_left + half_w + half_w / 2

    for cx in (cx_sunrise, cx_sunset):
        x0 = round(cx - icon_size / 2)
        run = _horizon_run_length(image, x0, hy)
        assert abs(run - 1 - icon_size) <= 1, (
            f"no centered icon found at predicted x0={x0} for cx={cx} "
            f"(run={run}px) -- column doesn't look centered within half_w"
        )

    # Sanity: the old left-aligned position would have put the icon flush
    # against the border, far from either computed center.
    old_left_aligned_x0 = widget_left + day_view._WIDGET_PAD
    assert abs(old_left_aligned_x0 - round(cx_sunrise - icon_size / 2)) > icon_size / 2, (
        "centered and left-aligned positions coincide -- fixture doesn't "
        "actually distinguish the two layouts"
    )


def test_triangle_is_shrunk_relative_to_the_dome():
    """#209 shrunk ``tri_half_w`` from ``size * 0.26`` to ``size * 0.19``;
    #219 further scales it by ``_DAWN_DUSK_ARROW_SCALE`` (0.75) and shifts
    its vertical center by ``_DAWN_DUSK_ARROW_OFFSET_Y`` -- the triangle's
    base (its widest row) must measure close to
    ``2 * size * 0.19 * _DAWN_DUSK_ARROW_SCALE``, not the old, wider
    proportion."""
    width = _WIDE_WIDTH
    widget_left, half_w, icon_size, _icon_top, horizon_y, _time_size = _dawn_dusk_layout(width)
    image = _render(width)
    px = image.load()

    cx_sunrise = widget_left + half_w / 2
    tri_half_w = icon_size * 0.19 * day_view._DAWN_DUSK_ARROW_SCALE
    band_center = horizon_y + icon_size * 0.015 + day_view._DAWN_DUSK_ARROW_OFFSET_Y
    band_bottom = band_center + tri_half_w  # sunrise (rising) triangle's base row

    # int(), not round() -- the base row is the triangle's LAST ink row, so
    # a float that rounds up one row past band_bottom lands just past it.
    y = int(band_bottom)
    lo = int(cx_sunrise - icon_size / 2) - 2
    hi = int(cx_sunrise + icon_size / 2) + 2
    xs = [x for x in range(lo, hi) if px[x, y] == (0, 0, 0)]
    assert xs, "no triangle base ink found at the predicted band_bottom row"
    measured_w = max(xs) - min(xs) + 1

    expected_w = 2 * tri_half_w
    assert abs(measured_w - expected_w) <= 3, (
        f"triangle base width ({measured_w}px) doesn't match the shrunk "
        f"proportion size*0.19*2={expected_w:.1f}px -- looks pinned to the "
        f"old, wider size*0.26 ratio instead"
    )
    old_expected_w = 2 * icon_size * 0.26
    assert abs(measured_w - old_expected_w) > 3, (
        "measured width matches the OLD size*0.26 proportion -- triangle "
        "doesn't look shrunk"
    )


def test_moon_icon_size_stays_fixed_regardless_of_dawn_dusk_icon_size():
    """The moon icon is unrelated to the dawn/dusk widget's own sizing and
    must stay keyed to the fixed ``_ICON_SIZE`` directly (at its
    ``_MOON_ICON_OFFSET_X``-nudged x position, per #219)."""
    width = _WIDE_WIDTH
    widget_left, _half_w, _icon_size, _icon_top, _horizon_y, _time_size = _dawn_dusk_layout(width)
    image = _render(width)

    moon_top = MARGIN + day_view._WIDGET_DAWN_DUSK_H + day_view._WIDGET_V_GAP
    moon_icon_x0 = widget_left + day_view._WIDGET_PAD + day_view._MOON_ICON_OFFSET_X
    moon_icon_y0 = moon_top + (day_view._WIDGET_MOON_H - day_view._ICON_SIZE) // 2
    mid_y = moon_icon_y0 + day_view._ICON_SIZE // 2

    px = image.load()
    xs = [
        x
        for x in range(moon_icon_x0 - 3, moon_icon_x0 + day_view._ICON_SIZE + 3)
        if px[x, mid_y] == (0, 0, 0)
    ]
    assert xs, "no moon icon ink found at its expected midline row"
    moon_w = max(xs) - min(xs) + 1
    assert abs(moon_w - 1 - day_view._ICON_SIZE) <= 1, (
        f"moon icon width ({moon_w}px) drifted from the fixed _ICON_SIZE "
        f"({day_view._ICON_SIZE}px)"
    )
