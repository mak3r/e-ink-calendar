#!/usr/bin/env bash
# scripts/deploy.sh — git-based deploy to a Raspberry Pi.
#
# Primary path: push the current branch, then over SSH have the Pi pull,
# reinstall Pi requirements, and restart the systemd service.
#
# Secrets are NEVER deployed by the git path. They live outside the checkout in
# the service user's ~/.config/eink-calendar/ and are synced only by the
# explicit `secrets` subcommand below (rsync + sudo cp, not git).
#
# Assumes the Pi has been set up per docs/runbook.md §4–§7: a dedicated
# `--system` service user (default name `eink-calendar`) with no login shell,
# in the spi,gpio groups, owning ~/app and ~/.config/eink-calendar/.
#
# Usage:
#   scripts/deploy.sh code    <pi-host>   # push + pull + reinstall + restart
#   scripts/deploy.sh secrets <pi-host>   # rsync local ~/.config/eink-calendar/ to the Pi
#   scripts/deploy.sh all     <pi-host>   # secrets, then code
#
# Environment:
#   EINK_SERVICE_USER  service user on the Pi   (default: eink-calendar)
#   EINK_REMOTE_DIR    checkout path on the Pi  (default: ~<service user>/app)
#   EINK_SERVICE       systemd unit name        (default: eink-calendar)
#   EINK_CONFIG_DIR    local secrets dir        (default: $HOME/.config/eink-calendar)
#   EINK_SSH_USER      ssh user on the Pi       (default: the host's default; must have sudo)

set -euo pipefail

SERVICE_USER="${EINK_SERVICE_USER:-eink-calendar}"
REMOTE_DIR="${EINK_REMOTE_DIR:-/home/${SERVICE_USER}/app}"
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
  ssh "${target}" \
    REMOTE_DIR="${REMOTE_DIR}" SERVICE="${SERVICE}" SERVICE_USER="${SERVICE_USER}" BRANCH="${branch}" \
    'bash -s' <<'REMOTE'
set -euo pipefail
if [ ! -d "${REMOTE_DIR}/.git" ]; then
  echo "deploy: ${REMOTE_DIR} is not a git checkout." >&2
  echo "        deploy.sh needs a git-based install. Set it up once with:" >&2
  echo "        sudo -u ${SERVICE_USER} git clone <repo-url> ${REMOTE_DIR}" >&2
  echo "        (see docs/runbook.md §5)" >&2
  exit 1
fi
cd "${REMOTE_DIR}"
sudo -u "${SERVICE_USER}" git fetch --prune origin
sudo -u "${SERVICE_USER}" git checkout "${BRANCH}"
sudo -u "${SERVICE_USER}" git reset --hard "origin/${BRANCH}"
if [ -f requirements-pi.txt ]; then
  sudo -u "${SERVICE_USER}" "${REMOTE_DIR}/.venv/bin/pip" install --quiet --upgrade -r requirements-pi.txt
fi
sudo systemctl restart "${SERVICE}.service"
sudo systemctl --no-pager --lines=5 status "${SERVICE}.service" || true
REMOTE
  echo "==> Code deploy complete"
}

deploy_secrets() {
  local target; target="$(ssh_host "$1")"
  [ -d "${CONFIG_DIR}" ] || die "local config dir not found: ${CONFIG_DIR}"

  local stage="/tmp/eink-secrets-$$"
  echo "==> Staging secrets ${CONFIG_DIR}/ -> ${target}:${stage}/"
  # Trailing slash on source: copy contents, not the dir itself.
  rsync -az --delete --chmod=D700,F600 "${CONFIG_DIR}/" "${target}:${stage}/"

  echo "==> Installing into ~${SERVICE_USER}/.config/eink-calendar/ as ${SERVICE_USER}"
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
