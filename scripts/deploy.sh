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
# explicit `secrets` subcommand below (rsync + sudo rsync --chown, not git).
#
# Assumes the Pi has been set up per docs/runbook.md §4–§7: a dedicated
# `--system` service user (default name `eink-calendar`) with no login shell,
# in the spi,gpio groups, owning ~/app (a symlink to an extracted release) and
# ~/.config/eink-calendar/.
#
# SSH login user: the service user has no login shell, so you connect as a
# normal sudo-capable user. Pass `user@host`, or set EINK_SSH_USER — a bare
# hostname connects as `<service-user>@host` and fails with "Permission denied
# (publickey)". That user needs `sudo`; this script allocates a TTY (`ssh -tt`)
# so an ordinary password prompt works (issue #82). NOPASSWD sudo also works.
#
# The `code` path just fetches the release tarball, repoints ~/app, and runs the
# release's own `scripts/install.sh` on the Pi — the same script docs/runbook.md
# §5 has the operator run by hand (issue #81). install.sh does the Python
# guard (3.11–3.13, #66), the lgpio/spidev build toolchain, and the hash-locked
# `pip install --require-hashes -r requirements.lock` (SECURITY.md §6, #68).
#
# Usage:
#   scripts/deploy.sh code    [user@]<pi-host> [VERSION]  # fetch release + install + restart
#   scripts/deploy.sh secrets [user@]<pi-host>            # rsync local ~/.config/eink-calendar/ to the Pi
#   scripts/deploy.sh all     [user@]<pi-host> [VERSION]  # secrets, then code
#
# VERSION is a release tag such as v1.0.0. When omitted, the newest tag reachable
# from the local checkout (`git describe --tags --abbrev=0`) is used.
#
# Environment:
#   EINK_SERVICE_USER  service user on the Pi   (default: eink-calendar)
#   EINK_HOME          service user's home      (default: /home/<service user>)
#   EINK_SERVICE       systemd unit name        (default: eink-calendar)
#   EINK_CONFIG_DIR    local secrets dir        (default: $HOME/.config/eink-calendar)
#   EINK_REPO_SLUG     GitHub <owner>/<repo>    (default: parsed from `origin`)
#   EINK_SSH_USER      ssh login user on the Pi (default: from `user@host`, else the
#                      host's own default; must have sudo — NOT the service user)

set -euo pipefail

SERVICE_USER="${EINK_SERVICE_USER:-eink-calendar}"
SERVICE_HOME="${EINK_HOME:-/home/${SERVICE_USER}}"
SERVICE="${EINK_SERVICE:-eink-calendar}"
CONFIG_DIR="${EINK_CONFIG_DIR:-$HOME/.config/eink-calendar}"

die() { echo "deploy: $*" >&2; exit 1; }

ssh_host() {
  local host="$1"
  if [ -n "${EINK_SSH_USER:-}" ]; then
    echo "${EINK_SSH_USER}@${host}"
  elif [ "${host}" != "${host#*@}" ]; then
    # already user@host
    echo "${host}"
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

deploy_code() {
  local target; target="$(ssh_host "$1")"
  local version="${2:-}"
  if [ -z "${version}" ]; then
    version="$(git describe --tags --abbrev=0)" || die "no local tags; pass VERSION explicitly"
  fi
  local slug; slug="$(repo_slug)"
  local tarball="https://github.com/${slug}/archive/refs/tags/${version}.tar.gz"
  # GitHub's tag archive extracts to <repo>-<version without leading v>
  local reponame="${slug#*/}"
  local dir="${reponame}-${version#v}"

  echo "==> Deploying ${slug} ${version} to ${target}"
  # -tt forces a TTY so an ordinary `sudo` password prompt works on the Pi
  # (issue #82); NOPASSWD sudo is fine too.
  ssh -tt "${target}" \
    SERVICE="${SERVICE}" SERVICE_USER="${SERVICE_USER}" \
    TARBALL="${tarball}" RELEASE_DIR="${dir}" \
    'bash -s' <<'REMOTE'
set -euo pipefail

HOME_DIR="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)"
[ -n "${HOME_DIR}" ] || { echo "deploy: service user ${SERVICE_USER} not found — see docs/runbook.md §4" >&2; exit 1; }

# 1. Fetch + extract the release and repoint ~/app, as the service user.
sudo -u "${SERVICE_USER}" -H TARBALL="${TARBALL}" RELEASE_DIR="${RELEASE_DIR}" bash -s <<'FETCH'
set -euo pipefail
cd ~
[ -d "${RELEASE_DIR}" ] || curl -fsSL "${TARBALL}" | tar xz
ln -sfn "${RELEASE_DIR}" app
FETCH

# 2. Run the release's own installer (same script as docs/runbook.md §5).
sudo EINK_SERVICE_USER="${SERVICE_USER}" bash -c "cd '${HOME_DIR}/${RELEASE_DIR}' && ./scripts/install.sh"

# 3. Restart the service.
sudo systemctl restart "${SERVICE}.service"
sudo systemctl --no-pager --lines=5 status "${SERVICE}.service" || true
REMOTE
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

  echo "==> Installing into ${SERVICE_HOME}/.config/eink-calendar/ as ${SERVICE_USER}"
  # -tt so `sudo` can prompt for a password (issue #82).
  ssh -tt "${target}" STAGE="${stage}" SERVICE_USER="${SERVICE_USER}" 'bash -s' <<'REMOTE'
set -euo pipefail
trap 'rm -rf "${STAGE}"' EXIT
DEST="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)/.config/eink-calendar"
sudo install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 700 "${DEST}"
sudo rsync -a --delete \
  --include='*_credentials.json' --include='*_token.json' --exclude='*' \
  --chown="${SERVICE_USER}:${SERVICE_USER}" "${STAGE}/" "${DEST}/"
sudo find "${DEST}" -maxdepth 1 -type f \( -name '*_credentials.json' -o -name '*_token.json' \) -exec chmod 600 {} +
REMOTE
  echo "==> Secrets sync complete (credential/token files only; config.yaml untouched)"
}

main() {
  local cmd="${1:-}"; local host="${2:-}"; local version="${3:-}"
  [ -n "${host}" ] || die "usage: deploy.sh {code|secrets|all} [user@]<pi-host> [VERSION]  (SSH user needs sudo; see header)"
  case "${cmd}" in
    code)    deploy_code "${host}" "${version}" ;;
    secrets) deploy_secrets "${host}" ;;
    all)     deploy_secrets "${host}"; deploy_code "${host}" "${version}" ;;
    *)       die "unknown command '${cmd}' (expected code|secrets|all)" ;;
  esac
}

main "$@"
