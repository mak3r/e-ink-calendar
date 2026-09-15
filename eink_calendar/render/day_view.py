"""Day view: today's events as a column of deduplicated, card-style entries.

Identical events booked on more than one configured calendar are merged into a
single card whose left-edge accent stripe splits into one band per source
calendar color; a color/label legend in the header band maps each color back
to a calendar name. Cards occupy the left three-quarters of the panel — the
right quarter is reserved for a future widget. See
``.claude/plans/day-view-card-redesign.md`` (persona/product-designer branch)
for the approved design this implements.

Card sizing scales with how many cards actually render — a light day gets
larger cards instead of small ones with dead space below them — per
``.claude/plans/day-view-density-stacking-fix.md`` (which supersedes the
"space-around" distribution and hardcoded-busy-tier approach originally
proposed in ``day-view-light-day-scaling.md``). Cards always stack top-down,
immediately under the rule, with only the selected tier's fixed gap between
them; any leftover column space stays blank below the last card (or the
overflow row) rather than being distributed. The tier is picked from how
many cards actually render, uniformly, whether or not the ``max_entries``
cap trimmed anything — so a lower cap's own worst case renders at a larger
tier, while the ``max_entries=9`` worst case (8-9 visible) still lands on the
same fixed "compact" tier as the original #127 design and stays
pixel-identical to it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime

from PIL import Image, ImageDraw

from eink_calendar.calendar_source.models import Event
from eink_calendar.render.layout_common import (
    MARGIN,
    draw_text,
    line_height,
    text_size,
    vendored_font,
    wrap_text,
)
from eink_calendar.render.palette import ACCENT_COLORS, color
from eink_calendar.weather_source.models import WeatherSnapshot

__all__ = ["render"]

_FONT_DAY_NAME = 42
_FONT_DATE = 17
_FONT_KEY = 14

# Day name -> date line, date line -> rule (tight), rule -> first card (roomy).
_DATE_TOP_GAP = 2
_RULE_GAP_ABOVE = 2
_RULE_GAP_BELOW = 8

_KEY_GAP = 16  # between calendar-key legend entries

_COLUMN_FRACTION = 0.75  # event column occupies the left 3/4 of the panel
_BORDER_W = 2  # constant across every tier
_STRIPE_INSET = 2  # keeps the stripe clear of the rounded corners
_SWATCH = 12  # calendar-key legend swatch

# Widget column (dawn/dusk, moon phase, weather) — see
# .claude/plans/day-view-widget-column.md and the post-deploy fixes in
# .claude/plans/day-view-widget-column-fixes.md. Runs the full panel height,
# independent of the calendar column's header/rule.
_WIDGET_GAP = 12  # calendar column's right edge -> widget column's left edge
_WIDGET_V_GAP = 10  # between the three stacked widgets
_WIDGET_PAD = 8
_WIDGET_BORDER_W = 2
_WIDGET_CORNER_RADIUS = 8
_WIDGET_DAWN_DUSK_H = 104  # bumped from 76 once the icon grew to match its text column's width (#203)
_WIDGET_MOON_H = 76
_FONT_WIDGET_LABEL = 13
_FONT_WIDGET_TITLE = 15
_FONT_TIME_VALUE = 14  # starting point _draw_dawn_dusk_widget grows from to fill the available width (#209)
_FONT_TIME_VALUE_MAX = 20  # ceiling on that growth; lower this to size the time text directly
_ICON_SIZE = 44  # moon phase icon
_MOON_ICON_OFFSET_X = 10  # nudges the icon right of its padding-only position
_DAWN_DUSK_ICON_SIZE = 56  # sun icon: a fixed constant, independent of the time text's width (#209)
_DAWN_DUSK_ARROW_SCALE = 0.75  # scales the rising/setting triangle, both icons together
_DAWN_DUSK_ARROW_OFFSET_Y = 2  # raises (negative) / lowers (positive) that triangle, both icons together

# Weather widget: H/L at the top (larger than other widget labels), then
# each forecast period as a stacked row (label line, then icon + temp).
_FONT_HL_LABEL = 13
_FONT_HL_VALUE = 22
_FONT_FORECAST_LABEL = 14
_FONT_FORECAST_TEMP = 26
_FORECAST_ICON_SIZE = 36
_FORECAST_OFFSET_X = 16  # shifts the label/icon/temp column right, as one unit

# astral's 8 named phases -> fraction of the disk illuminated (0=new, 1=full).
_MOON_LIT_FRACTION = {
    "New Moon": 0.0,
    "Waxing Crescent": 0.25,
    "First Quarter": 0.5,
    "Waxing Gibbous": 0.75,
    "Full Moon": 1.0,
    "Waning Gibbous": 0.75,
    "Last Quarter": 0.5,
    "Waning Crescent": 0.25,
}
_MOON_WAXING = frozenset(
    {"Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon"}
)


@dataclass(frozen=True)
class _Tier:
    """Card-sizing constants for one density tier.

    ``compact`` reuses the original day-view-card-redesign (#127) numbers
    exactly, so a render that ends up in the compact tier with no overflow
    trimming looks the same as before this feature existed.
    """

    name: str
    font_label: int
    font_summary: int
    card_pad: int
    stripe_w: int
    corner_radius: int
    card_gap: int


_TIER_COMPACT = _Tier("compact", font_label=14, font_summary=15, card_pad=5, stripe_w=10, corner_radius=6, card_gap=5)
_TIER_COMFORTABLE = _Tier("comfortable", font_label=18, font_summary=20, card_pad=7, stripe_w=13, corner_radius=8, card_gap=7)
_TIER_SPACIOUS = _Tier("spacious", font_label=22, font_summary=24, card_pad=8, stripe_w=16, corner_radius=10, card_gap=8)

# Most spacious first, so _tier_down() always steps toward compact.
_TIERS = (_TIER_SPACIOUS, _TIER_COMFORTABLE, _TIER_COMPACT)


def _tier_for(visible_count: int) -> _Tier:
    """Density tier for a card count already limited by ``max_entries``."""
    if visible_count <= 3:
        return _TIER_SPACIOUS
    if visible_count <= 6:
        return _TIER_COMFORTABLE
    return _TIER_COMPACT


def _tier_down(tier: _Tier) -> _Tier:
    """One step more compact than ``tier`` (a no-op already at compact)."""
    index = _TIERS.index(tier)
    return _TIERS[min(index + 1, len(_TIERS) - 1)]


@dataclass
class _Group:
    """One or more identical (summary, start, end, all_day) events merged
    into a single card; ``colors`` holds each source event's color, in
    first-seen order (capped at 5: the 4 accents plus the "black" fallback)."""

    summary: str
    start: datetime
    end: datetime
    all_day: bool
    colors: list[str] = field(default_factory=list)


def _swatch_color(event: Event) -> str:
    return event.color if event.color in ACCENT_COLORS else "black"


def _dedupe(events: list[Event]) -> list[_Group]:
    groups: dict[tuple, _Group] = {}
    order: list[tuple] = []
    for event in events:
        key = (event.summary, event.start, event.end, event.all_day)
        group = groups.get(key)
        if group is None:
            group = _Group(
                summary=event.summary, start=event.start, end=event.end, all_day=event.all_day
            )
            groups[key] = group
            order.append(key)
        c = _swatch_color(event)
        if c not in group.colors:
            group.colors.append(c)
    return [groups[key] for key in order]


def render(
    events: list[Event],
    when: date,
    resolution: tuple[int, int],
    *,
    calendar_labels: dict[str, str] | None = None,
    max_entries: int = 9,
    weather: WeatherSnapshot | None = None,
) -> Image.Image:
    """Render ``when``'s events as a header + card list, plus a dawn/dusk +
    moon phase + weather widget column in the reserved right quarter.

    ``calendar_labels`` maps a swatch color (as used by :func:`_swatch_color`)
    to a human calendar label, for the header legend — typically built from
    ``AccountConfig.calendars`` (``color -> label``). ``max_entries`` caps the
    number of cards shown before an overflow row summarizes the rest.
    ``weather`` is ``None`` when no ``weather:`` location is configured, in
    which case the widget column is left blank (as it was before this
    feature existed); when present but its ``.weather`` reading is ``None``
    (cold start, failed fetch), the weather widget alone is omitted — the
    always-available dawn/dusk and moon phase widgets still render.
    """
    width, height = resolution
    image = Image.new("RGB", resolution, color("white"))
    draw = ImageDraw.Draw(image)

    day_font = vendored_font(bold=True, size=_FONT_DAY_NAME)
    date_font = vendored_font(size=_FONT_DATE)
    key_font = vendored_font(size=_FONT_KEY)

    day_name = when.strftime("%A")
    draw_text(image, (MARGIN, MARGIN), day_name, fill="black", font=day_font)
    day_name_h = text_size(day_name, font=day_font)[1]

    date_y = MARGIN + day_name_h + _DATE_TOP_GAP
    date_line = when.strftime("%d %B %Y")
    draw_text(image, (MARGIN, date_y), date_line, fill="black", font=date_font)
    date_h = text_size(date_line, font=date_font)[1]

    todays = [e for e in events if e.occurs_on(when)]
    groups = sorted(_dedupe(todays), key=lambda g: (not g.all_day, g.start))

    column_right = MARGIN + round((width - 2 * MARGIN) * _COLUMN_FRACTION)
    widget_left = column_right + _WIDGET_GAP

    _draw_calendar_key(
        image, draw, groups, calendar_labels or {}, column_right, key_font,
        date_y, date_h,
    )

    rule_y = date_y + date_h + _RULE_GAP_ABOVE
    draw.line([(MARGIN, rule_y), (column_right, rule_y)], fill=color("black"))

    _draw_widget_column(image, draw, weather, widget_left, width, height)

    if len(groups) > max_entries:
        visible, overflow = groups[: max_entries - 1], groups[max_entries - 1 :]
    else:
        visible, overflow = groups, []

    start_y = rule_y + _RULE_GAP_BELOW

    if not visible:
        _draw_no_events(image, column_right, start_y, height)
        return image

    # Pick a density tier for however many cards actually render — uniformly,
    # whether or not max_entries trimmed anything (a lower cap's own worst
    # case then naturally lands on a bigger tier). Step down a tier if the
    # whole block doesn't fit; _draw_stacked's own per-card check is the
    # final fallback if even the compact tier doesn't fit.
    available_h = (height - MARGIN) - start_y
    tier = _tier_for(len(visible))
    while True:
        label_font = vendored_font(bold=True, size=tier.font_label)
        summary_font = vendored_font(bold=True, size=tier.font_summary)
        block_h = sum(
            _layout_card(g, label_font, summary_font, column_right, tier)[1] for g in visible
        ) + tier.card_gap * (len(visible) - 1)
        if block_h <= available_h or tier is _TIER_COMPACT:
            break
        tier = _tier_down(tier)

    y, overflow = _draw_stacked(
        image, draw, visible, tier, label_font, summary_font, column_right, start_y, height, overflow,
    )
    if overflow:
        _draw_overflow_row(image, draw, y, column_right, overflow, label_font, tier)

    return image


def _draw_no_events(image: Image.Image, column_right: int, start_y: int, height: int) -> None:
    """Zero events today: "No events", at the spacious tier's size, centered
    (both axes) in the event column instead of left-anchored under the rule."""
    font = vendored_font(bold=True, size=_TIER_SPACIOUS.font_summary)
    text = "No events"
    tw, th = text_size(text, font=font)
    cx = (MARGIN + column_right) // 2
    cy = (start_y + (height - MARGIN)) // 2
    draw_text(image, (cx - tw // 2, cy - th // 2), text, fill="black", font=font)


def _draw_stacked(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    visible: list[_Group],
    tier: _Tier,
    label_font,
    summary_font,
    column_right: int,
    start_y: int,
    height: int,
    overflow: list[_Group],
) -> tuple[int, list[_Group]]:
    """Draw ``visible`` top-down at ``tier``: first card under the rule, each
    next one offset by the previous card's height plus ``tier.card_gap`` —
    the only card-drawing loop; no distributed leftover space, ever. Folds
    any card that doesn't fit (and everything after it) into ``overflow``
    instead of drawing off-panel. Returns the y position after the last
    drawn card and the (possibly extended) overflow list.
    """
    y = start_y
    for i, group in enumerate(visible):
        wrapped, card_h, layout = _layout_card(group, label_font, summary_font, column_right, tier)
        if y + card_h > height - MARGIN:
            overflow = visible[i:] + overflow
            break
        _draw_card(image, draw, y, column_right, group, wrapped, card_h, layout, label_font, summary_font, tier)
        y += card_h + tier.card_gap
    return y, overflow


def _draw_calendar_key(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    groups: list[_Group],
    calendar_labels: dict[str, str],
    right_edge: int,
    key_font,
    header_top: int,
    header_h: int,
) -> None:
    """Right-aligned legend (swatch + label) for each distinct color among
    today's events, vertically centered on the date row, right-aligned to
    where the widget column begins."""
    colors_seen: list[str] = []
    for g in groups:
        for c in g.colors:
            if c not in colors_seen:
                colors_seen.append(c)
    if not colors_seen:
        return

    entries = [(c, calendar_labels.get(c, c.title())) for c in colors_seen]
    widths = [_SWATCH + 6 + text_size(label, font=key_font)[0] for _, label in entries]
    total_w = sum(widths) + _KEY_GAP * (len(entries) - 1)

    text_h = line_height(key_font)
    x = right_edge - total_w
    y = header_top + (header_h - _SWATCH) // 2
    text_y = header_top + (header_h - text_h) // 2
    for (c, label), w in zip(entries, widths):
        draw.rectangle(
            [(x, y), (x + _SWATCH, y + _SWATCH)], fill=color(c), outline=color("black")
        )
        draw_text(image, (x + _SWATCH + 6, text_y), label, fill="black", font=key_font)
        x += w + _KEY_GAP


def _draw_stripe(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], colors: list[str]) -> None:
    """Solid stripe for a single color; equal horizontal bands for several."""
    x0, y0, x1, y1 = box
    if len(colors) <= 1:
        draw.rectangle([(x0, y0), (x1, y1)], fill=color(colors[0] if colors else "black"))
        return
    band_h = (y1 - y0) / len(colors)
    for i, c in enumerate(colors):
        top = round(y0 + i * band_h)
        bottom = y1 if i == len(colors) - 1 else round(y0 + (i + 1) * band_h)
        draw.rectangle([(x0, top), (x1, bottom)], fill=color(c))


@dataclass(frozen=True)
class _CardLayout:
    stripe_x0: int
    stripe_x1: int
    text_x: int
    summary_x: int


def _layout_card(
    group: _Group, label_font, summary_font, column_right: int, tier: _Tier
) -> tuple[list[str], int, _CardLayout]:
    """Compute a card's wrapped summary, total height, and x-positions
    without drawing anything, so callers can check it fits before drawing."""
    label_w = max(
        text_size("ALL DAY", font=label_font)[0],
        text_size("00:00", font=label_font)[0],
    ) + tier.card_pad

    stripe_x0 = MARGIN + _BORDER_W + _STRIPE_INSET
    stripe_x1 = stripe_x0 + tier.stripe_w
    text_x = stripe_x1 + tier.card_pad
    summary_x = text_x + label_w
    summary_max_w = max(column_right - _BORDER_W - tier.card_pad - summary_x, 1)

    summary_line_h = line_height(summary_font)
    wrapped = wrap_text(group.summary, summary_max_w, font=summary_font) or [""]
    inner_h = max(summary_line_h * len(wrapped), line_height(label_font), tier.stripe_w)
    card_h = 2 * tier.card_pad + inner_h

    return wrapped, card_h, _CardLayout(stripe_x0, stripe_x1, text_x, summary_x)


def _draw_card(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    column_right: int,
    group: _Group,
    wrapped: list[str],
    card_h: int,
    layout: _CardLayout,
    label_font,
    summary_font,
    tier: _Tier,
) -> None:
    """Draw one rounded-rectangle event card at ``y`` per a prior :func:`_layout_card`."""
    box = (MARGIN, y, column_right, y + card_h)
    draw.rounded_rectangle(box, radius=tier.corner_radius, outline=color("black"), width=_BORDER_W)
    _draw_stripe(
        draw,
        (
            layout.stripe_x0,
            y + _BORDER_W + _STRIPE_INSET,
            layout.stripe_x1,
            y + card_h - _BORDER_W - _STRIPE_INSET,
        ),
        group.colors,
    )

    content_top = y + tier.card_pad
    when_label = "ALL DAY" if group.all_day else group.start.strftime("%H:%M")
    draw_text(image, (layout.text_x, content_top), when_label, fill="black", font=label_font)
    summary_line_h = line_height(summary_font)
    for i, seg in enumerate(wrapped):
        draw_text(
            image,
            (layout.summary_x, content_top + i * summary_line_h),
            seg,
            fill="black",
            font=summary_font,
        )


def _draw_overflow_row(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    column_right: int,
    hidden: list[_Group],
    label_font,
    tier: _Tier,
) -> None:
    """A segmented color band (one segment per distinct hidden color) plus a
    "+N more" count, glanceable in place of N plain-text rows. Drawn at
    ``tier`` — the same tier the visible cards above it used."""
    colors_seen: list[str] = []
    for g in hidden:
        for c in g.colors:
            if c not in colors_seen:
                colors_seen.append(c)

    band_h = line_height(label_font) + tier.card_pad
    band_w = min(120, column_right - MARGIN - 2 * tier.card_pad)
    x0, y0, x1, y1 = MARGIN, y, MARGIN + band_w, y + band_h
    draw.rectangle([(x0, y0), (x1, y1)], outline=color("black"), width=_BORDER_W)

    if colors_seen:
        inner_x0, inner_x1 = x0 + _BORDER_W, x1 - _BORDER_W
        seg_w = (inner_x1 - inner_x0) / len(colors_seen)
        for i, c in enumerate(colors_seen):
            sx0 = round(inner_x0 + i * seg_w)
            sx1 = inner_x1 if i == len(colors_seen) - 1 else round(inner_x0 + (i + 1) * seg_w)
            draw.rectangle([(sx0, y0 + _BORDER_W), (sx1, y1 - _BORDER_W)], fill=color(c))

    label = f"+{len(hidden)} more"
    text_y = y0 + (band_h - line_height(label_font)) // 2
    draw_text(image, (x1 + tier.card_pad, text_y), label, fill="black", font=label_font)


# -- widget column (dawn/dusk, moon phase, weather) -------------------------
#
# Three independently bordered, rounded-rectangle widgets stacked top to
# bottom in the panel's right quarter, matching the event cards' visual
# language (solid black border, rounded corners). Icons are hand-drawn flat
# PIL shapes in black/white only — palette.py reserves the four accent
# colors for per-calendar color-coding, so widgets (which aren't calendar
# data) stay black-on-white like the rest of the chrome.


def _draw_widget_column(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    weather: WeatherSnapshot | None,
    widget_left: int,
    width: int,
    height: int,
) -> None:
    if weather is None:
        return

    widget_right = width - MARGIN
    label_font = vendored_font(size=_FONT_WIDGET_LABEL)
    title_font = vendored_font(bold=True, size=_FONT_WIDGET_TITLE)

    y = MARGIN
    dawn_dusk_box = (widget_left, y, widget_right, y + _WIDGET_DAWN_DUSK_H)
    _draw_dawn_dusk_widget(image, draw, dawn_dusk_box, weather, label_font)
    y += _WIDGET_DAWN_DUSK_H + _WIDGET_V_GAP

    moon_box = (widget_left, y, widget_right, y + _WIDGET_MOON_H)
    _draw_moon_widget(image, draw, moon_box, weather, title_font)
    y += _WIDGET_MOON_H + _WIDGET_V_GAP

    if weather.weather is not None:
        weather_box = (widget_left, y, widget_right, height - MARGIN)
        _draw_weather_widget(image, draw, weather_box, weather.weather)


def _draw_dawn_dusk_widget(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    weather: WeatherSnapshot,
    label_font,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        box, radius=_WIDGET_CORNER_RADIUS, outline=color("black"), width=_WIDGET_BORDER_W
    )
    half_w = (x1 - x0) // 2
    frame_h = y1 - y0

    # Time value: the largest font whose "%H:%M" text still fits the
    # available half-width for both columns — grow from _FONT_TIME_VALUE
    # until it stops fitting, then back off one step, mirroring the
    # "grow, check it fits, step back" pattern already used elsewhere in
    # this file for tier fallback, applied to font point size instead of a
    # discrete tier (#209 requirement 1; #185 requirement 3 originally
    # picked the fixed starting size this now grows from).
    available_w = half_w - 2 * _WIDGET_PAD
    time_size = _FONT_TIME_VALUE
    while time_size < _FONT_TIME_VALUE_MAX:
        candidate = vendored_font(bold=True, size=time_size + 1)
        widest = max(
            text_size(weather.sunrise.strftime("%H:%M"), font=candidate)[0],
            text_size(weather.sunset.strftime("%H:%M"), font=candidate)[0],
        )
        if widest > available_w:
            break
        time_size += 1
    time_font = vendored_font(bold=True, size=time_size)

    # Icon size is a fixed constant, independent of the time text's width —
    # matching 1:1 (#203's approach) breaks down once the text is genuinely
    # maximized, since the icon would then need to be as wide (and thus as
    # tall) as the time text itself, which doesn't fit this fixed-height
    # widget alongside two lines of text below it (#209).
    icon_size = _DAWN_DUSK_ICON_SIZE

    # Center the whole icon+label+value block vertically in the widget,
    # using the icon's actual ink extent (from _draw_sun_icon's own
    # formulas: dome top at horizon_y - r = size*0.45 - size*0.36 =
    # size*0.09; band_bottom = size*0.465 + size*0.19 = size*0.655) rather
    # than its nominal reserved height, so there's no leftover gap baked
    # into the centering math (#209).
    dome_top_offset = icon_size * 0.09
    ink_bottom_offset = icon_size * 0.655
    label_h = line_height(label_font)
    value_h = line_height(time_font)
    ink_gap, value_gap = 4, 2  # tight -- sit close to the ink, not the icon's nominal box (#214)
    content_h = (ink_bottom_offset - dome_top_offset) + ink_gap + label_h + value_gap + value_h
    margin = (frame_h - content_h) / 2
    icon_top = y0 + margin - dome_top_offset  # so the dome's own top lands at y0 + margin

    for col_offset, label, value, rising in (
        (0, "Sunrise", weather.sunrise.strftime("%H:%M"), True),
        (half_w, "Sunset", weather.sunset.strftime("%H:%M"), False),
    ):
        cx = x0 + col_offset + half_w / 2
        ink_bottom = _draw_sun_icon(draw, cx - icon_size / 2, icon_top, icon_size, rising=rising)

        label_w = text_size(label, font=label_font)[0]
        label_y = ink_bottom + ink_gap
        draw_text(
            image, (round(cx - label_w / 2), round(label_y)), label, fill="black", font=label_font
        )

        value_w = text_size(value, font=time_font)[0]
        value_y = label_y + label_h + value_gap
        draw_text(
            image, (round(cx - value_w / 2), round(value_y)), value, fill="black", font=time_font
        )


def _draw_moon_widget(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    weather: WeatherSnapshot,
    title_font,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        box, radius=_WIDGET_CORNER_RADIUS, outline=color("black"), width=_WIDGET_BORDER_W
    )
    icon_x = x0 + _WIDGET_PAD + _MOON_ICON_OFFSET_X
    icon_y = y0 + (y1 - y0 - _ICON_SIZE) // 2
    _draw_moon_icon(image, draw, icon_x, icon_y, weather.moon_phase)

    # A two-word phase name like "Waxing Crescent" doesn't fit this narrow
    # widget on one line (#178 requirement 2) — wrap it the same way event
    # summaries wrap, then center the wrapped block in the space between the
    # icon's right edge and the widget's right inner edge.
    icon_right = icon_x + _ICON_SIZE
    available_w = max(x1 - _WIDGET_PAD - icon_right, 1)
    lines = wrap_text(weather.moon_phase, available_w, font=title_font) or [weather.moon_phase]
    line_h = line_height(title_font)
    text_y = y0 + (y1 - y0 - line_h * len(lines)) // 2
    for i, line in enumerate(lines):
        line_w = text_size(line, font=title_font)[0]
        line_x = icon_right + (available_w - line_w) // 2
        draw_text(image, (line_x, text_y + i * line_h), line, fill="black", font=title_font)


def _draw_weather_widget(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    reading,
) -> None:
    """H/L at the top, then each same-day forecast period as a stacked row:
    the period label on its own line, then that period's own condition icon
    + temperature on the next (#178 requirement 4 — replaces the single
    ambiguous top icon/temp/condition #167 originally drew). The forecast
    rows are space-around distributed across whatever height is left below
    H/L, rather than packed with a fixed gap, so a light forecast doesn't
    leave the bottom of the widget empty (#191)."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        box, radius=_WIDGET_CORNER_RADIUS, outline=color("black"), width=_WIDGET_BORDER_W
    )
    pad = _WIDGET_PAD
    hl_label_font = vendored_font(bold=True, size=_FONT_HL_LABEL)
    hl_value_font = vendored_font(bold=True, size=_FONT_HL_VALUE)

    hl_top = y0 + pad
    hl_text_y = hl_top + (line_height(hl_value_font) - line_height(hl_label_font)) // 2
    hl_segment_gap = 14
    hl_parts = [("H:", reading.high_f), ("L:", reading.low_f)]
    hl_widths = [
        text_size(prefix, font=hl_label_font)[0] + 3 + text_size(f"{round(temp)}°", font=hl_value_font)[0]
        for prefix, temp in hl_parts
    ]
    hl_total_w = sum(hl_widths) + hl_segment_gap * (len(hl_parts) - 1)
    available_w = x1 - pad - (x0 + pad)
    hx = x0 + pad + max((available_w - hl_total_w) // 2, 0)
    for prefix, temp in hl_parts:
        draw_text(image, (hx, hl_text_y), prefix, fill="black", font=hl_label_font)
        hx += text_size(prefix, font=hl_label_font)[0] + 3
        value = f"{round(temp)}°"
        draw_text(image, (hx, hl_top), value, fill="black", font=hl_value_font)
        hx += text_size(value, font=hl_value_font)[0] + hl_segment_gap

    if not reading.forecast:
        return

    hl_bottom = hl_top + line_height(hl_value_font)
    forecast_label_font = vendored_font(bold=True, size=_FONT_FORECAST_LABEL)
    forecast_temp_font = vendored_font(bold=True, size=_FONT_FORECAST_TEMP)
    label_line_h = line_height(forecast_label_font)
    row_h = label_line_h + 2 + _FORECAST_ICON_SIZE

    # Space-around: the gap after H/L and the gaps between/after the rows all
    # get an equal share of whatever height is left, instead of a fixed gap
    # that leaves the widget's lower portion blank (mirrors the same
    # "distribute the leftover space" fix already applied to the event-card
    # list).
    n = len(reading.forecast)
    available = (y1 - pad) - hl_bottom
    slack = max(available - row_h * n, 0)
    gap = slack / (n + 1)

    forecast_x0 = x0 + pad + _FORECAST_OFFSET_X
    row_y = hl_bottom + gap
    for point in reading.forecast:
        draw_text(image, (forecast_x0, round(row_y)), point.label, fill="black", font=forecast_label_font)
        icon_y = round(row_y) + label_line_h + 2

        # Icon + temp move as their own centered group (independent of the
        # label, which stays put) — each row's temp text width can differ,
        # so this is computed per row rather than shared.
        temp_str = f"{round(point.temp_f)}°"
        icon_temp_w = _FORECAST_ICON_SIZE + pad + text_size(temp_str, font=forecast_temp_font)[0]
        icon_x = x0 + pad + max((available_w - icon_temp_w) // 2, 0)
        _draw_condition_icon(draw, icon_x, icon_y, point.condition, size=_FORECAST_ICON_SIZE)

        temp_x = icon_x + _FORECAST_ICON_SIZE + pad
        temp_y = icon_y + (_FORECAST_ICON_SIZE - line_height(forecast_temp_font)) // 2
        draw_text(image, (temp_x, temp_y), temp_str, fill="black", font=forecast_temp_font)

        row_y += row_h + gap


def _draw_sun_icon(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, *, rising: bool) -> float:
    """A yellow-filled sun dome sitting on the horizon line, with a solid
    triangle arrow straddling the horizon directly (roughly half above, half
    below) indicating rising (points up) or setting (points down) — both
    sunrise and sunset use the same band, differentiated purely by arrow
    direction (#178 requirement 3; the original #167 icon had no visible
    dome — its fill was white-on-white — and split the arrows above/below
    the horizon, which read as asymmetric once rendered against a real
    mock). The triangle straddling the horizon (rather than living entirely
    in the band below it) frees up room to grow both the dome and the
    triangle within the same icon footprint (#197 requirement 1). ``size``
    is caller-supplied (not the module-level ``_ICON_SIZE``) so the dawn/dusk
    widget can size this icon independently (#203), of the moon icon, which
    still uses ``_ICON_SIZE`` directly. The triangle is shrunk relative to
    the dome (tri_half_w: 0.26 -> 0.19) so it reads as an accent rather than
    a same-size second shape (#209).

    Returns ``band_bottom`` — the triangle's lowest ink pixel, the same
    value for both directions (the shared band is symmetric; only apex/base
    swap). Callers must lay out whatever comes next relative to this return
    value, not ``y + size`` — the icon's nominal reserved box is taller than
    what it actually draws, and treating ``y + size`` as the bottom leaves
    dead space (#209)."""
    cx = x + size / 2
    horizon_y = y + size * 0.45
    r = size * 0.36

    draw.pieslice(
        [(cx - r, horizon_y - r), (cx + r, horizon_y + r)],
        180,
        360,
        outline=color("black"),
        fill=color("yellow"),
        width=2,
    )
    draw.line([(x, horizon_y), (x + size, horizon_y)], fill=color("black"), width=2)

    # A fixed, proportionate size, straddling the horizon rather than
    # confined to the band below it (#197 requirement 1; #185 requirement 1
    # established the fixed-proportion part of this; #209 shrunk it
    # relative to the dome). _DAWN_DUSK_ARROW_SCALE/_OFFSET_Y apply here only,
    # so both the sunrise and sunset arrow (this same function, called once
    # per direction) always move together.
    tri_half_w = size * 0.19 * _DAWN_DUSK_ARROW_SCALE  # was 0.26 -- shrunk per #209
    band_center = horizon_y + size * 0.015 + _DAWN_DUSK_ARROW_OFFSET_Y
    band_top = band_center - tri_half_w
    band_bottom = band_center + tri_half_w
    apex_y, base_y = (band_top, band_bottom) if rising else (band_bottom, band_top)
    draw.polygon(
        [(cx, apex_y), (cx - tri_half_w, base_y), (cx + tri_half_w, base_y)], fill=color("black")
    )
    return band_bottom


def _draw_moon_icon(
    image: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, phase_name: str
) -> None:
    """A moon disk shaded for ``phase_name`` — the classic two-ellipse-overlap
    trick: paint the "night" half black, then punch a terminator ellipse
    (black for crescents, white for gibbous) into it, both hard-edged so the
    result stays black/white only, no gray."""
    size = _ICON_SIZE
    box = (x, y, x + size, y + size)
    k = _MOON_LIT_FRACTION.get(phase_name, 0.5)

    if k <= 0.0:
        draw.ellipse(box, outline=color("black"), fill=color("black"), width=2)
        return
    if k >= 1.0:
        draw.ellipse(box, outline=color("black"), fill=color("white"), width=2)
        return

    patch = Image.new("RGB", (size, size), color("white"))
    pdraw = ImageDraw.Draw(patch)
    r = size / 2
    lit_right = phase_name in _MOON_WAXING
    night_box = (r, 0, size, size) if lit_right else (0, 0, r, size)
    pdraw.rectangle(night_box, fill=color("black"))

    term_half_w = abs(k - 0.5) * size
    term_box = (r - term_half_w, 0, r + term_half_w, size)
    pdraw.ellipse(term_box, fill=color("black") if k < 0.5 else color("white"))

    mask = Image.new("1", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=1)
    image.paste(patch, (x, y), mask)
    draw.ellipse(box, outline=color("black"), width=2)


def _draw_condition_icon(
    draw: ImageDraw.ImageDraw, x: int, y: int, condition: str, size: float
) -> None:
    """A flat, hard-edged icon for one of the six values ``_condition_name()``
    (``weather_source/fetch.py``, #177) can return: sunny, partly sunny,
    partly cloudy, cloudy, rain, snow. The sun is filled yellow (matching
    the dawn/dusk dome); rain/snow marks are blue; cloud shapes stay
    black-on-white — every shape is still hard-edged, no gray, no
    anti-aliasing (#178 requirement 4).
    """
    if condition == "sunny":
        _draw_sun_shape(draw, x, y, size, rays=True)
        return
    if condition == "partly sunny":
        # Sun dominant (mostly visible), a smaller cloud at its base.
        _draw_sun_shape(draw, x, y, size * 0.85, rays=True)
        _draw_cloud(draw, x + size * 0.15, y + size * 0.4, size * 0.7)
        return
    if condition == "partly cloudy":
        # Cloud dominant, a smaller sun peeking out from behind it.
        _draw_sun_shape(draw, x, y, size * 0.55, rays=False)
        _draw_cloud(draw, x + size * 0.05, y + size * 0.2, size * 0.85)
        return
    if condition == "cloudy":
        _draw_cloud(draw, x, y, size)
        return
    if condition == "snow":
        _draw_cloud(draw, x, y, size)
        for dx in (0.3, 0.55, 0.8):
            _draw_snowflake(draw, x + size * dx, y + size * 0.85, size * 0.14)
        return
    # "rain", and any value _condition_name() doesn't otherwise map (its own
    # storm -> rain fallback) — a cloud with blue raindrop marks below it.
    _draw_cloud(draw, x, y, size)
    for dx in (0.25, 0.5, 0.75):
        lx = x + size * dx
        draw.line(
            [(lx, y + size * 0.75), (lx - size * 0.1, y + size * 0.95)],
            fill=color("blue"),
            width=2,
        )


def _draw_sun_shape(
    draw: ImageDraw.ImageDraw, x: int, y: int, size: float, *, rays: bool
) -> None:
    """A filled-yellow sun circle — with rays when it's the dominant shape
    in its icon (sunny; the sun half of partly-sunny), without them when
    it's peeking from behind a cloud (partly-cloudy)."""
    cx, cy = x + size / 2, y + size / 2
    r = size * 0.3
    draw.ellipse(
        [(cx - r, cy - r), (cx + r, cy + r)], outline=color("black"), fill=color("yellow"), width=2
    )
    if not rays:
        return
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x0 = cx + math.cos(rad) * (r + 2)
        y0 = cy + math.sin(rad) * (r + 2)
        x1 = cx + math.cos(rad) * (r + size * 0.18)
        y1 = cy + math.sin(rad) * (r + size * 0.18)
        draw.line([(x0, y0), (x1, y1)], fill=color("black"), width=2)


def _draw_cloud(draw: ImageDraw.ImageDraw, x: float, y: float, size: float) -> None:
    """Three overlapping circles (left, center, right — center bigger/higher,
    forming the peak) plus one white seam-cleanup ellipse drawn last, no
    separate flat base (#197 requirement 2 — replaces the previous
    flat-bottomed three-circles-plus-rectangle shape)."""
    circles = (
        (0.30 * size, 0.55 * size, 0.28 * size),
        (0.55 * size, 0.35 * size, 0.32 * size),
        (0.75 * size, 0.55 * size, 0.28 * size),
    )
    for dcx, dcy, r in circles:
        cx, cy = x + dcx, y + dcy
        draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            outline=color("black"),
            fill=color("white"),
            width=2,
        )

    # Erases only the internal seams where the circles cross — stays well
    # above the circles' own bottom edges (~0.67*size-0.83*size) so the true
    # outer silhouette isn't clipped flat.
    draw.ellipse(
        [(x + size * 0.20, y + size * 0.48), (x + size * 0.85, y + size * 0.62)],
        outline=color("white"),
        fill=color("white"),
        width=2,
    )


def _draw_snowflake(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    for angle in (0, 60, 120):
        rad = math.radians(angle)
        dx, dy = math.cos(rad) * r, math.sin(rad) * r
        draw.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=color("blue"), width=1)
