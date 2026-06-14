#!/bin/bash
# Idempotent installer for the GitHub Actions self-hosted runner tarball.
#
# Operator directive 2026-06-14: pre-stage the install so the launcher's
# first-run fetch is integrity-checked + reproducible (no surprise version
# drift). Pinned to the same version `scitex_dev/ci/runner/launcher.sh`
# already defaults to (v2.328.0).
#
# Designed to run on the HPC compute node (spartan-bm159 today), but works
# on any Linux host with curl + sha256sum. No SLURM, no GitHub auth, no
# registration — that's launcher.sh's job. This script ONLY ensures the
# tarball is present + verified at the cache path launcher.sh checks first.
#
# Idempotent: re-running on an already-staged cache is a fast no-op.
#
# Usage:
#   install-runner.sh [--cache-dir DIR] [--version VER]
#
# Env (overrides):
#   RUNNER_VERSION   default 2.328.0
#   CACHE_DIR        default $HOME/.cache/scitex-dev/ci-runner
#                    (operator may want to point this at persistent project
#                    storage; launcher.sh reads $(dirname $RUNNER_HOME)/cache,
#                    so symlink if you want them to share)

set -euo pipefail

RUNNER_VERSION="${RUNNER_VERSION:-2.328.0}"
CACHE_DIR="${CACHE_DIR:-$HOME/.cache/scitex-dev/ci-runner}"

# Pinned SHA256 (downloaded + verified locally 2026-06-14 via curl from
# https://github.com/actions/runner/releases/download/v2.328.0/…).
# When bumping RUNNER_VERSION, update both the version AND the digest in
# the SHA256_BY_VERSION table below. CI will refuse to install an
# unknown version.
declare -A SHA256_BY_VERSION=(
  ["2.328.0"]="01066fad3a2893e63e6ca880ae3a1fad5bf9329d60e77ee15f2b97c148c3cd4e"
)

# CLI overrides.
while [ $# -gt 0 ]; do
  case "$1" in
    --cache-dir) CACHE_DIR="$2"; shift 2 ;;
    --version)   RUNNER_VERSION="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,/^set -euo pipefail$/p' "$0" | sed -e 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "ERR: unknown arg '$1' (try --help)" >&2
      exit 2 ;;
  esac
done

EXPECTED_SHA="${SHA256_BY_VERSION[$RUNNER_VERSION]:-}"
if [ -z "$EXPECTED_SHA" ]; then
  echo "ERR: unknown RUNNER_VERSION=$RUNNER_VERSION — no pinned digest." >&2
  echo "Update SHA256_BY_VERSION in $(basename "$0") and re-run." >&2
  exit 3
fi

TARBALL="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
DEST="$CACHE_DIR/$TARBALL"

mkdir -p "$CACHE_DIR"

# Fast path: already staged + verified.
if [ -f "$DEST" ]; then
  HAVE_SHA=$(sha256sum "$DEST" | awk '{print $1}')
  if [ "$HAVE_SHA" = "$EXPECTED_SHA" ]; then
    echo "[install-runner] cached $TARBALL verified ($HAVE_SHA)"
    echo "[install-runner] CACHE_DIR=$CACHE_DIR"
    exit 0
  fi
  echo "[install-runner] cached $TARBALL has WRONG sha ($HAVE_SHA != $EXPECTED_SHA); re-fetching" >&2
  rm -f "$DEST"
fi

echo "[install-runner] fetching $URL"
curl -fSL --retry 3 --retry-delay 5 -o "$DEST" "$URL"

HAVE_SHA=$(sha256sum "$DEST" | awk '{print $1}')
if [ "$HAVE_SHA" != "$EXPECTED_SHA" ]; then
  echo "ERR: downloaded $TARBALL sha mismatch: got $HAVE_SHA, expected $EXPECTED_SHA" >&2
  rm -f "$DEST"
  exit 4
fi

echo "[install-runner] staged + verified $TARBALL ($HAVE_SHA)"
echo "[install-runner] CACHE_DIR=$CACHE_DIR"
echo "[install-runner] Next: launcher.sh (called by 'scitex-dev ci runner up') will pick this up."
