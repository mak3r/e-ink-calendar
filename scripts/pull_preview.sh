#!/usr/bin/env bash
# scripts/pull_preview.sh — fetch and open the Pi's current rendered image.
#
# Requires nothing running on the Pi beyond sshd. The render
# (~eink-calendar/app/data/last_render.png) is written by the service under
# UMask=0077, so it is mode 0600 owned by the nologin `eink-calendar` user — an
# ordinary SSH user cannot read it directly. This pulls it via `sudo` on the Pi
# (rsync --rsync-path="sudo rsync", with a `sudo cat` fallback), the same
# passwordless-sudo baseline scripts/deploy.sh assumes (issues #82, #89).
#
# Usage:
#   scripts/pull_preview.sh [user@]<pi-host>
#
# Environment:
#   EINK_REMOTE_DIR   app dir on the Pi         (default: /home/eink-calendar/app,
#                     the service user's ~/app symlink — see docs/runbook.md §5)
#   EINK_REMOTE_RENDER path to the render, overrides REMOTE_DIR/data/last_render.png
#   EINK_SSH_USER     ssh login user on the Pi  (default: from user@host, else the
#                     host's default; must have passwordless sudo, NOT eink-calendar)
#   EINK_PREVIEW_OUT  local output path         (default: ./data/last_render.png)

set -euo pipefail

REMOTE_DIR="${EINK_REMOTE_DIR:-/home/eink-calendar/app}"
REMOTE_RENDER="${EINK_REMOTE_RENDER:-${REMOTE_DIR}/data/last_render.png}"
OUT="${EINK_PREVIEW_OUT:-./data/last_render.png}"

die() { echo "pull_preview: $*" >&2; exit 1; }

host="${1:-}"
[ -n "${host}" ] || die "usage: pull_preview.sh [user@]<pi-host>"

target="${host}"
[ -n "${EINK_SSH_USER:-}" ] && target="${EINK_SSH_USER}@${host}"

mkdir -p "$(dirname "${OUT}")"

echo "==> Fetching ${target}:${REMOTE_RENDER}"
# Primary: rsync running as root on the far end so it can read the 0600 file.
if rsync -az --rsync-path="sudo rsync" "${target}:${REMOTE_RENDER}" "${OUT}" 2>/dev/null; then
  :
else
  # Fallback: `sudo cat` over ssh. No `-t`, so stdin is not a PTY and the binary
  # stream passes through untouched (a PTY would mangle it — issue #89).
  echo "==> rsync path failed, trying sudo cat"
  # REMOTE_RENDER is deliberately expanded client-side into the remote command
  # (it is our own default or the operator's EINK_REMOTE_RENDER).
  # shellcheck disable=SC2029
  ssh "${target}" "sudo cat -- '${REMOTE_RENDER}'" > "${OUT}" \
    || die "could not fetch render — is passwordless sudo set up for ${target%%@*}, and does ${REMOTE_RENDER} exist yet?"
fi

[ -s "${OUT}" ] || die "fetched an empty file — ${REMOTE_RENDER} may not exist on the Pi yet"

echo "==> Saved ${OUT}"

case "$(uname -s)" in
  Darwin) open "${OUT}" ;;
  Linux)  if command -v xdg-open >/dev/null 2>&1; then xdg-open "${OUT}"; else echo "(no opener; view ${OUT} manually)"; fi ;;
  *)      echo "(view ${OUT} manually)" ;;
esac
