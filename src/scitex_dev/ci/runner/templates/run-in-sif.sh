#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run-in-sif.sh — GitHub-runner-faithful Spartan CI executor (GOLD template).
#
# A repo onboards by copying this VERBATIM into .github/ci/run-in-sif.sh and
# calling it from its self-hosted `ci.yml` job. Nothing in here is repo-
# specific: the package name, deps, and test paths are all read from the
# checkout (pyproject.toml) at runtime.
#
# ===========================================================================
# THE MODEL — exactly like a GitHub-hosted runner: two layers + a wheel cache
# ===========================================================================
#
#   LAYER 1  BASE IMAGE (read-only, reused)        == github's runner image
#     The SIF ($SIF). A LEAN base: Python 3.11/3.12/3.13 + uv + basic tools
#     and system-libs (git, build-essential, libglib2.0-0, fd, ripgrep) +
#     scitex-dev (audit tooling). It bakes NO per-package deps. Never written.
#
#   LAYER 2  WORKFLOW OVERLAY (writable, cached)   == per-job disk + actions/cache
#     "A job == one workflow .yml file." Each pytest workflow gets ONE
#     writable overlay holding its installed deps, KEYED on
#         (python-version, sha256(this repo's pyproject.toml))
#     CACHE HIT  -> overlay for the key already exists -> REUSE it, NO install
#                   (== actions/cache restore).
#     CACHE MISS -> no overlay for the key -> create one, install deps into it,
#                   KEEP it under the key (== actions/cache save).
#     Overlays persist on GPFS, one per (repo x py-version) in steady state.
#     Superseded-key overlays (older pyproject hash) are PRUNED.
#
#   LAYER 0  SHARED WHEEL CACHE                    == github's pip/uv cache
#     $UV_CACHE_DIR on GPFS, shared by every workflow so the MISS/install
#     path is fast. uv locks the cache dir -> concurrency-safe.
#
# ---------------------------------------------------------------------------
# THE PERMISSION SOLUTION (root-owned baked-venv issue)
# ---------------------------------------------------------------------------
#   The SIF's /opt is root-owned and read-only; a non-root, no-fakeroot
#   overlay CANNOT copy-up /opt to write into a baked venv there (and an
#   ext3-image overlay needs fakeroot we don't have on the compute path). So
#   we DON'T touch /opt. Instead we use a DIRECTORY overlay (which a plain
#   user can write to) and create a FRESH venv at a BRAND-NEW path the overlay
#   owns -- $VENV_IN_SIF (default /ci/venv) -- as the runner user. Clean,
#   non-root, github-like: every workflow gets its own venv, just like a fresh
#   hosted runner.
#
# ---------------------------------------------------------------------------
# Env contract (set by ci.yml from repo Actions Variables / runner env):
#   APPTAINER        path to the apptainer binary (vars.SCITEX_CI_APPTAINER)
#   SIF              path to the read-only base SIF (vars.SCITEX_CI_SIF)
#   CI_OVERLAY_ROOT  GPFS dir holding keyed overlays
#                    (vars.SCITEX_CI_OVERLAY_ROOT)
#   UV_CACHE_DIR     GPFS shared uv wheel cache (vars.SCITEX_CI_UV_CACHE)
# Optional:
#   PY_VERSION       python version (else $1, else 3.12)
#   PYTEST_ARGS      extra args appended to pytest (e.g. coverage flags)
#   PYTEST_N         xdist worker count (else derived; 0/"" => no -n)
#   VENV_IN_SIF      in-overlay venv path (default /ci/venv)
#   EXTRAS           pip extras spec (default ".[all,dev]")
#
# Usage (from ci.yml):  bash .github/ci/run-in-sif.sh "$PY_VERSION"
# ---------------------------------------------------------------------------
set -euo pipefail

PY_VERSION="${PY_VERSION:-${1:-3.12}}"
VENV_IN_SIF="${VENV_IN_SIF:-/ci/venv}"
EXTRAS="${EXTRAS:-.[all,dev]}"

# ---- validate the env contract loudly (no silent fallbacks) ----------------
: "${APPTAINER:?APPTAINER unset (repo var SCITEX_CI_APPTAINER)}"
: "${SIF:?SIF unset (repo var SCITEX_CI_SIF)}"
: "${CI_OVERLAY_ROOT:?CI_OVERLAY_ROOT unset (repo var SCITEX_CI_OVERLAY_ROOT)}"
: "${UV_CACHE_DIR:?UV_CACHE_DIR unset (repo var SCITEX_CI_UV_CACHE)}"
export UV_CACHE_DIR
[ -f pyproject.toml ] || {
    echo "::error::no pyproject.toml in $(pwd)"
    exit 1
}
[ -x "$APPTAINER" ] || command -v "$APPTAINER" >/dev/null || {
    echo "::error::apptainer not executable: $APPTAINER"
    exit 1
}
[ -e "$SIF" ] || {
    echo "::error::SIF missing: $SIF"
    exit 1
}

