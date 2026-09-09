# Security — Secret & Credential Handling Conventions

**Read this before touching any authentication, OAuth, or config-loading code.**

This document formalizes the Security Considerations agreed in the approved
architecture plan. It is the source material `qa` pulls from when writing the
revoke/rotate procedure in `docs/runbook.md`.

---

## 1. Secrets live outside the repo checkout — always

Tokens, OAuth client secrets, and `config.yaml` are **never** stored in the
repository working tree, not even git-ignored. They live in a dedicated
per-user config directory:

```
~/.config/eink-calendar/
├── config.yaml            # runtime configuration
├── client_secret.json     # Google OAuth client secret (downloaded from Cloud Console)
└── token.json             # cached OAuth refresh/access token (created on first auth)
```

- Code MUST resolve these paths from `$XDG_CONFIG_HOME/eink-calendar/`
  (falling back to `~/.config/eink-calendar/`), never from a path inside the
  checkout or the current working directory.
- No `config.yaml`, `client_secret*.json`, `token.json`, or `credentials.json`
  may ever be added to the repo. `.gitignore` carries defense-in-depth patterns
  for these names (see `.gitignore` "Project-specific patterns"), but the
  primary rule is that they simply do not exist inside the checkout.
- Test fixtures use clearly fake placeholder values only (see `.gitleaks.toml`
  allowlist) and live under `test/`.

## 2. OAuth scope is `calendar.readonly` and is frozen

- The application requests exactly one scope:
  `https://www.googleapis.com/auth/calendar.readonly`.
- This scope MUST NOT be silently widened. Any change to the requested scope
  set is a security-reviewed change: open a `type/security` issue, get explicit
  human approval, and update this document before merging.
- A widened scope also forces every user through the Google consent screen
  again — treat scope as a stable public contract.

## 3. Authorizing Google account requirements

The Google account used to authorize the app (the account whose calendar is
read) MUST satisfy all of the following:

- **2-Factor Authentication is enabled.** No exceptions.
- **Not enrolled in the Advanced Protection Program (APP).** APP blocks most
  third-party OAuth access and will break token refresh. Check this *before*
  choosing which account to authorize; if the intended account is in APP,
  choose a different account or a dedicated one.
- Prefer a **dedicated account** (or at least one where calendar read exposure
  is acceptable) rather than a primary personal account.

## 4. OAuth consent screen: publishing status must be "In production"

- In Google Cloud Console, the OAuth consent screen MUST be set to publishing
  status **"In production"**.
- If it is left in **"Testing"**, Google expires refresh tokens after **7 days**,
  which silently breaks the calendar sync one week after every re-auth.
- "In production" for an unverified app used only by its owner is expected and
  acceptable here; the unverified-app warning on the consent screen is normal.

## 5. Systemd service runs as a dedicated non-privileged user

- The deployment systemd unit MUST run the service as a **dedicated,
  non-sudo system user** (e.g. `eink-calendar`), not `root` and not a human
  login user.
- That user owns `~/.config/eink-calendar/` (i.e. the service user's own home /
  config dir), and those files are mode `0600` (token/secret) or `0640`
  (config).
- The unit MUST set `UMask=0077` so that any file the service writes outside
  `local_files.write_private_text()` — notably `data/last_render.png`, which is
  a picture of the family's calendar — is not world-readable.
- The unit applies systemd sandboxing: `NoNewPrivileges=true`,
  `ProtectSystem=strict`, `ProtectHome=read-only` with `ReadWritePaths=` scoped
  to the checkout's `data/` and the service user's config dir, `PrivateTmp=true`,
  `ProtectKernelTunables=true`, `ProtectKernelModules=true`,
  `ProtectControlGroups=true`, `RestrictRealtime=true`, `RestrictSUIDSGID=true`,
  `LockPersonality=true`.
- Device access (SPI/GPIO) is left at the default policy until hardware
  bring-up; tightening to `DevicePolicy=closed` + explicit `DeviceAllow=` for
  the Inky panel's `/dev` nodes is tracked for the bring-up phase and must be
  verified against real hardware.
- Final unit content is owned by `gitops-manager`; this section states the
  security requirements it must meet, and is kept in sync with
  `systemd/eink-calendar.service` as that file changes.

---

## Revoke / rotate (summary — full procedure lives in `docs/runbook.md`)

- **Revoke:** remove the app's access at
  <https://myaccount.google.com/permissions> for the authorizing account, then
  delete `~/.config/eink-calendar/token.json`.
- **Rotate client secret:** create a new client secret in Google Cloud Console,
  replace `~/.config/eink-calendar/client_secret.json`, delete
  `token.json`, restart the service, and complete the auth flow again.
- **Rotate token only:** delete `~/.config/eink-calendar/token.json` and
  re-run the auth flow; the client secret is unchanged.

---

## Reporting a vulnerability

This is a single-owner hobby deployment. Report security concerns by opening a
GitHub issue labeled `type/security` + `persona/security`.
