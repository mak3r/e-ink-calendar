#!/usr/bin/env bash
# scripts/deploy.sh — release-based deploy to a Raspberry Pi.
#
# Primary path: fetch a tagged release tarball from GitHub, extract it into the
# service user's home, repoint the ~/app symlink at it, reinstall the Pi
# requirements, and restart the systemd service over SSH. This mirrors the
# manual install in docs/runbook.md §5 exactly — "always deploy a tagged
# release, never main HEAD" — so a Pi set up from the runbook can be updated
# with this script and nothing else (no git checkout required on the Pi).
#
# Secrets are NEVER deployed by the code path. They live outside the checkout in
# the service user's ~/.config/eink-calendar/ and are synced only by the
# explicit `secrets` subcommand below (rsync + rsync --chown, not git).
#
# Assumes the Pi has been set up per docs/runbook.md §4–§7: a dedicated
# `--system` service user (default name `eink-calendar`) with no login shell,
# in the spi,gpio groups, owning ~/app (a symlink to an extracted release) and
# ~/.config/eink-calendar/.
#
# SSH login user: the service user has no login shell, so you connect as a
# normal sudo-capable user. Pass `user@host`, or set EINK_SSH_USER — a bare
# hostname connects as `<service-user>@host` and fails with "Permission denied
# (publickey)". That user needs `sudo` (password prompt or NOPASSWD both work).
#
# How the remote steps run: each is written to a temp script on the Pi and run
# with a single `sudo bash <script>` under `ssh -tt`. The PTY exists only for a
# possible sudo password prompt; the script is a real file, so stdin is never
# consumed and the shell is non-interactive (issue #119 — an earlier fix piped
# a heredoc to `ssh -tt … bash -s`, which ran interactively and hung at the
# sudo prompt). Inside, root drops to the service user with `runuser` — no
# nested sudo, no RunAs-target password.
#
# Usage:
#   scripts/deploy.sh code         [user@]<pi-host> [VERSION]  # fetch release + install + restart
#   scripts/deploy.sh secrets      [user@]<pi-host>            # push credential/token files to the Pi
#   scripts/deploy.sh all          [user@]<pi-host> [VERSION]  # secrets, then code
#   scripts/deploy.sh check-config [user@]<pi-host>            # read-only: diff the SHARED config keys
#
# check-config compares only the keys the dev Mac and Pi must keep identical
# (accounts, refresh, view, buttons.bindings, cache.path) — never the
# env-specific ones (display.*, buttons.pin_map). It writes nothing and exits
# non-zero on drift. Needs python3 + PyYAML locally (both in requirements-*.txt).
#
# VERSION is a release tag such as v1.0.0. When omitted, the newest tag reachable
# from the local checkout (`git describe --tags --abbrev=0`) is used.
#
# Environment:
#   EINK_SERVICE_USER  service user on the Pi   (default: eink-calendar)
#   EINK_SERVICE       systemd unit name        (default: eink-calendar)
#   EINK_CONFIG_DIR    local secrets dir        (default: $HOME/.config/eink-calendar)
#   EINK_REPO_SLUG     GitHub <owner>/<repo>    (default: parsed from `origin`)
#   EINK_SSH_USER      ssh login user on the Pi (default: from `user@host`, else the
#                      host's own default; must have sudo — NOT the service user)

set -euo pipefail

SERVICE_USER="${EINK_SERVICE_USER:-eink-calendar}"
SERVICE="${EINK_SERVICE:-eink-calendar}"
CONFIG_DIR="${EINK_CONFIG_DIR:-$HOME/.config/eink-calendar}"

die() { echo "deploy: $*" >&2; exit 1; }

ssh_host() {
  local host="$1"
  if [ -n "${EINK_SSH_USER:-}" ]; then
    echo "${EINK_SSH_USER}@${host}"
  elif [ "${host}" != "${host#*@}" ]; then
    echo "${host}"                       # already user@host
  else
    echo "deploy: '${host}' has no login user — connecting as your default SSH user." >&2
    echo "        If that is wrong you'll get 'Permission denied (publickey)'; pass" >&2
    echo "        user@host or set EINK_SSH_USER (must have sudo, not the service user)." >&2
    echo "${host}"
  fi
}

