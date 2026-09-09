#!/usr/bin/env bash
# scripts/deploy.sh — git-based deploy to a Raspberry Pi.
#
# Primary path: push the current branch, then over SSH have the Pi pull,
# reinstall Pi requirements, and restart the systemd service.
#
# Secrets are NEVER deployed by the git path. They live outside the checkout in
# ~/.config/eink-calendar/ and are synced only by the explicit `secrets`
# subcommand below (rsync, not git).
#
# Usage:
#   scripts/deploy.sh code    <pi-host>   # push + pull + reinstall + restart
#   scripts/deploy.sh secrets <pi-host>   # rsync local ~/.config/eink-calendar/ to the Pi
#   scripts/deploy.sh all     <pi-host>   # secrets, then code
#
# Environment:
#   EINK_REMOTE_DIR   checkout path on the Pi   (default: /opt/eink-calendar)
#   EINK_SERVICE      systemd unit name         (default: eink-calendar)
#   EINK_CONFIG_DIR   local secrets dir         (default: $HOME/.config/eink-calendar)
#   EINK_SSH_USER     ssh user on the Pi        (default: the host's default)

set -euo pipefail

REMOTE_DIR="${EINK_REMOTE_DIR:-/opt/eink-calendar}"
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

deploy_code() {
  local target; target="$(ssh_host "$1")"
  local branch; branch="$(git rev-parse --abbrev-ref HEAD)"
  local sha;    sha="$(git rev-parse --short HEAD)"

  echo "==> Pushing ${branch} (${sha})"
  git push origin "${branch}"

  echo "==> Deploying to ${target}:${REMOTE_DIR}"
  ssh "${target}" REMOTE_DIR="${REMOTE_DIR}" SERVICE="${SERVICE}" BRANCH="${branch}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd "${REMOTE_DIR}"
sudo -u eink git fetch --prune origin
sudo -u eink git checkout "${BRANCH}"
sudo -u eink git reset --hard "origin/${BRANCH}"
if [ -f requirements-pi.txt ]; then
  sudo -u eink "${REMOTE_DIR}/.venv/bin/pip" install --quiet --upgrade -r requirements-pi.txt
fi
sudo systemctl restart "${SERVICE}.service"
sudo systemctl --no-pager --lines=5 status "${SERVICE}.service" || true
REMOTE
  echo "==> Code deploy complete"
}

deploy_secrets() {
  local target; target="$(ssh_host "$1")"
  [ -d "${CONFIG_DIR}" ] || die "local config dir not found: ${CONFIG_DIR}"

  echo "==> Syncing secrets ${CONFIG_DIR}/ -> ${target}:~/.config/eink-calendar/"
  # Trailing slash on source: copy contents, not the dir itself.
  # --delete keeps the Pi in sync with local; adjust if you keep Pi-only files.
  rsync -az --delete --chmod=D700,F600 \
    "${CONFIG_DIR}/" "${target}:.config/eink-calendar/"
  echo "==> Secrets sync complete (never committed to git)"
}

main() {
  local cmd="${1:-}"; local host="${2:-}"
  [ -n "${host}" ] || die "usage: deploy.sh {code|secrets|all} <pi-host>"
  case "${cmd}" in
    code)    deploy_code "${host}" ;;
    secrets) deploy_secrets "${host}" ;;
    all)     deploy_secrets "${host}"; deploy_code "${host}" ;;
    *)       die "unknown command '${cmd}' (expected code|secrets|all)" ;;
  esac
}

main "$@"
