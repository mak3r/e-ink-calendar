"""Dispatch a view mode + cached events to a finished ``PIL.Image``.

The composite is built in RGB using only :data:`~eink_calendar.render.palette`
colors and a non-anti-aliased font, so it is already palette-pure — the ``inky``
library does the final quantization to the panel with no manual dithering here.
"""

from __future__ import annotations

from datetime import date

from PIL import Image

from eink_calendar.calendar_source.models import Event
from eink_calendar.render import day_view, month_view, week_view

__all__ = ["DEFAULT_RESOLUTION", "render"]

DEFAULT_RESOLUTION = (800, 480)


def render(
    view_mode: str,
    events: list[Event],
    *,
    when: date | None = None,
    resolution: tuple[int, int] = DEFAULT_RESOLUTION,
    week_starts_on: str = "monday",
) -> Image.Image:
    """Render ``events`` for ``view_mode`` (``"day"``/``"week"``/``"month"``).

    ``view_mode`` accepts a plain string or a ``view_state.ViewMode`` (which is a
    ``str`` enum). ``when`` defaults to today.
    """
    # A str-mixed Enum's str() is "ViewMode.DAY" on 3.11, so read .value first.
    mode = str(getattr(view_mode, "value", view_mode)).lower()
    # app.py always passes an explicit tz-aware `when` from the configured
    # timezone; this fallback only matters for ad-hoc/dev calls.
    day = when or date.today()  # noqa: DTZ011
    ordered = sorted(events, key=lambda e: (e.start, e.end, e.id))

    if mode == "day":
        return day_view.render(ordered, day, resolution)
    if mode == "week":
        return week_view.render(ordered, day, resolution, week_starts_on)
    if mode == "month":
        return month_view.render(ordered, day, resolution, week_starts_on)
    raise ValueError(f"unknown view mode {view_mode!r}; expected day, week, or month")
