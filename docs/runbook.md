# Runbook

Operational guide for the e-ink calendar: a Raspberry Pi driving a Pimoroni
Inky Impression (Spectra-6) panel that shows a Google Calendar in Day / Week /
Month views.

This guide is generic and public — it assumes no prior context on the project.
Replace `<owner>/<repo>` and the example paths with your own values.

> **Status:** Cross-checked against `SECURITY.md` (#4) and
> `scripts/setup_oauth.py` (#14), both merged. The systemd unit and `deploy.sh` /
> `pull_preview.sh` details (§9–§10) still track issue #15 — confirm the exact
> unit-file contents and deploy flow against that once merged.

---

## 1. What you need

- Raspberry Pi (any model with the 40-pin header; a Pi Zero 2 W or Pi 3/4/5 is fine)
- Pimoroni Inky Impression e-ink panel, seated on the GPIO header
- microSD card, 8 GB or larger
- A Google account whose calendar you want to display
- A second computer (Mac/Linux/Windows) with a browser, used **once** for OAuth consent

---

## 2. Flash Raspberry Pi OS

1. Install **Raspberry Pi OS (Bookworm)**, 64-bit, with Raspberry Pi Imager.
2. In the Imager's advanced options set the hostname, enable SSH, and configure Wi‑Fi / locale.
3. Boot the Pi and SSH in.

## 3. Enable SPI

The Inky panel talks over SPI.

```bash
sudo raspi-config nonint do_spi 0   # 0 = enable
sudo reboot
```

After reboot, confirm `/dev/spidev0.0` exists.

## 4. Create a dedicated service user

The calendar runs as its own non-sudo system user — never as `pi` or root
(`SECURITY.md` §5). This guide uses the user name `eink-calendar`.

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin eink-calendar
sudo usermod -aG spi,gpio eink-calendar
```

That user owns its own `~/.config/eink-calendar/` directory; secrets there are
mode `0600` and `config.yaml` is `0640` (§6).

## 5. Install the application

Always deploy a **tagged release**, never `main` HEAD.

```bash
# pick the latest tag from https://github.com/<owner>/<repo>/releases
VERSION=v1.0.0
sudo -u eink-calendar -H bash -c "
  cd ~ &&
  curl -fsSL https://github.com/<owner>/<repo>/archive/refs/tags/${VERSION}.tar.gz | tar xz &&
  ln -sfn <repo>-${VERSION#v} app
"
```

Install the Pi runtime dependencies (the Pi-only set — GPIO + Inky libraries):

```bash
sudo -u eink-calendar -H bash -c "
  cd ~/app &&
  python3 -m venv .venv &&
  .venv/bin/pip install -r requirements-pi.txt
"
```

## 6. Configure

Configuration and all secrets live **outside the repo checkout** — never in the
working tree, not even git-ignored (`SECURITY.md` §1). The app resolves them
from `$XDG_CONFIG_HOME/eink-calendar/`, falling back to
`~/.config/eink-calendar/` (i.e. the service user's own config dir).

```bash
sudo -u eink-calendar -H bash -c "
  mkdir -p ~/.config/eink-calendar &&
  cp ~/app/config/config.example.yaml ~/.config/eink-calendar/config.yaml &&
  chmod 0640 ~/.config/eink-calendar/config.yaml
"
sudo -u eink-calendar -H nano ~eink-calendar/.config/eink-calendar/config.yaml
```

File modes in this directory (`SECURITY.md` §5):

| File | Mode |
|---|---|
| `config.yaml` | `0640` |
| `*_credentials.json` (OAuth client secret) | `0600` |
| `*_token.json` (cached refresh/access token) | `0600` |

`SECURITY.md` shows a single-account layout (`client_secret.json` / `token.json`);
this project's config is multi-account from day one, so each `accounts[]` entry
names its own `credentials_file` / `token_file` (e.g. `personal_credentials.json`,
`personal_token.json`).

Set at least:

- `display.driver: inky`
- `display.resolution` — confirm against `inky.auto().resolution` during bring-up (section 11)
- `refresh.daily_time` and `refresh.timezone` — when the daily auto-refresh runs
- `accounts[].calendars[].color` — one of the six palette keys
  (`black`, `white`, `red`, `yellow`, `blue`, `green`), never a raw hex value
- `accounts[].credentials_file` / `token_file` — paths under `~/.config/eink-calendar/`

## 7. Google Cloud project + OAuth client

1. In the [Google Cloud console](https://console.cloud.google.com/) create a project.
2. Enable the **Google Calendar API**.
3. Configure the **OAuth consent screen**:
   - User type: External
   - **Publishing status: In production.** Do **not** leave it in *Testing* —
     testing-mode refresh tokens expire after 7 days and the display will
     silently stop updating.
   - Scope: `https://www.googleapis.com/auth/calendar.readonly` only. This
     read-only scope is permanent for this project; do not widen it.
4. Create an **OAuth client ID** of type *Desktop app*. Download the JSON.
5. Copy it to the Pi as the account's `credentials_file`:

```bash
sudo -u eink-calendar -H cp ~/personal_credentials.json ~eink-calendar/.config/eink-calendar/personal_credentials.json
sudo -u eink-calendar -H chmod 600 ~eink-calendar/.config/eink-calendar/*credentials*.json
```

### Choosing the authorizing account

- Enable **2‑Step Verification (2FA)** on the Google account before authorizing.
- If the account is enrolled in Google's **Advanced Protection Program**, OAuth
  to a self-published app may be blocked — use a different account or unenroll.

## 8. Run the one-time OAuth consent

This is the **only** step that needs a browser, and it is run once per account.
`scripts/setup_oauth.py` is the only place `InstalledAppFlow.run_local_server()`
is ever called — the Pi runtime never opens a browser; it only silently refreshes
an existing token.

Easiest path: run it on your Mac/laptop (which has a browser), then copy the
resulting token file to the Pi. The machine you run it on needs both the
account's `config.yaml` entry **and** its `credentials_file` (OAuth client
secret) present at the configured paths — the script reads `credentials_file` /
`token_file` straight from the config.

```bash
# on a machine with a browser, in a checkout of the same release:
pip install -r requirements-dev.txt

# either invocation works:
python -m scripts.setup_oauth --account personal
python scripts/setup_oauth.py --account personal --config ~/my-config.yaml   # --config optional
```

The script prints the **"Production" (not "Testing")** and **2FA** reminders,
then waits for you to press **Enter** before opening the browser (Ctrl-C
aborts). On success it writes the token to the account's `token_file`, created
`0600` in a `0700` directory. Repeat `--account <name>` for each configured
account.

Copy the generated token to the Pi:

```bash
scp ~/.config/eink-calendar/personal_token.json eink-host:/tmp/
ssh eink-host 'sudo -u eink-calendar -H cp /tmp/personal_token.json ~eink-calendar/.config/eink-calendar/ && sudo -u eink-calendar -H chmod 600 ~eink-calendar/.config/eink-calendar/personal_token.json && rm /tmp/personal_token.json'
```

After this, the Pi refreshes the access token silently forever using the stored
refresh token — no further human interaction.

## 9. Install the systemd service

```bash
sudo cp ~eink-calendar/app/systemd/eink-calendar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eink-calendar.service
```

The unit runs as the `eink-calendar` user, `Restart=on-failure`,
`After=network-online.target`, so it comes back on its own after a reboot or a
transient crash. Per `SECURITY.md` §5 it also applies standard hardening —
`NoNewPrivileges=true`, `ProtectSystem=strict`, `PrivateTmp=true`, and
`ProtectHome=` scoped so the service can still read
`~eink-calendar/.config/eink-calendar/`. Final unit content is owned by
`gitops-manager` (issue #15).

Check it:

```bash
systemctl status eink-calendar.service
journalctl -u eink-calendar.service -f
```

Within a few seconds the panel should show the default view.

## 10. Deploying updates

Use `scripts/deploy.sh` (git-based): it pushes the new release, pulls it on the
Pi, reinstalls `requirements-pi.txt`, and restarts the service over SSH.
Secrets under `~eink-calendar/.config/eink-calendar/` are **never** touched by git — they
are synced separately, by an explicit rsync step, only when they actually
change.

To preview the current screen from your desk without anything extra running on
the Pi (only `sshd`):

```bash
scripts/pull_preview.sh <pi-host>
```

This copies the Pi's `data/last_render.png` locally and opens it.

---

## 11. First-boot hardware bring-up checklist

Run once on real hardware and record the results here:

| Check | How | Result |
|---|---|---|
| Panel detected | `python3 -c "from inky.auto import auto; print(auto().resolution)"` | _fill in_ |
| `display.resolution` in config matches the line above | edit `config.yaml` | _fill in_ |
| Panel actually refreshes with the composited image | watch after `systemctl start` | _fill in_ |
| Button pin map matches [Pimoroni's current pinout](https://learn.pimoroni.com/) | compare to `buttons.pin_map` | _fill in_ |
| Button A cycles Day → Week → Month | press it | _fill in_ |
| Button B forces a refresh | press it, watch the journal | _fill in_ |
| Buttons C and D do nothing (no crash, no log) | press them | _fill in_ |
| Daily auto-refresh fires at `daily_time` | set a near-future time, wait | _fill in_ |
| Service restarts after `sudo reboot` with no prompt | reboot | _fill in_ |

---

## 12. Troubleshooting

**Panel never updates / blank panel**
`journalctl -u eink-calendar.service -e`. If SPI is disabled you'll see a device
error — re-run section 3. A blank panel with a healthy log usually means the
cache is empty and the first fetch failed; see the auth items below.

**Display froze on an old image**
By design: a failed fetch keeps the last good render rather than blanking. Check
the journal for repeated fetch failures. The image on screen is always the last
success; `data/last_render.png` is that same image.

**"invalid_grant" / token errors in the log**
The refresh token was revoked or expired. Most common cause: the OAuth consent
screen is still in *Testing* (7-day expiry) — set it to *In production*
(section 7) and re-run section 8. Otherwise the token was revoked manually
(section 13) — re-run section 8 to reissue.

**Wrong colours on events**
Every `color` in `config.yaml` must be one of the six palette keys. The app
rejects a raw hex value at startup with a message naming the field — check the
journal for a config validation error.

**View cycling seems to hit the network**
It shouldn't — button A renders from cache only. If refreshes correlate with
button A presses, file a bug against `persona/developer`.

---

## 13. Revoke and rotate credentials

### When to revoke

- The Pi, its SD card, or a backup containing `~eink-calendar/.config/eink-calendar/` is lost, sold, or disposed of
- You suspect the token or credentials JSON leaked (committed to a repo, pasted somewhere, emailed)
- You are decommissioning the display
- Routine hygiene: rotate at least once a year

### How to revoke

1. Sign in to the Google account the display uses.
2. Open <https://myaccount.google.com/permissions> (**Google Account → Security →
   Third-party apps & services** / "Your connections").
3. Select this app (the name is whatever you set on the OAuth consent screen).
4. Choose **Remove access** / **Delete all connections**.
5. On the Pi, delete the cached token(s):
   ```bash
   sudo -u eink-calendar -H rm ~eink-calendar/.config/eink-calendar/*_token.json
   ```

This immediately invalidates every issued refresh token. The display will keep
showing its last render and log `invalid_grant` on the next refresh.

### How to reissue after revoking

1. Re-run the one-time consent for each account (section 8) and copy the new
   token files back to the Pi (the dead `*_token.json` were already removed in
   "How to revoke" step 5).
2. Restart the service:
   ```bash
   sudo systemctl restart eink-calendar.service
   ```

### Rotating the OAuth client secret (credentials JSON)

1. In the Google Cloud console, under **APIs & Services → Credentials**, delete
   the old OAuth client ID and create a new Desktop-app client.
2. Replace every `credentials_file` on the Pi with the new JSON (`chmod 600`).
3. Re-run section 8 (a new client requires fresh consent).

### What never needs rotating

The `calendar.readonly` scope is fixed for this project (`SECURITY.md` §2). It
MUST NOT be silently widened: any change to the requested scope set requires a
`type/security` issue, explicit human approval, and a `SECURITY.md` update
before merging — it is not a config tweak. A widened scope also forces a fresh
consent flow for every account.
