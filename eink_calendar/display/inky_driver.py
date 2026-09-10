"""Real Pimoroni Inky Impression 7.3" (Spectra 6) driver.

This module imports ``inky``, which only installs on the Raspberry Pi. It is
imported lazily by :func:`eink_calendar.display.factory.create_display` and only
when ``config.display.driver == "inky"`` — never at package import time — so the
rest of ``eink_calendar`` stays importable on a Mac with no GPIO libraries.

Real-hardware behavior (``inky.auto()`` detection, the actual multi-second panel
refresh) is validated on the Pi during bring-up, not in CI — see
``docs/runbook.md``. The ``log`` lines here are deliberately chatty: they are
the only window bring-up has into whether ``set_image`` / ``show`` actually
reach the panel with a sane frame (issue #100).
"""

from __future__ import annotations

import logging
import os
import time

from PIL import Image

from eink_calendar.display.base import DisplayDriver, archive_image

__all__ = ["InkyDisplay"]

log = logging.getLogger("eink_calendar")

# A real Spectra-6 refresh takes tens of seconds. If ``panel.show()`` returns
# much faster than this, the SPI/BUSY handshake almost certainly did not run
# (SPI disabled, BUSY pin miswired) even though nothing raised — flag it.
_MIN_PLAUSIBLE_REFRESH_S = 2.0


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

        log.info(
            "inky panel: %s resolution=%s colour=%s rotation=%s",
            type(self._panel).__name__,
            getattr(self._panel, "resolution", "?"),
            getattr(self._panel, "colour", "?"),
            getattr(self._panel, "rotation", "?"),
        )

    def set_image(self, image: Image.Image) -> None:
        self._staged = image.convert("RGB")

    def show(self) -> None:
        if self._staged is None:
            log.warning("inky show() called with no staged frame — skipping")
            return

        archive_image(self._staged, self._archive_path, data_dir=self._data_dir)

        frame = self._to_panel_frame(self._staged)
        log.info("pushing %s %s frame to the inky panel", frame.size, frame.mode)
        started = time.monotonic()
        try:
            self._panel.set_image(frame)
            self._panel.show()
        except Exception:
            # A dead panel must be loud during bring-up, not silently stuck on
            # the previous frame — re-raise after logging (systemd restarts).
            log.exception("inky panel push failed")
            raise
        elapsed = time.monotonic() - started

        if elapsed < _MIN_PLAUSIBLE_REFRESH_S:
            log.warning(
                "inky show() returned in %.2fs — a Spectra-6 refresh takes far "
                "longer; check that SPI is enabled and the panel is wired",
                elapsed,
            )
        else:
            log.info("inky panel refreshed in %.0fs", elapsed)

    def _to_panel_frame(self, image: Image.Image) -> Image.Image:
        """Map the palette-pure render onto the panel's native six colours.

        ``inky``'s ``set_image`` dithers an RGB image against a *blended*
        palette; handing it a mode-``P`` image whose palette is exactly the
        driver's ``DESATURATED_PALETTE`` takes its no-dither direct-map path
        instead, so the six flat colours land as-is. Falls back to the RGB
        image for any driver class that doesn't expose that palette.
        """
        desaturated = getattr(self._panel, "DESATURATED_PALETTE", None)
        if not desaturated:
            return image
        flat = [channel for entry in desaturated for channel in entry]
        flat = (flat + [0] * 768)[:768]
        palette_image = Image.new("P", (1, 1))
        palette_image.putpalette(flat)
        return image.convert("RGB").quantize(
            colors=len(desaturated),
            palette=palette_image,
            dither=Image.Dither.NONE,
        )
