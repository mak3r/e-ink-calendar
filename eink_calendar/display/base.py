"""Display driver interface + the one piece of behavior both drivers share.

``app.py`` and ``render_once.py`` only ever hold a :class:`DisplayDriver` — never
a concrete driver class — so the same code path drives the real Inky panel and
the Mac mock identically. The choice is made once, in ``factory.create_display``.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

__all__ = ["DisplayDriver", "archive_image"]

log = logging.getLogger("eink_calendar")


def archive_image(image: Image.Image, path: str | os.PathLike[str]) -> None:
    """Persist the composited RGB image to ``path`` before the panel push.

    Both the real and mock drivers call this with the same path so there is
    always an on-disk copy of exactly what was last sent to the display,
    regardless of which driver is active.

    A failure here (read-only filesystem, bad path, disk full) is logged
    loudly but **never raised**: a stale preview must not blank the panel or
    kill the gpiozero button thread. The panel push is the source of truth;
    the archive is a convenience for ``pull_preview.sh`` / design review.
    """
    target = Path(path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(target)
    except OSError:
        log.warning("could not archive render to %s", target, exc_info=True)


class DisplayDriver(ABC):
    """Stage an image, then flush it to the display."""

    @abstractmethod
    def set_image(self, image: Image.Image) -> None:
        """Stage ``image`` as the next frame (not yet visible)."""

    @abstractmethod
    def show(self) -> None:
        """Archive the staged frame and make it visible on the display."""
