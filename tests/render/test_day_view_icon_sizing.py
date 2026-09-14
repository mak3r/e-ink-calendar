"""Coverage for #204: sunrise/sunset icon width-matching (#203/PR #205).

Covers the four acceptance criteria from #204: the icon size passed to
``_draw_sun_icon`` matches the wider of the label/time text columns, both
the rising and setting icons share that one size (not independently
computed), the moon icon's size stays keyed to the fixed ``_ICON_SIZE``
regardless of how wide the sunrise/sunset icon grows, and a wide 24-hour
time value like "20:43" still fits within ``_WIDGET_DAWN_DUSK_H`` without
spilling into the moon widget below it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from eink_calendar.render import day_view
from eink_calendar.render.layout_common import MARGIN, text_size, vendored_font
from eink_calendar.weather_source.models import WeatherSnapshot

RESOLUTION = (800, 480)


def _widget_bounds(width: int) -> tuple[int, int]:
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    return widget_left, width - MARGIN


def _expected_icon_size(sunrise: datetime, sunset: datetime) -> int:
    """Replicates ``_draw_dawn_dusk_widget``'s own icon-sizing formula."""
    label_font = vendored_font(size=day_view._FONT_WIDGET_LABEL)
    time_font = vendored_font(bold=True, size=day_view._FONT_TIME_VALUE)
    return max(
        text_size("Sunrise", font=label_font)[0],
        text_size("Sunset", font=label_font)[0],
        text_size(sunrise.strftime("%H:%M"), font=time_font)[0],
        text_size(sunset.strftime("%H:%M"), font=time_font)[0],
    )


def _horizon_run_length(image, x0: int, horizon_y: int) -> int:
    """Length of the icon's horizontal horizon line starting at ``x0`` — the
    line is drawn ``size`` px wide (``_draw_sun_icon``'s ``draw.line`` call
    spans ``[x, x + size]``), so its pixel run length reveals the actual
    ``size`` the icon was drawn with, independent of any dome/triangle ink."""
    px = image.load()
    x = x0
    while px[x, horizon_y] == (0, 0, 0):
        x += 1
    return x - x0


def test_icon_size_matches_the_widest_label_or_time_text_column():
    width = RESOLUTION[0]
    widget_left, _ = _widget_bounds(width)
    sunrise = datetime(2026, 9, 9, 6, 33, tzinfo=timezone.utc)
    sunset = datetime(2026, 9, 9, 19, 11, tzinfo=timezone.utc)
    snapshot = WeatherSnapshot(weather=None, sunrise=sunrise, sunset=sunset, moon_phase="Full Moon")
    image = day_view.render([], sunrise.date(), RESOLUTION, weather=snapshot)

    expected_size = _expected_icon_size(sunrise, sunset)
    horizon_y = round(MARGIN + day_view._WIDGET_PAD + expected_size * 0.45)
    sunrise_x0 = widget_left + day_view._WIDGET_PAD

    run = _horizon_run_length(image, sunrise_x0, horizon_y)
    # The horizon line is drawn with width=2, so its run is size+1 px.
    assert abs(run - 1 - expected_size) <= 1, (
        f"sunrise icon's horizon-line run ({run}px) doesn't match the expected "
        f"text-derived icon size ({expected_size}px)"
    )


def test_rising_and_setting_icons_share_the_same_size():
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    half_w = (widget_right - widget_left) // 2
    sunrise = datetime(2026, 9, 9, 6, 33, tzinfo=timezone.utc)
    sunset = datetime(2026, 9, 9, 19, 11, tzinfo=timezone.utc)
    snapshot = WeatherSnapshot(weather=None, sunrise=sunrise, sunset=sunset, moon_phase="Full Moon")
    image = day_view.render([], sunrise.date(), RESOLUTION, weather=snapshot)

    expected_size = _expected_icon_size(sunrise, sunset)
    horizon_y = round(MARGIN + day_view._WIDGET_PAD + expected_size * 0.45)
    sunrise_x0 = widget_left + day_view._WIDGET_PAD
    sunset_x0 = widget_left + half_w + day_view._WIDGET_PAD // 2

    rising_run = _horizon_run_length(image, sunrise_x0, horizon_y)
    setting_run = _horizon_run_length(image, sunset_x0, horizon_y)
    assert rising_run == setting_run, (
        f"rising icon ({rising_run}px) and setting icon ({setting_run}px) were "
        "sized independently instead of sharing one max() size"
    )