repo_slug() {
  if [ -n "${EINK_REPO_SLUG:-}" ]; then
    echo "${EINK_REPO_SLUG}"
    return
  fi
  local url; url="$(git config --get remote.origin.url)" || die "no origin remote; set EINK_REPO_SLUG"
  # git@github.com:owner/repo.git  or  https://github.com/owner/repo.git
  url="${url%.git}"
  url="${url#*github.com[:/]}"
  case "${url}" in
    */*) echo "${url}" ;;
    *)   die "could not parse owner/repo from '${url}'; set EINK_REPO_SLUG" ;;
  esac
}

# run_remote_root <target> [args...] < script
#   Stream a script (stdin) to a temp file on the Pi, then run it once as root
#   with `sudo bash <file> [args...]` under a PTY. The script is a file, so
#   `sudo` can prompt for a password on the PTY without eating the script
#   (issue #119). Positional args reach the script as $1, $2, … .
run_remote_root() {
  local target="$1"; shift
  local remote="/tmp/eink-deploy-$$.sh"
  # ${remote} is expanded client-side on purpose — it's our own PID-derived path.
  # shellcheck disable=SC2029
  ssh "${target}" "cat > '${remote}' && chmod 700 '${remote}'"
  local q="" a
  for a in "$@"; do q+=" $(printf '%q' "${a}")"; done
  # shellcheck disable=SC2029
  ssh -tt "${target}" "sudo bash '${remote}'${q}; rc=\$?; rm -f '${remote}'; exit \$rc"
}

deploy_code() {
  local target; target="$(ssh_host "$1")"
  local version="${2:-}"
  if [ -z "${version}" ]; then
    version="$(git describe --tags --abbrev=0)" || die "no local tags; pass VERSION explicitly"
  fi
  [[ "${version}" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION '${version}' is not a vX.Y.Z release tag"

  local slug; slug="$(repo_slug)"
  local tarball="https://github.com/${slug}/archive/refs/tags/${version}.tar.gz"
  # GitHub's tag archive extracts to <repo>-<version without leading v>
  local dir="${slug#*/}-${version#v}"

  echo "==> Deploying ${slug} ${version} to ${target}"
  run_remote_root "${target}" "${SERVICE_USER}" "${tarball}" "${dir}" "${SERVICE}" <<'SCRIPT'
set -euo pipefail
SERVICE_USER="$1"; TARBALL="$2"; RELEASE_DIR="$3"; SERVICE="$4"

HOME_DIR="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)"
[ -n "${HOME_DIR}" ] || { echo "deploy: service user ${SERVICE_USER} not found — see docs/runbook.md §4" >&2; exit 1; }

# 1. Fetch + extract the release and repoint ~/app, as the service user.
runuser -u "${SERVICE_USER}" -- bash -c '
  set -euo pipefail
  cd ~
  [ -d "$1" ] || curl -fsSL "$2" | tar xz
  ln -sfn "$1" app
' _ "${RELEASE_DIR}" "${TARBALL}"

# 2. Run the release's own installer (same script as docs/runbook.md §5): the
#    Python guard (#66), the lgpio/spidev build toolchain, and the hash-locked
#    `pip install --require-hashes -r requirements.lock` (SECURITY.md §6, #68).
EINK_SERVICE_USER="${SERVICE_USER}" bash -c 'cd "$1/$2" && exec ./scripts/install.sh' _ "${HOME_DIR}" "${RELEASE_DIR}"

# 3. Restart the service.
systemctl restart "${SERVICE}.service"
systemctl --no-pager --lines=5 status "${SERVICE}.service" || true
SCRIPT
  echo "==> Code deploy complete (${version})"
}

