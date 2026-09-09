#!/usr/bin/env bash
# scripts/pull_preview.sh — fetch and open the Pi's current rendered image.
#
# Requires nothing running on the Pi beyond sshd. No network listener, no
# web server — just an scp/rsync of the last render, then open it locally.
#
# Usage:
#   scripts/pull_preview.sh <pi-host>
#
# Environment:
#   EINK_REMOTE_DIR   checkout path on the Pi   (default: /opt/eink-calendar)
#   EINK_REMOTE_RENDER  path to the render, overrides REMOTE_DIR/data/last_render.png
#   EINK_SSH_USER     ssh user on the Pi        (default: the host's default)
#   EINK_PREVIEW_OUT  local output path         (default: ./data/last_render.png)

set -euo pipefail

REMOTE_DIR="${EINK_REMOTE_DIR:-/opt/eink-calendar}"
REMOTE_RENDER="${EINK_REMOTE_RENDER:-${REMOTE_DIR}/data/last_render.png}"
OUT="${EINK_PREVIEW_OUT:-./data/last_render.png}"

die() { echo "pull_preview: $*" >&2; exit 1; }

host="${1:-}"
[ -n "${host}" ] || die "usage: pull_preview.sh <pi-host>"

target="${host}"
[ -n "${EINK_SSH_USER:-}" ] && target="${EINK_SSH_USER}@${host}"

mkdir -p "$(dirname "${OUT}")"

echo "==> Fetching ${target}:${REMOTE_RENDER}"
rsync -az "${target}:${REMOTE_RENDER}" "${OUT}" \
  || scp "${target}:${REMOTE_RENDER}" "${OUT}" \
  || die "could not fetch render (does ${REMOTE_RENDER} exist on the Pi yet?)"

echo "==> Saved ${OUT}"

case "$(uname -s)" in
  Darwin) open "${OUT}" ;;
  Linux)  if command -v xdg-open >/dev/null 2>&1; then xdg-open "${OUT}"; else echo "(no opener; view ${OUT} manually)"; fi ;;
  *)      echo "(view ${OUT} manually)" ;;
esac
