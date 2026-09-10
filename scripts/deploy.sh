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
# The `code` path apt-installs the Pi runtime/build prerequisites (needs the SSH
# user to have passwordless sudo) and enforces a supported Python range
# (3.11–3.13) before touching the venv — see issue #66.
#
# Usage:
#   scripts/deploy.sh code    <pi-host> [VERSION]  # fetch release + reinstall + restart
#   scripts/deploy.sh secrets <pi-host>            # rsync local ~/.config/eink-calendar/ to the Pi
#   scripts/deploy.sh all     <pi-host> [VERSION]  # secrets, then code
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
#   EINK_SSH_USER      ssh user on the Pi       (default: the host's default; must have sudo)

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
  else
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
  ssh "${target}" \
    SERVICE="${SERVICE}" SERVICE_USER="${SERVICE_USER}" \
    TARBALL="${tarball}" RELEASE_DIR="${dir}" \
    'bash -s' <<'REMOTE'
set -euo pipefail

# Supported Pi interpreters: Raspberry Pi OS Bookworm (3.11) .. Trixie (3.13).
# Fail early and clearly instead of dying inside a swig build (issue #66).
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "${PYV}" in
  3.11|3.12|3.13) echo "==> Pi Python ${PYV}" ;;
  *) echo "deploy: unsupported Pi Python ${PYV} (supported: 3.11-3.13)" >&2; exit 1 ;;
esac

# Pi runtime + build prerequisites. piwheels ships no lgpio/spidev wheels for
# cp313, so we install the distro builds (no compiler needed) and pull them into
# the venv via --system-site-packages; swig + headers are the fallback for any
# package that still has to build from sdist.
if command -v apt-get >/dev/null 2>&1; then
  echo "==> Ensuring Pi dependency packages"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-lgpio python3-spidev python3-numpy python3-pil python3-gpiozero \
    swig python3-dev build-essential libopenjp2-7
else
  echo "deploy: apt-get not found — install lgpio/spidev/numpy/pil + swig/headers yourself" >&2
fi

sudo -u "${SERVICE_USER}" -H \
  TARBALL="${TARBALL}" RELEASE_DIR="${RELEASE_DIR}" \
  bash -c '
    set -euo pipefail
    cd ~
    if [ ! -d "${RELEASE_DIR}" ]; then
      curl -fsSL "${TARBALL}" | tar xz
    fi
    ln -sfn "${RELEASE_DIR}" app
    cd app
    mkdir -p data
    # --system-site-packages so the apt-installed lgpio/spidev/numpy/Pillow
    # satisfy pip and it never falls back to a source build.
    [ -d .venv ] || python3 -m venv --system-site-packages .venv
    if [ -f requirements-pi.txt ]; then
      # No --upgrade: leave already-satisfied system packages in place.
      .venv/bin/pip install --quiet -r requirements-pi.txt
    fi
  '
sudo systemctl restart "${SERVICE}.service"
sudo systemctl --no-pager --lines=5 status "${SERVICE}.service" || true
REMOTE
  echo "==> Code deploy complete (${version})"
}

deploy_secrets() {
  local target; target="$(ssh_host "$1")"
  [ -d "${CONFIG_DIR}" ] || die "local config dir not found: ${CONFIG_DIR}"

  local stage="/tmp/eink-secrets-$$"
  echo "==> Staging secrets ${CONFIG_DIR}/ -> ${target}:${stage}/"
  # Trailing slash on source: copy contents, not the dir itself.
  rsync -az --delete --chmod=D700,F600 "${CONFIG_DIR}/" "${target}:${stage}/"

  echo "==> Installing into ${SERVICE_HOME}/.config/eink-calendar/ as ${SERVICE_USER}"
  ssh "${target}" STAGE="${stage}" SERVICE_USER="${SERVICE_USER}" 'bash -s' <<'REMOTE'
set -euo pipefail
DEST="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)/.config/eink-calendar"
sudo install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 700 "${DEST}"
sudo rsync -a --delete --chown="${SERVICE_USER}:${SERVICE_USER}" "${STAGE}/" "${DEST}/"
sudo find "${DEST}" -type f -exec chmod 600 {} +
rm -rf "${STAGE}"
REMOTE
  echo "==> Secrets sync complete (never committed to git)"
}

main() {
  local cmd="${1:-}"; local host="${2:-}"; local version="${3:-}"
  [ -n "${host}" ] || die "usage: deploy.sh {code|secrets|all} <pi-host> [VERSION]"
  case "${cmd}" in
    code)    deploy_code "${host}" "${version}" ;;
    secrets) deploy_secrets "${host}" ;;
    all)     deploy_secrets "${host}"; deploy_code "${host}" "${version}" ;;
    *)       die "unknown command '${cmd}' (expected code|secrets|all)" ;;
  esac
}

main "$@"