deploy_secrets() {
  local target; target="$(ssh_host "$1")"
  [ -d "${CONFIG_DIR}" ] || die "local config dir not found: ${CONFIG_DIR}"

  local stage="/tmp/eink-secrets-$$"
  echo "==> Staging credential/token files ${CONFIG_DIR}/ -> ${target}:${stage}/"
  # Only credential/token files are pushed. config.yaml is authored ON the Pi
  # (docs/runbook.md §6) — the dev machine's is `driver: mock` and would blank
  # the panel — and anything else the service writes under
  # ~/.config/eink-calendar/ (cache.json, …) is Pi-local. The same filter guards
  # `--delete` on both legs, so it only prunes stale credential/token files,
  # never config.yaml or Pi-local state (issue #109).
  # Trailing slash on source: copy contents, not the dir itself.
  rsync -az --delete \
    --include='*_credentials.json' --include='*_token.json' --exclude='*' \
    --chmod=D700,F600 "${CONFIG_DIR}/" "${target}:${stage}/"

  echo "==> Installing into ~${SERVICE_USER}/.config/eink-calendar/ as ${SERVICE_USER}"
  run_remote_root "${target}" "${SERVICE_USER}" "${stage}" <<'SCRIPT'
set -euo pipefail
SERVICE_USER="$1"; STAGE="$2"
trap 'rm -rf "${STAGE}"' EXIT
DEST="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)/.config/eink-calendar"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 700 "${DEST}"
rsync -a --delete \
  --include='*_credentials.json' --include='*_token.json' --exclude='*' \
  --chown="${SERVICE_USER}:${SERVICE_USER}" "${STAGE}/" "${DEST}/"
find "${DEST}" -maxdepth 1 -type f \( -name '*_credentials.json' -o -name '*_token.json' \) -exec chmod 600 {} +
SCRIPT
  echo "==> Secrets sync complete (credential/token files only; config.yaml untouched)"
}

check_config() {
  local target; target="$(ssh_host "$1")"
  local local_cfg="${CONFIG_DIR}/config.yaml"
  [ -f "${local_cfg}" ] || die "local config not found: ${local_cfg}"
  command -v python3 >/dev/null 2>&1 || die "check-config needs python3"

  local pi_cfg; pi_cfg="$(mktemp)"
  trap 'rm -f "${pi_cfg}"' EXIT

  echo "==> Reading ${target}'s config.yaml (read-only, nothing is written)"
  # config.yaml is 0640 owned by the service user; read it via sudo. Same
  # passwordless-sudo baseline as pull_preview.sh / deploy.sh (#82).
  # shellcheck disable=SC2029
  ssh "${target}" "sudo cat -- \"\$(getent passwd '${SERVICE_USER}' | cut -d: -f6)/.config/eink-calendar/config.yaml\"" > "${pi_cfg}" \
    || die "could not read the Pi config — passwordless sudo for ${target%%@*} required"
  [ -s "${pi_cfg}" ] || die "the Pi config.yaml is empty or absent"

  python3 - "${local_cfg}" "${pi_cfg}" <<'PY'
import sys, json
try:
    import yaml
except ImportError:
    sys.exit("check-config: PyYAML not importable — `pip install pyyaml` (it ships in requirements-base.txt)")

SHARED_TOP = ("accounts", "refresh", "view")

def shared(cfg):
    cfg = cfg or {}
    out = {k: cfg[k] for k in SHARED_TOP if k in cfg}
    for parent, child in (("buttons", "bindings"), ("cache", "path")):
        section = cfg.get(parent) or {}
        if child in section:
            out.setdefault(parent, {})[child] = section[child]
    return out

local = shared(yaml.safe_load(open(sys.argv[1])))
pi    = shared(yaml.safe_load(open(sys.argv[2])))

if local == pi:
    print("config: shared keys (accounts, refresh, view, buttons.bindings, cache.path) are in sync")
    sys.exit(0)

import difflib
dump = lambda d: json.dumps(d, indent=2, sort_keys=True, default=str).splitlines()
print("config: shared keys DIFFER —")
print("\n".join(difflib.unified_diff(dump(pi), dump(local), "pi", "local", lineterm="")))
sys.exit(1)
PY
}

main() {
  local cmd="${1:-}"; local host="${2:-}"; local version="${3:-}"
  [ -n "${host}" ] || die "usage: deploy.sh {code|secrets|all|check-config} [user@]<pi-host> [VERSION]  (SSH user needs sudo; see header)"
  case "${cmd}" in
    code)         deploy_code "${host}" "${version}" ;;
    secrets)      deploy_secrets "${host}" ;;
    all)          deploy_secrets "${host}"; deploy_code "${host}" "${version}" ;;
    check-config) check_config "${host}" ;;
    *)            die "unknown command '${cmd}' (expected code|secrets|all|check-config)" ;;
  esac
}

main "$@"
