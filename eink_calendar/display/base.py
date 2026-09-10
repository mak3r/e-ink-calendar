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

__all__ = ["ARCHIVE_MODE", "DisplayDriver", "archive_image"]

log = logging.getLogger("eink_calendar")

# The archived frame is a picture of the family's calendar — personal data
# (SECURITY.md §5). Written 0600 explicitly, regardless of the process umask,
# because the render also runs outside systemd (dev loop, render_once.py, cron).
ARCHIVE_MODE = 0o600


def archive_image(
    image: Image.Image,
    path: str | os.PathLike[str],
    *,
    data_dir: str | os.PathLike[str] | None = None,
) -> None:
    """Persist the composited RGB image to ``path`` before the panel push.

    Both the real and mock drivers call this with the same path so there is
    always an on-disk copy of exactly what was last sent to the display,
    regardless of which driver is active.

    The file is written atomically at mode :data:`ARCHIVE_MODE` (0600),
    mirroring ``local_files.write_private_text()`` — never at the process
    umask. ``data_dir`` (default: the target's own parent) is the only
    directory the archive may land in: a target that is a symlink, or whose
    parent resolves outside ``data_dir``, is refused rather than followed.

    A failure here (read-only filesystem, bad path, disk full, refused path)
    is logged loudly but **never raised**: a stale preview must not blank the
    panel or kill the gpiozero button thread. The panel push is the source of
    truth; the archive is a convenience for ``pull_preview.sh`` / design review.
    """
    target = Path(path).expanduser()
    allowed = Path(data_dir).expanduser() if data_dir is not None else target.parent
    try:
        allowed.mkdir(parents=True, exist_ok=True)
        if not _target_is_inside(target, allowed):
            log.warning(
                "refusing to archive render: %s resolves outside the data dir %s",
                target,
                allowed,
            )
            return
        _write_private_png(image.convert("RGB"), target)
    except OSError:
        log.warning("could not archive render to %s", target, exc_info=True)


def _target_is_inside(target: Path, allowed: Path) -> bool:
    """True if ``target`` sits directly in ``allowed`` and is not a symlink.

    The parent is resolved through symlinks (so a redirected ancestor is
    caught); the final component is compared literally (so a symlinked
    ``last_render.png`` pointing elsewhere is caught).
    """
    if target.is_symlink():
        return False
    return os.path.realpath(target.parent) == os.path.realpath(allowed)


def _write_private_png(image: Image.Image, target: Path) -> None:
    """Atomically write ``image`` to ``target`` as a 0600 PNG."""
    tmp = target.with_suffix(target.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, ARCHIVE_MODE)
    try:
        with os.fdopen(fd, "wb") as handle:
            image.save(handle, format="PNG")
        os.chmod(tmp, ARCHIVE_MODE)  # re-assert: umask can only have loosened it
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class DisplayDriver(ABC):
    """Stage an image, then flush it to the display."""

    @abstractmethod
    def set_image(self, image: Image.Image) -> None:
        """Stage ``image`` as the next frame (not yet visible)."""

    @abstractmethod
    def show(self) -> None:
        """Archive the staged frame and make it visible on the display."""