def test_moon_icon_size_stays_fixed_regardless_of_sunrise_sunset_icon_width():
    """A long sunrise/sunset time widens that icon well past ``_ICON_SIZE``
    (#203) — the moon icon below must stay unaffected, still keyed to the
    fixed module-level ``_ICON_SIZE`` directly."""
    width = RESOLUTION[0]
    widget_left, _ = _widget_bounds(width)
    # "20:43" forces an icon_size well above the fixed _ICON_SIZE=28.
    when = datetime(2026, 9, 9, 20, 43, tzinfo=timezone.utc)
    snapshot = WeatherSnapshot(weather=None, sunrise=when, sunset=when, moon_phase="Full Moon")
    image = day_view.render([], when.date(), RESOLUTION, weather=snapshot)

    dawn_dusk_icon_size = _expected_icon_size(when, when)
    assert dawn_dusk_icon_size > day_view._ICON_SIZE, (
        "fixture didn't actually widen the sunrise/sunset icon past _ICON_SIZE "
        "-- test no longer exercises the case it's meant to guard"
    )

    moon_top = MARGIN + day_view._WIDGET_DAWN_DUSK_H + day_view._WIDGET_V_GAP
    moon_icon_x0 = widget_left + day_view._WIDGET_PAD
    moon_icon_y0 = moon_top + (day_view._WIDGET_MOON_H - day_view._ICON_SIZE) // 2
    mid_y = moon_icon_y0 + day_view._ICON_SIZE // 2

    px = image.load()
    # Scan only a window around the icon itself, not out to
    # dawn_dusk_icon_size -- the phase-name text drawn to the icon's right
    # sits on this same row and would otherwise get counted as icon ink.
    xs = [
        x
        for x in range(moon_icon_x0 - 3, moon_icon_x0 + day_view._ICON_SIZE + 3)
        if px[x, mid_y] == (0, 0, 0)
    ]
    assert xs, "no moon icon ink found at its expected midline row"
    moon_w = max(xs) - min(xs) + 1
    # Outline stroke width=2 puts the measured span at _ICON_SIZE+1.
    assert abs(moon_w - 1 - day_view._ICON_SIZE) <= 1, (
        f"moon icon width ({moon_w}px) drifted from the fixed _ICON_SIZE "
        f"({day_view._ICON_SIZE}px) -- looks coupled to the dawn/dusk icon size"
    )


def test_wide_time_value_does_not_overflow_the_dawn_dusk_widget_height():
    """A 24-hour value like "20:43" widens the icon and its label/value
    stack — none of that content may spill past ``_WIDGET_DAWN_DUSK_H`` into
    the gap before the moon widget's own border below it."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    when = datetime(2026, 9, 9, 20, 43, tzinfo=timezone.utc)
    snapshot = WeatherSnapshot(weather=None, sunrise=when, sunset=when, moon_phase="Full Moon")
    image = day_view.render([], when.date(), RESOLUTION, weather=snapshot)

    box_bottom = MARGIN + day_view._WIDGET_DAWN_DUSK_H
    # Skip the box's own border stroke (a couple rows straddling box_bottom)
    # and stop short of the moon widget's own top border below the gap.
    gap_top = box_bottom + 1 + day_view._WIDGET_BORDER_W
    gap_bottom = box_bottom + day_view._WIDGET_V_GAP - day_view._WIDGET_BORDER_W - 1

    px = image.load()
    overflow = [
        (x, y)
        for y in range(gap_top, gap_bottom)
        for x in range(widget_left + 3, widget_right - 3)
        if px[x, y] == (0, 0, 0)
    ]
    assert not overflow, (
        f"found {len(overflow)} ink pixel(s) below the dawn/dusk widget's "
        f"border, e.g. {overflow[0]} -- content overflowed _WIDGET_DAWN_DUSK_H"
    )
