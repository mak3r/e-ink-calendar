"""Real Pimoroni Inky Impression 7.3" (Spectra 6) driver.

This module imports ``inky``, which only installs on the Raspberry Pi. It is
imported lazily by :func:`eink_calendar.display.factory.create_display` and only
when ``config.display.driver == "inky"`` — never at package import time — so the
rest of ``eink_calendar`` stays importable on a Mac with no GPIO libraries.

Real-hardware behavior (``inky.auto()`` detection, the actual multi-second panel
refresh) is validated on the Pi during bring-up, not in CI — see
``docs/runbook.md``.
"""

from __future__ import annotations

import os

from PIL import Image

from eink_calendar.display.base import DisplayDriver, archive_image

__all__ = ["InkyDisplay"]


class InkyDisplay(DisplayDriver):
    def __init__(
        self,
        archive_path: str | os.PathLike[str],
        *,
        data_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        # Imported here, not at module top, so importing this module still fails
        # loudly on a non-Pi box only if someone actually selects the inky driver.
        from inky.auto import auto

        self._panel = auto()
        self._archive_path = archive_path
        self._data_dir = data_dir
        self._staged: Image.Image | None = None

    def set_image(self, image: Image.Image) -> None:
        self._staged = image.convert("RGB")

    def show(self) -> None:
        if self._staged is None:
            return
        archive_image(self._staged, self._archive_path, data_dir=self._data_dir)
        self._panel.set_image(self._staged)
        self._panel.show()
