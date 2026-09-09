"""Per-account OAuth credential loading and silent refresh.

The token JSON lives outside the repo checkout (``~/.config/eink-calendar/``).
This module only ever does google-auth's *silent* refresh flow — it never opens
a browser. The interactive consent flow (``run_local_server``) exists solely in
``scripts/setup_oauth.py``, which a human runs once at install time; the Pi
runtime must never attempt it, or a non-technical family member would be stuck
with a blank display and no way forward.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from eink_calendar.calendar_source.local_files import write_private_text

__all__ = ["READONLY_SCOPES", "CalendarAuthError", "load_credentials"]

READONLY_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class CalendarAuthError(RuntimeError):
    """Raised when credentials are missing or cannot be refreshed silently."""


def load_credentials(
    token_file: str | os.PathLike[str],
    *,
    scopes: list[str] | None = None,
) -> Credentials:
    """Load credentials from ``token_file``, refreshing and re-saving if expired.

    Raises :class:`CalendarAuthError` if the token file is absent or the token
    is unusable and has no refresh token — the fix for both is to re-run
    ``scripts/setup_oauth.py`` on a machine with a browser.
    """
    path = Path(token_file).expanduser()
    if not path.is_file():
        raise CalendarAuthError(
            f"no OAuth token at {path}; run scripts/setup_oauth.py for this account"
        )

    creds = Credentials.from_authorized_user_file(str(path), scopes or READONLY_SCOPES)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # token.json holds a live refresh token — write it 0600, never with the
        # default umask. See eink_calendar.calendar_source.local_files.
        write_private_text(path, creds.to_json())
        return creds

    raise CalendarAuthError(
        f"OAuth token at {path} is invalid and has no refresh token; "
        "re-run scripts/setup_oauth.py for this account"
    )