# ---- derive the cache key: (py-version, sha256(pyproject.toml)) ------------
# Repo slug = directory name (matches the GitHub repo); stable + readable.
REPO="$(basename "$(pwd)")"
PYHASH="$(sha256sum pyproject.toml | cut -c1-16)"
KEY="${REPO}-py${PY_VERSION}-${PYHASH}"
OVERLAY="${CI_OVERLAY_ROOT}/${KEY}"
READY="${OVERLAY}/.ready" # written only after a successful install
mkdir -p "$CI_OVERLAY_ROOT" "$UV_CACHE_DIR"

echo "::notice::scitex-ci key=${KEY}"
echo "::notice::scitex-ci overlay=${OVERLAY}"
echo "::notice::scitex-ci uv-cache=${UV_CACHE_DIR}"

# ---- LAYER 2 cache restore-or-save -----------------------------------------
if [ -f "$READY" ]; then
    # ============ CACHE HIT (== actions/cache restore) ============
    # The overlay for this exact (py, pyproject) already has the venv +
    # deps installed. REUSE it. NO install. Just run pytest.
    echo "::notice::CACHE HIT -- reusing overlay, skipping install"
    INSTALL_RAN=0
else
    # ============ CACHE MISS (== actions/cache save) ============
    # No overlay for this key. Build a fresh one: dir overlay -> fresh venv
    # (as the runner user, at a NEW path the overlay owns) -> install deps ->
    # mark .ready so the next run is a HIT.
    echo "::notice::CACHE MISS -- creating overlay + installing deps"
    rm -rf "$OVERLAY"
    mkdir -p "$OVERLAY"
    # A directory overlay needs upper/ + work/ for overlayfs; apptainer
    # auto-creates them, but pre-creating keeps perms unambiguous.
    mkdir -p "$OVERLAY/upper" "$OVERLAY/work"

    # The single-quoted body is INTENTIONAL: the outer shell must not expand
    # the in-container vars; host values are spliced via the '"'"'..'"'"' idiom.
    # shellcheck disable=SC2016
    "$APPTAINER" exec --overlay "$OVERLAY" "$SIF" bash -eu -c '
    set -o pipefail
    PYV="'"$PY_VERSION"'"
    VENV="'"$VENV_IN_SIF"'"
    EXTRAS="'"$EXTRAS"'"
    # FRESH venv at a brand-new, overlay-owned path (NOT /opt) -- the crux of
    # the permission fix. uv finds the matching baked interpreter.
    mkdir -p "$(dirname "$VENV")"
    uv venv --python "$PYV" "$VENV"
    # Install the checkout editable, with extras, into the fresh venv.
    # UV_CACHE_DIR (exported, on GPFS) makes this fast + shared.
    uv pip install --python "$VENV/bin/python" -e "$EXTRAS"
    # pytest plumbing: xdist for parallelism, timeout for the per-test cap.
    uv pip install --python "$VENV/bin/python" pytest-xdist pytest-timeout
  '
    # Mark ready ONLY after a clean install (set -e above aborts on failure,
    # leaving no .ready -> next run correctly re-MISSes).
    date -Iseconds >"$READY"
    INSTALL_RAN=1
fi

# ---- PRUNE superseded-key overlays for THIS repo+py (keep current) ---------
# Steady state = one overlay per (repo x py-version); old pyproject hashes
# are removed so GPFS doesn't grow unbounded.
shopt -s nullglob
for d in "${CI_OVERLAY_ROOT}/${REPO}-py${PY_VERSION}-"*; do
    [ "$d" = "$OVERLAY" ] && continue
    echo "::notice::pruning superseded overlay $(basename "$d")"
    rm -rf "$d"
done
shopt -u nullglob

# ---- derive xdist worker count ---------------------------------------------
# nproc under an srun --overlap step can report the affinity mask (often 1),
# so prefer SLURM_CPUS_PER_TASK, then getconf, then nproc. Cap //2 to strip
# HT inflation. Per-repo override via env PYTEST_N.
if [ -z "${PYTEST_N+x}" ]; then
    CORES="${SLURM_CPUS_PER_TASK:-}"
    [ -z "$CORES" ] && CORES="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc)"
    PYTEST_N="$((CORES / 2))"
    [ "$PYTEST_N" -lt 1 ] && PYTEST_N=1
fi
N_FLAG=""
[ -n "${PYTEST_N}" ] && [ "${PYTEST_N}" != "0" ] && N_FLAG="-n ${PYTEST_N}"

echo "::notice::scitex-ci install_ran=${INSTALL_RAN} xdist=${PYTEST_N:-none}"

# ---- run pytest INSIDE the (now-populated) overlay venv ---------------------
# Read-only SIF + the SAME keyed overlay. No PYTHONPATH shadowing: the editable
# install in the fresh venv IS the PR code (uv pip install -e .), exactly like a
# hosted runner.
# Single-quoted body intentional (see install block above).
# shellcheck disable=SC2016
"$APPTAINER" exec --overlay "$OVERLAY" "$SIF" bash -eu -c '
  set -o pipefail
  VENV="'"$VENV_IN_SIF"'"
  export PATH="$VENV/bin:$PATH"
  exec "$VENV/bin/python" -m pytest '"$N_FLAG"' --tb=short -p no:cacheprovider \
    '"${PYTEST_ARGS:-}"'
'
