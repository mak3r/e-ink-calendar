"""The six-color Spectra 6 palette — the single source of truth for color.

The Inky Impression 7.3" panel can only display these six colors. Every color
used anywhere in ``render/`` must come from :data:`PALETTE` (keyed by name);
arbitrary hex/RGB literals are forbidden because the panel cannot show them and
the ``inky`` library would quantize them to something unpredictable.

Convention: body text and gridlines are ``black`` on a ``white`` ground. The
four accent colors (``red``, ``green``, ``blue``, ``yellow``) are reserved for
per-calendar event color-coding blocks only.
"""

from __future__ import annotations

__all__ = ["ACCENT_COLORS", "PALETTE", "color"]

PALETTE: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (220, 40, 40),
    "green": (40, 150, 70),
    "blue": (40, 80, 190),
    "yellow": (240, 200, 40),
}

# The colors config.py allows for a calendar's `color:` field.
ACCENT_COLORS: frozenset[str] = frozenset({"red", "green", "blue", "yellow"})


def color(name: str) -> tuple[int, int, int]:
    """Return the RGB tuple for a palette color name, or raise ``KeyError``."""
    try:
        return PALETTE[name]
    except KeyError:
        raise KeyError(
            f"{name!r} is not a palette color; valid: {sorted(PALETTE)}"
        ) from None
