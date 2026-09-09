"""Write local personal-data / credential files with private permissions.

The calendar cache holds event titles, times and descriptions (personal data);
``token.json`` holds a live OAuth refresh token (a credential). Both live under
``~/.config/eink-calendar/`` owned by a dedicated ``eink`` service user, and
neither may be readable by other users on the box — ``0600`` files inside
``0700`` directories — regardless of the process umask. See ``SECURITY.md``
§1 and §5; the systemd unit's ``UMask=0077`` is the compensating control.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["DIR_MODE", "FILE_MODE", "ensure_private_dir", "write_private_text"]

DIR_MODE = 0o700
FILE_MODE = 0o600


def ensure_private_dir(path: str | os.PathLike[str]) -> Path:
    """Create ``path`` (and parents) if needed and tighten it to ``0700``."""
    directory = Path(path).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(DIR_MODE)
    except OSError:
        # Best effort — e.g. a pre-existing dir we don't own. The file mode
        # below is the load-bearing control.
        pass
    return directory


def write_private_text(path: str | os.PathLike[str], text: str) -> Path:
    """Atomically write ``text`` to ``path`` as a ``0600`` file.

    The temp file is opened with ``O_CREAT`` at mode ``0600`` so it is never
    briefly world-readable, ``chmod``-ed again (in case an existing temp file or
    the umask loosened it), then ``os.replace``-d into place.
    """
    target = Path(path).expanduser()
    ensure_private_dir(target.parent)

    tmp = target.with_suffix(target.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target
