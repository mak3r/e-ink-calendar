"""Mock display driver for Mac development — no Inky panel, no GPIO.

Selected by :func:`eink_calendar.display.factory.create_display` when
``config.display.driver == "mock"``. It stages and "shows" frames exactly like
:class:`~eink_calendar.display.inky_driver.InkyDisplay`, but "showing" here just
means archiving the composited PNG to ``archive_path`` (``data/last_render.png``
by default) and, when ``auto_open`` is set, opening that file in the OS default
image viewer. This is what lets ``scripts/render_once.py`` and
``python -m eink_calendar.app`` run end to end on a Mac with no hardware.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from eink_calendar.display.base import DisplayDriver, archive_image

__all__ = ["MockDisplay"]


class MockDisplay(DisplayDriver):
    """Archive-to-PNG stand-in for the real panel."""

    def __init__(
        self,
        archive_path: str | os.PathLike[str],
        *,
        data_dir: str | os.PathLike[str] | None = None,
        auto_open: bool = False,
    ) -> None:
        self._archive_path = archive_path
        self._data_dir = data_dir
        self._auto_open = auto_open
        self._staged: Image.Image | None = None

    def set_image(self, image: Image.Image) -> None:
        self._staged = image.convert("RGB")

    def show(self) -> None:
        if self._staged is None:
            return
        archive_image(self._staged, self._archive_path, data_dir=self._data_dir)
        if self._auto_open:
            _open_in_viewer(Path(self._archive_path).expanduser())


def _viewer_command() -> list[str] | None:
    """The OS default-opener argv, or ``None`` if this platform has no known one."""
    if sys.platform == "darwin":
        found = shutil.which("open")
        return [found] if found else None
    if sys.platform.startswith("linux"):
        found = shutil.which("xdg-open")
        return [found] if found else None
    return None


def _open_in_viewer(path: Path) -> None:
    """Best-effort: open ``path`` in the OS default image viewer.

    Never raises — a headless dev box still gets the archived PNG, the preview
    window is just a convenience.
    """
    opener = _viewer_command()
    if opener is None:
        return
    try:
        # opener is a fixed system tool; path is a local file we just wrote.
        subprocess.Popen(
            [*opener, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
