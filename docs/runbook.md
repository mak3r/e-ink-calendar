# Runbook

Operational guide for the e-ink calendar: a Raspberry Pi driving a Pimoroni
Inky Impression (Spectra-6) panel that shows a Google Calendar in Day / Week /
Month views.

This guide is generic and public — it assumes no prior context on the project.
Replace `<owner>/<repo>` and the example paths with your own values.

> **Status:** Cross-checked against the merged `SECURITY.md` (#4),
> `scripts/setup_oauth.py` (#14), and the #15/#66 infra. §5 installs from the
> merged hash-locked `requirements.lock` (`--require-hashes`), mirroring
> `scripts/deploy.sh` (#68/#73). §11 (hardware bring-up) still needs one pass on
> real hardware.

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

Always deploy a **tagged release**, never `main` HEAD. Install the release
tarball and point `~eink-calendar/app` at it — no git checkout on the Pi.
`scripts/deploy.sh code` (§10) automates exactly these steps for later updates.

```bash
# pick the latest tag from https://github.com/<owner>/<repo>/releases
VERSION=v0.1.0
sudo -u eink-calendar -H bash -c "
  cd ~ &&
  curl -fsSL https://github.com/<owner>/<repo>/archive/refs/tags/${VERSION}.tar.gz | tar xz &&
  ln -sfn <repo>-${VERSION#v} app
"
```

`~app` stays a symlink to the extracted `<repo>-<version>` directory; a deploy
just extracts the new release and repoints the symlink, and the systemd unit
resolves it afresh on every restart.

**Install the lgpio/spidev build toolchain first.** Neither piwheels nor PyPI
ships an `lgpio` or `spidev` wheel for Python 3.13, so they build from their
(hash-verified) sdists on the Pi; without `swig` and the Python headers that
fails with an opaque `swig: No such file or directory` /
`Python.h: No such file or directory` (issue #66). `scripts/deploy.sh code` runs
this exact line:

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  swig python3-dev build-essential libopenjp2-7
```

Then create a plain venv and install the runtime from the pinned, hash-locked
`requirements.lock` — **`--require-hashes`, never the loose `requirements-*.txt`**
(`SECURITY.md` §6, issue #68). `requirements.lock` is `==`-pinned with `--hash=`
lines for every transitive dependency; a plain venv reproduces it exactly rather
than borrowing anything from system site-packages:

```bash
sudo -u eink-calendar -H bash -c "
  cd ~/app &&
  python3 -m venv .venv &&
  .venv/bin/pip install --require-hashes -r requirements.lock
"
```

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
- `Restart=on-failure`, `RestartSec=5`, `After=/Wants=network-online.target`,
  `WantedBy=multi-user.target` — it comes back on its own after a reboot or a
  transient crash
- Hardening (`SECURITY.md` §5): `UMask=0077` (so `data/last_render.png` — a
  picture of the family calendar — is not world-readable), `NoNewPrivileges=true`,
  `ProtectSystem=strict`, `ProtectHome=read-only` with
  `ReadWritePaths=-/home/eink-calendar/app/data /home/eink-calendar/.config/eink-calendar`
  (the leading `-` tolerates the release-relative `data/` dir not existing yet),
  `PrivateTmp=true`, plus `ProtectKernelTunables/Modules`, `ProtectControlGroups`,
  `RestrictRealtime`, `RestrictSUIDSGID`, `LockPersonality`
- SPI/GPIO device access is left at the default policy pending hardware bring-up
  (§11); tightening to `DevicePolicy=closed` needs the real panel to verify

Check it:

```bash
systemctl status eink-calendar.service
journalctl -u eink-calendar.service -f
```

Within a few seconds the panel should show the default view.

## 10. Deploying updates

`scripts/deploy.sh` is release-based — it does the same tarball-and-symlink dance
as §5, over SSH. Three subcommands:

```bash
scripts/deploy.sh code    <pi-host> [VERSION]   # fetch release tarball → repoint ~/app → hash-locked reinstall → restart
scripts/deploy.sh secrets <pi-host>             # rsync local ~/.config/eink-calendar/ → Pi (dir 0700 / files 0600 enforced)
scripts/deploy.sh all     <pi-host> [VERSION]   # secrets, then code
```

`VERSION` is a release tag such as `v0.1.0`; omitted, it uses the newest tag in
your local checkout (`git describe --tags --abbrev=0`). No git checkout is needed
on the Pi — only the §4–§7 setup (service user, `~/app` symlink, config dir) and
passwordless-or-prompted `sudo` for the SSH user. `code` also apt-installs the
lgpio/spidev build toolchain, rejects an unsupported Python (outside 3.11–3.13),
and installs from `requirements.lock` with `--require-hashes` — the same steps §5
lists by hand.

Secrets under `~eink-calendar/.config/eink-calendar/` are **never** touched by
the `code` path — only the explicit `secrets` subcommand syncs them, and only
when they actually change. Point the revoke/rotate procedure (§13) at
`deploy.sh secrets` for pushing rotated tokens.

Environment overrides (all optional): `EINK_SERVICE_USER` (default
`eink-calendar`), `EINK_HOME` (default `/home/<service user>`), `EINK_SERVICE`
(default `eink-calendar`), `EINK_CONFIG_DIR` (default `$HOME/.config/eink-calendar`
— the *local* rsync source), `EINK_REPO_SLUG` (default: parsed from `origin`),
`EINK_SSH_USER`.

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

Run once on real hardware and record the results here:

| Check | How | Result |
|---|---|---|
| Panel detected | `sudo -u eink-calendar -H bash -c '~/app/.venv/bin/python -c "from inky.auto import auto; print(auto().resolution)"'` | (800, 480) |
| `display.resolution` in config matches the line above | edit `config.yaml` | yes |
| Panel actually refreshes with the composited image | watch after `systemctl start` | no |
| Button pin map matches [Pimoroni's current pinout](https://learn.pimoroni.com/) | compare to `buttons.pin_map` | see table below |
| Button A cycles Day → Week → Month | press it | yes |
| Button B forces a refresh | press it, watch the journal | yes|
| Buttons C and D do nothing (no crash, no log) | press them | yes |
| Daily auto-refresh fires at `daily_time` | set a near-future time, wait | _fill in_ |
| Service restarts after `sudo reboot` with no prompt | reboot | yes |

```
gpioinfo 
gpiochip0 - 58 lines:
	line   0:	"ID_SDA"        	input
	line   1:	"ID_SCL"        	input
	line   2:	"GPIO2"         	input
	line   3:	"GPIO3"         	input
	line   4:	"GPIO4"         	input
	line   5:	"GPIO5"         	input bias=pull-up edges=both consumer="lg"
	line   6:	"GPIO6"         	input bias=pull-up edges=both consumer="lg"
	line   7:	"GPIO7"         	input
	line   8:	"GPIO8"         	output bias=disabled consumer="inky"
	line   9:	"GPIO9"         	input
	line  10:	"GPIO10"        	input
	line  11:	"GPIO11"        	input
	line  12:	"GPIO12"        	input
	line  13:	"GPIO13"        	input
	line  14:	"GPIO14"        	input
	line  15:	"GPIO15"        	input
	line  16:	"GPIO16"        	input bias=pull-up edges=both consumer="lg"
	line  17:	"GPIO17"        	input bias=pull-up consumer="inky"
	line  18:	"GPIO18"        	input
	line  19:	"GPIO19"        	input
	line  20:	"GPIO20"        	input
	line  21:	"GPIO21"        	input
	line  22:	"GPIO22"        	output bias=disabled consumer="inky"
	line  23:	"GPIO23"        	input
	line  24:	"GPIO24"        	input bias=pull-up edges=both consumer="lg"
	line  25:	"GPIO25"        	input
	line  26:	"GPIO26"        	input
	line  27:	"GPIO27"        	output bias=disabled consumer="inky"
	line  28:	"RGMII_MDIO"    	input
	line  29:	"RGMIO_MDC"     	input
	line  30:	"CTS0"          	input
	line  31:	"RTS0"          	input
	line  32:	"TXD0"          	input
	line  33:	"RXD0"          	input
	line  34:	"SD1_CLK"       	input
	line  35:	"SD1_CMD"       	input
	line  36:	"SD1_DATA0"     	input
	line  37:	"SD1_DATA1"     	input
	line  38:	"SD1_DATA2"     	input
	line  39:	"SD1_DATA3"     	input
	line  40:	"PWM0_MISO"     	input
	line  41:	"PWM1_MOSI"     	input
	line  42:	"STATUS_LED_G_CLK"	output consumer="ACT"
	line  43:	"SPIFLASH_CE_N" 	input
	line  44:	"SDA0"          	input
	line  45:	"SCL0"          	input
	line  46:	"RGMII_RXCLK"   	input
	line  47:	"RGMII_RXCTL"   	input
	line  48:	"RGMII_RXD0"    	input
	line  49:	"RGMII_RXD1"    	input
	line  50:	"RGMII_RXD2"    	input
	line  51:	"RGMII_RXD3"    	input
	line  52:	"RGMII_TXCLK"   	input
	line  53:	"RGMII_TXCTL"   	input
	line  54:	"RGMII_TXD0"    	input
	line  55:	"RGMII_TXD1"    	input
	line  56:	"RGMII_TXD2"    	input
	line  57:	"RGMII_TXD3"    	input
```
```
gpiochip1 - 8 lines:
	line   0:	"BT_ON"         	output consumer="shutdown"
	line   1:	"WL_ON"         	output
	line   2:	"PWR_LED_OFF"   	output active-low consumer="PWR"
	line   3:	"GLOBAL_RESET"  	output
	line   4:	"VDD_SD_IO_SEL" 	output consumer="vdd-sd-io"
	line   5:	"CAM_GPIO"      	output consumer="regulator-cam1"
	line   6:	"SD_PWR_ON"     	output consumer="regulator-sd-vcc"
	line   7:	"SD_OC_N"       	input
```
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

1. Re-run the one-time consent for each account (section 8), then push the
   refreshed config dir to the Pi with `scripts/deploy.sh secrets <pi-host>`
   (or `scp` the individual token files). The dead `*_token.json` were already
   removed in "How to revoke" step 5.
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
