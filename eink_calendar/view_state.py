"""Day/Week/Month view cycle logic.

Pure state — no I/O, no dependencies on other modules. The button-A handler in
``app.py`` calls :func:`cycle` (or :meth:`ViewMode.next`) to advance the display
to the next view; the daily scheduled refresh just re-renders the current one.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["ViewMode", "cycle"]


class ViewMode(str, Enum):
    """The three views the display can show, in cycle order.

    Values are the lowercase strings used in ``config.yaml``'s ``view.default``,
    so a ``ViewMode`` compares equal to its config string.
    """

    DAY = "day"
    WEEK = "week"
    MONTH = "month"

    @classmethod
    def from_name(cls, name: str) -> ViewMode:
        """Parse a config string (e.g. ``"day"``) into a :class:`ViewMode`."""
        try:
            return cls(name.strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"unknown view {name!r}; expected one of: {valid}"
            ) from None

    def next(self) -> ViewMode:
        """Return the next view in the cycle, wrapping Month → Day."""
        order = list(ViewMode)
        return order[(order.index(self) + 1) % len(order)]


def cycle(mode: ViewMode) -> ViewMode:
    """Advance one step through Day → Week → Month → Day."""
    return mode.next()
