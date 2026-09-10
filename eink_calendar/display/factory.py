"""Select a display driver from config without importing hardware modules.

``inky_driver`` (Pi-only ``inky`` import) and ``mock_driver`` are both imported
lazily inside :func:`create_display`, so ``import eink_calendar`` never pulls in
GPIO libraries.
"""

from __future__ import annotations

import os

from eink_calendar.display.base import DisplayDriver

__all__ = ["VALID_DRIVERS", "create_display"]

VALID_DRIVERS = ("inky", "mock")


def create_display(
    driver: str,
    *,
    archive_path: str | os.PathLike[str],
    data_dir: str | os.PathLike[str] | None = None,
    auto_open: bool = False,
) -> DisplayDriver:
    """Build the configured :class:`DisplayDriver`.

    ``archive_path`` is where both drivers persist the last composited frame
    (``data/last_render.png`` by default). ``data_dir`` is the only directory
    that archive is allowed to land in (default: ``archive_path``'s parent).
    ``auto_open`` only affects the mock driver (open the PNG in the default
    viewer after each refresh).
    """
    if driver == "inky":
        from eink_calendar.display.inky_driver import InkyDisplay

        return InkyDisplay(archive_path=archive_path, data_dir=data_dir)

    if driver == "mock":
        from eink_calendar.display.mock_driver import (  # type: ignore[import-not-found]
            MockDisplay,
        )

        return MockDisplay(
            archive_path=archive_path, data_dir=data_dir, auto_open=auto_open
        )

    raise ValueError(
        f"unknown display driver {driver!r}; expected one of {VALID_DRIVERS}"
    )
