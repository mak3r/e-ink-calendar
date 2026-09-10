#!/usr/bin/env bash
# scripts/install.sh — install / refresh the Pi runtime for the current release.
#
# THE single implementation of docs/runbook.md §5. Run it from INSIDE an
# extracted release directory (the tree this script ships in):
#
#   cd ~eink-calendar/app && sudo ./scripts/install.sh
#
# scripts/deploy.sh calls this same script over SSH, so a first install on the
# Pi and a later `deploy.sh code` run go through identical steps — no drift
# between the runbook and the deploy path (issues #81, #66, #68).
#
# Idempotent: safe to re-run for every release. Must run as root (the lgpio /
# spidev build toolchain is apt-installed); the venv is created as the service
# user so the systemd unit can use it.
#
# Steps: Python-version guard (3.11–3.13) → apt `swig python3-dev
# build-essential libopenjp2-7` → plain venv → `pip install --require-hashes -r
# requirements.lock` (falls back to `requirements-pi.txt` for pre-lock releases).
#
# Environment:
#   EINK_SERVICE_USER  service user that owns the venv (default: eink-calendar)

set -euo pipefail

SERVICE_USER="${EINK_SERVICE_USER:-eink-calendar}"

die() { echo "install: $*" >&2; exit 1; }

RELEASE_DIR="$(pwd)"

# Refuse to run anywhere but an extracted release — the runtime manifest is the
# marker.
if [ ! -f requirements.lock ] && [ ! -f requirements-pi.txt ]; then
  die "no requirements.lock / requirements-pi.txt in ${RELEASE_DIR}
       run this from inside an extracted release, e.g.:
         cd ~${SERVICE_USER}/app && sudo ./scripts/install.sh"
fi

[ "$(id -u)" -eq 0 ] || die "must run as root (apt is needed for the build toolchain): sudo ./scripts/install.sh"
id "${SERVICE_USER}" >/dev/null 2>&1 || die "service user '${SERVICE_USER}' does not exist — see docs/runbook.md §4"

# --- Python version guard (Bookworm 3.11 .. Trixie-era 3.13) ------------------
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "${PYV}" in
  3.11|3.12|3.13) echo "==> Python ${PYV}" ;;
  *) die "unsupported Python ${PYV} (supported: 3.11-3.13)" ;;
esac

# --- Build toolchain for the lgpio / spidev C extensions ---------------------
# Neither piwheels nor PyPI ships a wheel for them on cp3x, so they build from
# their hash-verified sdists — swig + the Python headers are what the #66
# failure was missing. numpy / Pillow install as wheels.
if command -v apt-get >/dev/null 2>&1; then
  echo "==> Installing build toolchain (swig, Python headers)"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    swig python3-dev build-essential libopenjp2-7
else
  echo "install: apt-get not found — ensure swig + Python headers are present yourself" >&2
fi

# --- venv + hash-locked runtime, owned by the service user ------------------
echo "==> Creating venv and installing the runtime as ${SERVICE_USER}"
sudo -u "${SERVICE_USER}" -H RELEASE_DIR="${RELEASE_DIR}" bash -s <<'AS_SERVICE_USER'
set -euo pipefail
cd "${RELEASE_DIR}"
mkdir -p data
[ -d .venv ] || python3 -m venv .venv
if [ -f requirements.lock ]; then
  # SECURITY.md §6: hash-verified install, never the loose requirements-*.txt.
  .venv/bin/pip install --quiet --require-hashes -r requirements.lock
else
  # Fallback for releases cut before requirements.lock existed.
  .venv/bin/pip install --quiet -r requirements-pi.txt
fi
AS_SERVICE_USER

echo "==> Runtime install complete (${RELEASE_DIR})"
