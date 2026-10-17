#!/usr/bin/env bash
# Runs INSIDE the reused scitex-ci SIF (apptainer exec — invoked via
# exec-in-sif.sh). Publishes ./dist/* to PyPI via MANUAL OIDC Trusted
# Publishing, then twine upload.
#
# This CPU job uses the versioned SIF and a manual OIDC token exchange over
# HTTPS. Separate Docker/service runners do not determine this job's route:
#
#   1. Ask the GitHub Actions OIDC provider for a JWT with audience=pypi,
#      using the per-job ACTIONS_ID_TOKEN_REQUEST_{TOKEN,URL} env vars (present
#      because the publish job declares `permissions: id-token: write`).
#      apptainer exec (no --cleanenv) passes those host env vars into the SIF.
#   2. Exchange that JWT at PyPI's mint-token endpoint for a short-lived,
#      scope-limited PyPI API token.
#   3. twine upload dist/* with TWINE_USERNAME=__token__ and that minted token.
#
# PyPI verifies the Trusted Publisher identity during token minting:
# project=scitex-dev, owner=scitex-ai, repo=scitex-dev,
# workflow=pypi-publish-and-github-release-on-tag.yml. Configuration or
# identity mismatches fail the exchange; this header does not certify trust.
#
# curl, python and (after a --target install) twine all live in the SIF.
#
# Fail-loud (operator directive): every step asserts non-empty output and
# `set -euo pipefail`; any failure is a HARD error with the exact cause, never
# a silent skip.
set -euo pipefail

V="${1:-3.12}"
VENV="/opt/venv-$V"
PY="$VENV/bin/python"
test -x "$PY" || {
    echo "::error::baked python missing in $VENV — rebuild the SIF: scitex-container apptainer build ci-cpu"
    exit 1
}

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# dist/ must already hold the artifacts (downloaded by the publish job before
# this script runs). Fail loud if empty.
if [ ! -d dist ] || [ -z "$(ls -A dist 2>/dev/null)" ]; then
    echo "::error::dist/ is empty — nothing to publish (download the build artifact first)"
    exit 1
fi
echo "=== dist to publish ==="
ls -l dist

# --- writable scratch (compute-node HOME is RO inside the container) ---
TMPDIR="/tmp/publish-scitex_dev-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-0}-$V"
export TMPDIR
# `${TMPDIR:?}` — see run-in-sif.sh for the reasoning and the measurement.
# Short version: `rm -rf ""` exits 0 SILENTLY on GNU coreutils, so an empty name
# would delete nothing, fail nothing, and leave the rest of the script
# addressing paths off the filesystem root. `:?` aborts instead.
rm -rf "${TMPDIR:?publish scratch path is empty — refusing to rm -rf it}"
mkdir -p "$TMPDIR/site" "$TMPDIR/uv-cache"
source "$(dirname "${BASH_SOURCE[0]}")/release-context.sh"
scitex_release_context "$TMPDIR" "$VENV"

# --- step 1: request the OIDC JWT (audience=pypi) from GitHub ---
: "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:?ACTIONS_ID_TOKEN_REQUEST_TOKEN not set — the publish job needs 'permissions: id-token: write'}"
: "${ACTIONS_ID_TOKEN_REQUEST_URL:?ACTIONS_ID_TOKEN_REQUEST_URL not set — the publish job needs 'permissions: id-token: write'}"

echo "=== minting OIDC JWT (audience=pypi) ==="
JWT="$(scitex_release_run curl -fsS \
    -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
    "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=pypi" |
    scitex_release_run "$PY" -c 'import sys,json; print(json.load(sys.stdin)["value"])')"
test -n "$JWT" || {
    echo "::error::OIDC JWT request returned an empty token"
    exit 1
}
echo "OIDC JWT obtained (length=${#JWT})"

# Only the existing protected-main caller may publish on the company runner.
# The token remains RAM-only; this local claim check does not verify its signature.
printf '%s' "$JWT" | scitex_release_run "$PY" .github/ci/release-identity.py oidc \
    --commit "${GITHUB_SHA:?GITHUB_SHA must identify the dispatch workflow source}"

# --- step 2: exchange the JWT for a short-lived PyPI API token ---
echo "=== exchanging JWT at PyPI mint-token endpoint ==="
MINT_RESP="$(scitex_release_run curl -sS -X POST https://pypi.org/_/oidc/mint-token \
    -d "{\"token\":\"${JWT}\"}")"
MINTED="$(printf '%s' "$MINT_RESP" |
    scitex_release_run "$PY" -c 'import sys,json; d=json.load(sys.stdin); print(d.get("token",""))')"
if [ -z "$MINTED" ]; then
    # Error codes identify trust/configuration failures without echoing an
    # arbitrary provider response, which may contain credential fields.
    echo "::error::PyPI mint-token returned no token."
    printf '%s' "$MINT_RESP" |
        scitex_release_run "$PY" -c 'import sys,json,re
d=json.load(sys.stdin)
codes={e.get("code", "unknown") for e in d.get("errors", []) if isinstance(e, dict)}
safe=sorted(c for c in codes if isinstance(c, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", c))
print("PyPI mint-token error codes: " + (", ".join(safe) or "unknown"))' \
            2>/dev/null || echo "PyPI mint-token error codes: unreadable"
    exit 1
fi
echo "PyPI token minted (length=${#MINTED})"

# --- step 3: install twine into the writable target, then upload ---
echo "=== installing twine (--target) ==="
scitex_release_run uv pip install --python "$PY" --target="$TMPDIR/site" twine

echo "=== twine upload dist/* ==="
scitex_release_run env PYTHONPATH="$TMPDIR/site" \
    TWINE_USERNAME="__token__" TWINE_PASSWORD="$MINTED" \
    "$PY" -m twine upload --config-file /dev/null \
    --non-interactive --disable-progress-bar dist/*

echo "PUBLISH-OK: scitex-dev dist/* uploaded to PyPI via manual OIDC trusted publishing"
