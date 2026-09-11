"""Day view: today's events as a column of deduplicated, card-style entries.

Identical events booked on more than one configured calendar are merged into a
single card whose left-edge accent stripe splits into one band per source
calendar color; a color/label legend in the header band maps each color back
to a calendar name. Cards occupy the left three-quarters of the panel — the
right quarter is reserved for a future widget. See
``.claude/plans/day-view-card-redesign.md`` (persona/product-designer branch)
for the approved design this implements.
"""

from __future__ import annotations

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

__all__ = ["render"]

_FONT_DAY_NAME = 42
_FONT_DATE = 17
_FONT_LABEL = 14
_FONT_SUMMARY = 15
_FONT_KEY = 14

# Day name -> date line, date line -> rule (tight), rule -> first card (roomy).
# Tuned so 8 cards + an overflow row (the worst case at the max_entries=9
# default) fit inside the 800x480 panel with room to spare — see the sizing
# check in tests/render/test_day_view.py.
_DATE_TOP_GAP = 2
_RULE_GAP_ABOVE = 2
_RULE_GAP_BELOW = 8

_KEY_GAP = 16  # between calendar-key legend entries

_COLUMN_FRACTION = 0.75  # event column occupies the left 3/4 of the panel
_CARD_GAP = 5
_CARD_PAD = 5
_CORNER_RADIUS = 6
_BORDER_W = 2
_STRIPE_W = 10
_STRIPE_INSET = 2  # keeps the stripe clear of the rounded corners
_SWATCH = 12  # calendar-key legend swatch


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


def _on_day(event: Event, day: date) -> bool:
    return event.start.date() <= day <= event.end.date()


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
) -> Image.Image:
    """Render ``when``'s events as a header + card list.

    ``calendar_labels`` maps a swatch color (as used by :func:`_swatch_color`)
    to a human calendar label, for the header legend — typically built from
    ``AccountConfig.calendars`` (``color -> label``). ``max_entries`` caps the
    number of cards shown before an overflow row summarizes the rest.
    """
    width, height = resolution
    image = Image.new("RGB", resolution, color("white"))
    draw = ImageDraw.Draw(image)

    day_font = vendored_font(bold=True, size=_FONT_DAY_NAME)
    date_font = vendored_font(size=_FONT_DATE)
    label_font = vendored_font(size=_FONT_LABEL)
    summary_font = vendored_font(size=_FONT_SUMMARY)
    key_font = vendored_font(size=_FONT_KEY)

    day_name = when.strftime("%A")
    draw_text(image, (MARGIN, MARGIN), day_name, fill="black", font=day_font)
    day_name_h = text_size(day_name, font=day_font)[1]

    date_y = MARGIN + day_name_h + _DATE_TOP_GAP
    date_line = when.strftime("%d %B %Y")
    draw_text(image, (MARGIN, date_y), date_line, fill="black", font=date_font)
    date_h = text_size(date_line, font=date_font)[1]

    todays = [e for e in events if _on_day(e, when)]
    groups = sorted(_dedupe(todays), key=lambda g: (not g.all_day, g.start))

    _draw_calendar_key(
        image, draw, groups, calendar_labels or {}, width, key_font, MARGIN, day_name_h
    )

    rule_y = date_y + date_h + _RULE_GAP_ABOVE
    draw.line([(MARGIN, rule_y), (width - MARGIN, rule_y)], fill=color("black"))

    column_right = MARGIN + round((width - 2 * MARGIN) * _COLUMN_FRACTION)

    if len(groups) > max_entries:
        visible, overflow = groups[: max_entries - 1], groups[max_entries - 1 :]
    else:
        visible, overflow = groups, []

    y = rule_y + _RULE_GAP_BELOW
    for i, group in enumerate(visible):
        wrapped, card_h, layout = _layout_card(group, label_font, summary_font, column_right)
        if y + card_h > height - MARGIN:
            # Doesn't fit (e.g. an unusually long, multi-line-wrapped summary
            # ate more vertical budget than the max_entries sizing assumed) —
            # fold it and everything after it into the overflow row rather
            # than silently dropping it off the bottom of the panel.
            overflow = visible[i:] + overflow
            break
        _draw_card(
            image, draw, y, column_right, group, wrapped, card_h, layout, label_font, summary_font
        )
        y += card_h + _CARD_GAP

    if overflow:
        _draw_overflow_row(image, draw, y, column_right, overflow, label_font)

    if not groups:
        draw_text(image, (MARGIN, y), "No events", fill="black", font=summary_font)

    return image


def _draw_calendar_key(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    groups: list[_Group],
    calendar_labels: dict[str, str],
    width: int,
    key_font,
    header_top: int,
    header_h: int,
) -> None:
    """Right-aligned legend (swatch + label) for each distinct color among
    today's events, vertically centered on the day-name row."""
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
    x = width - MARGIN - total_w
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
    group: _Group, label_font, summary_font, column_right: int
) -> tuple[list[str], int, _CardLayout]:
    """Compute a card's wrapped summary, total height, and x-positions
    without drawing anything, so callers can check it fits before drawing."""
    label_w = max(
        text_size("ALL DAY", font=label_font)[0],
        text_size("00:00", font=label_font)[0],
    ) + _CARD_PAD

    stripe_x0 = MARGIN + _BORDER_W + _STRIPE_INSET
    stripe_x1 = stripe_x0 + _STRIPE_W
    text_x = stripe_x1 + _CARD_PAD
    summary_x = text_x + label_w
    summary_max_w = max(column_right - _BORDER_W - _CARD_PAD - summary_x, 1)

    summary_line_h = line_height(summary_font)
    wrapped = wrap_text(group.summary, summary_max_w, font=summary_font) or [""]
    inner_h = max(summary_line_h * len(wrapped), line_height(label_font), _STRIPE_W)
    card_h = 2 * _CARD_PAD + inner_h

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
) -> None:
    """Draw one rounded-rectangle event card at ``y`` per a prior :func:`_layout_card`."""
    box = (MARGIN, y, column_right, y + card_h)
    draw.rounded_rectangle(box, radius=_CORNER_RADIUS, outline=color("black"), width=_BORDER_W)
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

    content_top = y + _CARD_PAD
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
) -> None:
    """A segmented color band (one segment per distinct hidden color) plus a
    "+N more" count, glanceable in place of N plain-text rows."""
    colors_seen: list[str] = []
    for g in hidden:
        for c in g.colors:
            if c not in colors_seen:
                colors_seen.append(c)

    band_h = line_height(label_font) + _CARD_PAD
    band_w = min(120, column_right - MARGIN - 2 * _CARD_PAD)
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
    draw_text(image, (x1 + _CARD_PAD, text_y), label, fill="black", font=label_font)
