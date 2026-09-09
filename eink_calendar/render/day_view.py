"""Day view: a single day's events as a time-ordered list."""

from __future__ import annotations

from datetime import date

from PIL import Image, ImageDraw

from eink_calendar.calendar_source.models import Event
from eink_calendar.render.layout_common import MARGIN, draw_text, text_size, wrap_text
from eink_calendar.render.palette import ACCENT_COLORS, color

__all__ = ["render"]

_SWATCH = 12
_ROW_GAP = 8


def _on_day(event: Event, day: date) -> bool:
    return event.start.date() <= day <= event.end.date()


def _swatch_color(event: Event) -> str:
    return event.color if event.color in ACCENT_COLORS else "black"


def render(
    events: list[Event],
    when: date,
    resolution: tuple[int, int],
) -> Image.Image:
    width, height = resolution
    image = Image.new("RGB", resolution, color("white"))
    draw = ImageDraw.Draw(image)

    draw_text(image, (MARGIN, MARGIN), when.strftime("%A"), fill="black", scale=3)
    draw_text(
        image,
        (MARGIN, MARGIN + text_size("A", scale=3)[1] + 4),
        when.strftime("%d %B %Y"),
        fill="black",
        scale=1,
    )
    header_bottom = MARGIN + text_size("A", scale=3)[1] + text_size("A")[1] + 16
    draw.line([(MARGIN, header_bottom), (width - MARGIN, header_bottom)], fill=color("black"))

    todays = sorted(
        (e for e in events if _on_day(e, when)),
        key=lambda e: (not e.all_day, e.start),
    )

    y = header_bottom + _ROW_GAP
    line_h = text_size("Ag")[1]
    text_x = MARGIN + _SWATCH + 8
    for event in todays:
        if y > height - MARGIN - line_h:
            break
        draw.rectangle(
            [(MARGIN, y), (MARGIN + _SWATCH, y + _SWATCH)],
            fill=color(_swatch_color(event)),
            outline=color("black"),
        )
        when_label = "all day" if event.all_day else event.start.strftime("%H:%M")
        draw_text(image, (text_x, y), when_label, fill="black")

        summary_x = text_x + text_size("00:00 ")[0]
        wrapped = wrap_text(event.summary, width - MARGIN - summary_x) or [""]
        for i, seg in enumerate(wrapped):
            if y > height - MARGIN - line_h:
                break
            draw_text(image, (summary_x, y + i * line_h), seg, fill="black")
        y += max(_SWATCH, line_h * len(wrapped)) + _ROW_GAP

    if not todays:
        draw_text(image, (MARGIN, y), "No events", fill="black")

    return image
