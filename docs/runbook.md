# Runbook

Operational guide for the e-ink calendar: a Raspberry Pi driving a Pimoroni
Inky Impression (Spectra-6) panel that shows a Google Calendar in Day / Week /
Month views.

This guide is generic and public — it assumes no prior context on the project.
Replace `<owner>/<repo>` and the example paths with your own values.

> **Status:** Cross-checked against the merged infra from the v0.2.0 Pi bring-up
> cluster — `scripts/install.sh` (#81), `scripts/deploy.sh` / `ssh -tt` sudo
> (#82), `liblgpio-dev` (#85), the `data/` + `LG_WD` systemd fixes (#86), SPI/I2C
> (#88) — plus `SECURITY.md` (#4) and `setup_oauth.py` (#14). §11 (hardware
> bring-up) still needs a full pass on real hardware.

---

## 1. What you need

- Raspberry Pi (any model with the 40-pin header; a Pi Zero 2 W or Pi 3/4/5 is fine)
- Pimoroni Inky Impression e-ink panel, seated on the GPIO header
- microSD card, 8 GB or larger
- A Google account whose calendar you want to display
- A second computer (Mac/Linux/Windows) with a browser, used **once** for OAuth consent

---

## 2. Flash Raspberry Pi OS

1. Install **Raspberry Pi OS**, 64-bit, with Raspberry Pi Imager. Supported
   images run **Python 3.11 (Bookworm) through 3.13 (Trixie-era)** — CI gates
   every release on both ends of that range (issue #66). Newer or older
   interpreters are unsupported; `scripts/deploy.sh` refuses them outright.
2. In the Imager's advanced options set the hostname, enable SSH, and configure Wi‑Fi / locale.
3. Boot the Pi and SSH in.

## 3. Enable SPI and I2C

The Inky panel is driven over SPI, and `inky.auto()` reads the panel's model
from an EEPROM **over I2C** — both buses must be on (issue #88).

```bash
sudo raspi-config nonint do_spi 0   # 0 = enable
sudo raspi-config nonint do_i2c 0   # 0 = enable
```

Current `inky` (2.x) manages the SPI chip-select line itself via `gpiod` and
aborts (`Chip Select: (line 8, GPIO8) currently claimed by spi0 CS0`) if the
kernel SPI driver is holding it. Free GPIO7/8 by adding the no-chip-select
overlay:

```bash
# append to /boot/firmware/config.txt, below the existing dtparam=spi=on
echo 'dtoverlay=spi0-0cs' | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

After reboot, confirm **both** `/dev/spidev0.0` and `/dev/i2c-1` exist.

## 4. Create a dedicated service user

The calendar runs as its own non-sudo system user — never as `pi` or root
(`SECURITY.md` §5). This guide uses the user name `eink-calendar`.

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin eink-calendar
sudo usermod -aG spi,gpio,i2c eink-calendar
```

The `i2c` group is what lets the service user read `/dev/i2c-1` for EEPROM
detection (§3, issue #88).

That user owns its own `~/.config/eink-calendar/` directory; secrets there are
mode `0600` and `config.yaml` is `0640` (§6).

## 5. Install the application

Always deploy a **tagged release**, never `main` HEAD. Install the release
tarball and point `~eink-calendar/app` at it — no git checkout on the Pi.
`scripts/deploy.sh code` (§10) automates exactly these steps for later updates.

```bash
# set this to the latest tag from https://github.com/<owner>/<repo>/releases
VERSION=vX.Y.Z
sudo -u eink-calendar -H bash -c "
  cd ~ &&
  curl -fsSL https://github.com/<owner>/<repo>/archive/refs/tags/${VERSION}.tar.gz | tar xz &&
  ln -sfn <repo>-${VERSION#v} app
"
```

`~app` stays a symlink to the extracted `<repo>-<version>` directory; a deploy
just extracts the new release and repoints the symlink, and the systemd unit
resolves it afresh on every restart.

Then run the release's own installer — **the one and only install step**
(`scripts/install.sh`, issue #81). `scripts/deploy.sh code` (§10) runs this exact
script over SSH, so a first install and every later update go through identical
steps:

```bash
cd ~eink-calendar/app && sudo ./scripts/install.sh
```

`install.sh` is idempotent and, as root:

- guards the Python version (3.11–3.13, issue #66)
- `apt-get install`s the lgpio/spidev build toolchain —
  `swig python3-dev build-essential libopenjp2-7 liblgpio-dev`. Neither piwheels
  nor PyPI ships an `lgpio`/`spidev` wheel for Python 3.13, so they build from
  their hash-verified sdists; `swig` + headers get the compile through (#66) and
  `liblgpio-dev` provides the `-llgpio` the extension links against (#85).
- as the service user: `mkdir -p data`, creates a plain venv, and
  `pip install --require-hashes -r requirements.lock` — **hash-verified, never
  the loose `requirements-*.txt`** (`SECURITY.md` §6, issue #68). It falls back
  to `requirements-pi.txt` only for releases cut before the lock existed.

(`requirements-base.txt` / `requirements-pi.txt` are the human-edited inputs;
regenerate the lock with `uv pip compile --universal --generate-hashes
--no-header requirements-pi.txt -o requirements.lock` after editing them.)

## 6. Configure

Configuration and all secrets live **outside the repo checkout** — never in the
working tree, not even git-ignored (`SECURITY.md` §1). With no `--config`
argument, `load_config()` (`eink_calendar/config.py`) looks in this order:

1. `$EINK_CALENDAR_CONFIG` — a full path to the `config.yaml` file (not a
   directory)
2. `~/.config/eink-calendar/config.yaml` — the service user's own config dir
   (this is what the systemd unit relies on)
3. `./config/config.yaml` — relative to the working directory (dev only)

There is no `$XDG_CONFIG_HOME` handling. Running as the `eink-calendar` user,
path 2 resolves to `/home/eink-calendar/.config/eink-calendar/config.yaml`, so
no environment variable is needed on the Pi.

### This device's `config.yaml` is authored on the Pi

The Pi's `config.yaml` is written here, by hand, and is the **single source of
truth for this device**. `deploy.sh` never reads, writes, or deletes it —
`deploy.sh secrets` syncs credential/token files only (§10, §13). The dev Mac
keeps its own separate `config.yaml`. This is deliberate for a
two-environment, single-operator project (`architecture.md` "Per-environment
config", issue #110).

Two classes of key:

| | Keys | Rule |
|---|---|---|
| **Environment-specific** | `display.driver`, `display.resolution`, `display.output_path`, `display.mock_auto_open`, `buttons.pin_map` | Legitimately differ per machine — set them per device and leave them. |
| **Shared** | `accounts`, `refresh`, `view`, `buttons.bindings`, `cache.path` | Must stay identical on both machines or they render different calendars. When one changes (e.g. adding a calendar), **edit both** the dev and the Pi `config.yaml` by hand. `config.example.yaml` marks each key. |

```bash
sudo -u eink-calendar -H bash -c "
  mkdir -p ~/.config/eink-calendar &&
  cp ~/app/config/config.example.yaml ~/.config/eink-calendar/config.yaml &&
  chmod 0640 ~/.config/eink-calendar/config.yaml
"
sudo -u eink-calendar -H nano ~eink-calendar/.config/eink-calendar/config.yaml
```

**`config.example.yaml` ships dev defaults — the panel stays dark until you
change them.** It sets `display.driver: mock` (renders to a PNG, never drives the
Inky) and `display.mock_auto_open: true` (tries to `xdg-open` that PNG, which
fails noisily on a headless Pi). Immediately after the copy, edit at minimum:

- `display.driver: inky`
- `display.mock_auto_open: false`
- `refresh.timezone` — your IANA zone (e.g. `America/New_York`)
- `accounts[].calendars` — your real calendar IDs and palette colours
- `accounts[].credentials_file` / `token_file` — the paths set up in §7–§8

The full field reference is below.

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

- `display.driver: inky` (the example ships `mock`)
- `display.mock_auto_open: false` (the example ships `true`)
- `display.resolution` — confirm against `inky.auto().resolution` during bring-up (section 11)
- `display.output_path` — where the last composited frame is archived (and what
  `pull_preview.sh` fetches, §10). A **relative** value is anchored to the
  process working directory: under systemd that is `WorkingDirectory=~/app`, so
  the default `data/last_render.png` lands at
  `/home/eink-calendar/app/data/last_render.png` — the path the systemd unit's
  `ReadWritePaths` and `pull_preview.sh`'s default both already expect. Leave it
  at the default unless you have a reason not to; if you set an absolute path,
  keep it **outside** `~/.config/eink-calendar/` (so `deploy.sh secrets`'
  `rsync --delete` can't touch it) and add it to the unit's `ReadWritePaths`.
- `refresh.daily_time` and `refresh.timezone` — when the daily auto-refresh runs
- `accounts[].calendars[].color` — one of the six palette keys
  (`black`, `white`, `red`, `yellow`, `blue`, `green`), never a raw hex value
- `accounts[].credentials_file` / `token_file` — absolute or `~`-prefixed paths
  under `~/.config/eink-calendar/` (they are `expanduser()`'d but **not** resolved
  relative to the config file, so a bare filename will not be found)

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

The shipped unit (`systemd/eink-calendar.service`, owned by `gitops-manager`) is
authoritative. Key settings:

- `User=eink-calendar` / `Group=eink-calendar`,
  `WorkingDirectory=/home/eink-calendar/app` (a symlink systemd resolves afresh
  on every start — repointing it, as a deploy does, takes effect on the next
  `systemctl restart`),
  `ExecStart=…/app/.venv/bin/python -m eink_calendar.app`
- `Environment=EINK_CALENDAR_CONFIG=/home/eink-calendar/.config/eink-calendar/config.yaml`
  — set explicitly so config resolution (§6) does not depend on `HOME`
- `Environment=LG_WD=/tmp` — lgpio's `lg` library drops a `.lgd-nfy*` FIFO in
  CWD, which is the read-only release tree under `ProtectSystem=strict`; without
  this, lgpio init fails and `gpiozero` silently falls back to a missing pin
  factory (issue #86, confirmed on hardware)
- `Environment=GPIOZERO_PIN_FACTORY=lgpio` — fail loudly instead of falling back
- `ExecStartPre=+/bin/mkdir -p …/app/data` and `+/bin/chown` — the unit creates
  and owns the render-archive dir on the host before the sandbox binds it RW
  (`ReadWritePaths` does not create missing dirs). This is why a hand-followed
  §5 no longer needs a separate `mkdir` (issue #87); `install.sh` also creates it.
- `Restart=on-failure`, `RestartSec=5`, `After=/Wants=network-online.target`,
  `WantedBy=multi-user.target` — it comes back on its own after a reboot or a
  transient crash
- Hardening (`SECURITY.md` §5): `UMask=0077` (so `data/last_render.png` — a
  picture of the family calendar — is not world-readable), `NoNewPrivileges=true`,
  `ProtectSystem=strict`, `ProtectHome=read-only` with
  `ReadWritePaths=/home/eink-calendar/app/data /home/eink-calendar/.config/eink-calendar`
  (no `-` tolerance — the `ExecStartPre` guarantees `data/` exists, so a bind
  failure should stop the unit loudly), `PrivateTmp=true`, plus
  `ProtectKernelTunables/Modules`, `ProtectControlGroups`, `RestrictRealtime`,
  `RestrictSUIDSGID`, `LockPersonality`
- SPI/GPIO device access is left at the default policy pending hardware bring-up
  (§11); tightening to `DevicePolicy=closed` needs the real panel to verify

Check it:

```bash
systemctl status eink-calendar.service
journalctl -u eink-calendar.service -f
```

Within a few seconds the panel should show the default view.

## 10. Deploying updates

`scripts/deploy.sh` is release-based — it fetches the release tarball, repoints
`~eink-calendar/app`, runs the release's own `scripts/install.sh` (the §5
installer), and restarts the service, all over SSH. Three subcommands:

```bash
scripts/deploy.sh code    [user@]<pi-host> [VERSION]   # fetch release → repoint ~/app → run install.sh → restart
scripts/deploy.sh secrets [user@]<pi-host>             # rsync local ~/.config/eink-calendar/ → Pi (dir 0700 / files 0600 enforced)
scripts/deploy.sh all     [user@]<pi-host> [VERSION]   # secrets, then code
```

`VERSION` is a release tag such as `vX.Y.Z`; omitted, it uses the newest tag in
your local checkout (`git describe --tags --abbrev=0`). No git checkout is needed
on the Pi — only the §4–§7 setup (service user, `~/app` symlink, config dir).

**The SSH login user is a normal sudo-capable account — never the
`eink-calendar` service user** (which has no login shell). Give the target as
`user@pi-host` or set `EINK_SSH_USER`; a bare hostname connects as the host's
default SSH user and, if that's wrong, fails with `Permission denied
(publickey)`. That user needs `sudo` — the script runs `ssh -tt` so an ordinary
sudo **password prompt works** (issue #82); passwordless (`NOPASSWD`) sudo is
fine too but not required.

Neither path touches the Pi's `config.yaml`. The `code` path doesn't go near
`~/.config/eink-calendar/` at all; `deploy.sh secrets` syncs **only**
`*_credentials.json` / `*_token.json` (an rsync allowlist, `--delete` guarded by
the same filter — issue #109), so `config.yaml`, `cache.json` and other Pi-local
state are never synced or pruned. `config.yaml` is authored on the Pi (§6);
point the revoke/rotate procedure (§13) at `deploy.sh secrets` for pushing
rotated tokens.

Environment overrides (all optional): `EINK_SERVICE_USER` (default
`eink-calendar`), `EINK_HOME` (default `/home/<service user>`), `EINK_SERVICE`
(default `eink-calendar`), `EINK_CONFIG_DIR` (default `$HOME/.config/eink-calendar`
— the *local* rsync source), `EINK_REPO_SLUG` (default: parsed from `origin`),
`EINK_SSH_USER` (the sudo-capable login user, **not** the service user).

### Upgrading a Pi from a pre-0.3.0 release

v0.3.0 replaced `display.mock_output_path` with `display.output_path` (§6). A
config left from an older release keeps working — the app logs a one-line
warning and archives to the default `data/last_render.png` — but rename the key
in the Pi's `config.yaml` to silence it, or just delete it if the default path
is fine.

### Previewing the current screen

Without anything running on the Pi beyond `sshd`:

```bash
scripts/pull_preview.sh <pi-host>
```

This copies the Pi's `data/last_render.png` (from `~eink-calendar/app/data/`)
locally and opens it. Override `EINK_REMOTE_DIR` or `EINK_REMOTE_RENDER` if your
layout differs.

---

## 11. First-boot hardware bring-up checklist

Run once on real hardware and record the results here. **Results below are from
the first v0.2.0 bring-up (Raspberry Pi OS Trixie, Inky Impression 7.3").**

| Check | How | Result |
|---|---|---|
| `/dev/spidev0.0` and `/dev/i2c-1` both present | `ls -l /dev/spidev0.0 /dev/i2c-1` | _fill in_ |
| Panel EEPROM visible on I2C | `i2cdetect -y 1` shows a device at `0x50` | _fill in_ |
| App starts clean **as the service user** | `sudo -u eink-calendar -H bash -c '~/app/.venv/bin/python -m eink_calendar.app'` (exercises SPI CS + I2C + lgpio inside the systemd sandbox constraints) | yes (panel detected, buttons OK — see below) |
| Panel detected | `sudo -u eink-calendar -H bash -c '~/app/.venv/bin/python -c "from inky.auto import auto; print(auto().resolution)"'` | `(800, 480)` |
| `display.resolution` in config matches the line above | edit `config.yaml` | yes |
| Panel actually refreshes with the composited image | watch after `systemctl start` | **no** — tracked in #100 |
| Button pin map matches [Pimoroni's current pinout](https://learn.pimoroni.com/) | compare to `buttons.pin_map` | yes — see `gpioinfo` below |
| Button A cycles Day → Week → Month | press it | yes |
| Button B forces a refresh | press it, watch the journal | yes |
| Buttons C and D do nothing (no crash, no log) | press them | yes |
| Daily auto-refresh fires at `daily_time` | set a near-future time, wait | _fill in_ |
| Service restarts after `sudo reboot` with no prompt | reboot | yes |

`gpioinfo` from the bring-up Pi confirms the pin map — `inky` holds GPIO8/22/27
(SPI DC/CS/reset) and GPIO17; `lg` (lgpio, via `gpiozero` for the buttons) holds
GPIO5/6/16/24 with pull-ups and edge detection:

```
gpiochip0 - 58 lines:
	line   5:	"GPIO5"         	input bias=pull-up edges=both consumer="lg"
	line   6:	"GPIO6"         	input bias=pull-up edges=both consumer="lg"
	line   8:	"GPIO8"         	output bias=disabled consumer="inky"
	line  16:	"GPIO16"        	input bias=pull-up edges=both consumer="lg"
	line  17:	"GPIO17"        	input bias=pull-up consumer="inky"
	line  22:	"GPIO22"        	output bias=disabled consumer="inky"
	line  24:	"GPIO24"        	input bias=pull-up edges=both consumer="lg"
	line  27:	"GPIO27"        	output bias=disabled consumer="inky"
	(all other gpiochip0 lines: input, unclaimed)

gpiochip1 - 8 lines:
	line   0:	"BT_ON"         	output consumer="shutdown"
	line   2:	"PWR_LED_OFF"   	output active-low consumer="PWR"
	line   6:	"SD_PWR_ON"     	output consumer="regulator-sd-vcc"
	(gpiochip1 is the RP1 south bank — not used by this project)
```

---

## 12. Troubleshooting

**Panel never updates / blank panel**
`journalctl -u eink-calendar.service -e`. If SPI is disabled you'll see a device
error — re-run section 3. A blank panel with a healthy log usually means the
cache is empty and the first fetch failed; see the auth items below.

**Panel stays on the old image although init is clean (buttons work, no errors)**
Known open issue as of the first v0.2.0 bring-up — `inky.auto()` succeeds and the
service is healthy but the composited frame never reaches the panel. Tracked in
**#100** (`persona/developer`). Not a config problem; nothing to change here yet.

**`RuntimeError: No EEPROM detected!` in the log**
`inky.auto()` reads the panel model over I2C and I2C is off, or the service user
isn't in the `i2c` group. Re-run section 3 (`do_i2c 0`), confirm `/dev/i2c-1`
and `i2cdetect -y 1` shows `0x50`, and check `groups eink-calendar` includes
`i2c` (section 4).

**`Chip Select: (line 8, GPIO8) currently claimed by spi0 CS0`**
The kernel SPI driver is holding the chip-select line `inky` 2.x wants to manage
itself. Add `dtoverlay=spi0-0cs` under `dtparam=spi=on` in
`/boot/firmware/config.txt` and reboot (section 3).

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

1. Re-run the one-time consent for each account (section 8), then push the
   refreshed credential/token files with `scripts/deploy.sh secrets <pi-host>`
   (or `scp` them individually). `secrets` syncs only `*_credentials.json` /
   `*_token.json` — it does **not** touch the Pi's `config.yaml` (§6, §10). The
   dead `*_token.json` were already removed in "How to revoke" step 5.
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
