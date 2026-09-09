#!/usr/bin/env python3
"""One-time OAuth consent helper — run once per account, by a human with a browser.

This is the ONLY place ``InstalledAppFlow.run_local_server()`` is ever called.
It reads the named account's ``credentials_file`` / ``token_file`` from the
config and writes a fresh token JSON *outside* the repo checkout. The Pi/Mac
runtime (``eink_calendar.app``) never runs this — it only ever silently
refreshes an existing token via ``calendar_source.auth.load_credentials``.

Usage:
    python -m scripts.setup_oauth --account personal
    python scripts/setup_oauth.py --account personal --config ~/my-config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this file directly (`python scripts/setup_oauth.py`) as well as
# `python -m scripts.setup_oauth` — the human installer will reach for either.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow

from eink_calendar.calendar_source.auth import READONLY_SCOPES
from eink_calendar.calendar_source.local_files import write_private_text
from eink_calendar.config import ConfigError, load_config

_REMINDER = """\
────────────────────────────────────────────────────────────────────────
Before you authorize, confirm ALL THREE of these —
this script cannot check them for you, and getting them wrong means the
display silently stops updating weeks later:

  1. OAuth consent screen is set to "Production" (NOT "Testing") in the
     Google Cloud console. Testing-mode refresh tokens expire after 7
     days; the family would have to re-authorize constantly.

  2. Two-factor authentication is enabled on the Google account you are
     about to sign in with. This token is long-lived and lives on a
     device in a shared household.

  3. The account is NOT enrolled in Google's Advanced Protection Program
     (check at https://myaccount.google.com/advanced-protection/). APP
     silently blocks most third-party OAuth and breaks token refresh
     later — use a different or dedicated account if it is enrolled.
────────────────────────────────────────────────────────────────────────
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create/refresh a Google Calendar OAuth token for one account."
    )
    parser.add_argument(
        "--account",
        required=True,
        help="account name as it appears under 'accounts:' in config.yaml",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="path to config.yaml (default: the usual search path)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        parser.error(str(exc))

    account = next((a for a in config.accounts if a.name == args.account), None)
    if account is None:
        configured = ", ".join(a.name for a in config.accounts)
        parser.error(
            f"no account named {args.account!r} in config; configured: {configured}"
        )

    client_secrets = Path(account.credentials_file)
    token_file = Path(account.token_file)
    if not client_secrets.is_file():
        parser.error(
            f"OAuth client secrets file not found at {client_secrets} "
            f"(account {account.name!r})"
        )

    print(_REMINDER)
    try:
        input("Press Enter to open your browser for consent (Ctrl-C to abort)... ")
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets), READONLY_SCOPES
    )
    creds = flow.run_local_server(port=0)

    # token.json holds a live refresh token — write it 0600 in a 0700 dir from
    # the very first creation, so later silent refreshes in auth.py never
    # re-save over a world-readable file. Same helper auth.py uses.
    write_private_text(token_file, creds.to_json())
    print(f"\nWrote token for account {account.name!r} to {token_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
