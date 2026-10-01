#!/usr/bin/env bash
# Source after creating job scratch, before launching any release application.
# The outer SIF wrapper binds its own job directory at /tmp. Each subprocess
# gets only this literal environment; provider credentials and user overrides
# are never inherited. The calling shell's HOME is not changed.

scitex_release_context() {
    local scratch="${1:?release scratch is required}"
    local venv="${2:?release interpreter environment is required}"
    case "$scratch" in
        /*) ;;
        *) echo "::error::release scratch must be absolute" >&2; return 1 ;;
    esac
    test -d "$scratch" && test -w "$scratch" || {
        echo "::error::release scratch must already exist and be writable" >&2
        return 1
    }
    mkdir -p "$scratch/scitex" "$scratch/cache" "$scratch/xdg-data" \
        "$scratch/xdg-config" "$scratch/runtime" "$scratch/pip-cache"
    chmod 700 "$scratch/runtime"
    local refused="$scratch/refused-store-socket"
    test ! -e "$refused" || {
        echo "::error::refused release store socket path already exists" >&2
        return 1
    }
    local encoded="${refused//%/%25}"
    encoded="${encoded// /%20}"
    encoded="${encoded//\//%2F}"
    encoded="${encoded//&/%26}"
    encoded="${encoded//\?/%3F}"
    encoded="${encoded//#/%23}"
    SCITEX_RELEASE_ENV=(
        "PATH=$venv/bin:/usr/local/bin:/usr/bin:/bin"
        "LANG=C.UTF-8" "LC_ALL=C.UTF-8"
        "SCITEX_LOGGING_FORMAT=default"
        "SCITEX_TESTMON_CACHE_ROOT=$scratch/cache/testmon"
        "TMPDIR=$scratch"
        "SCITEX_DIR=$scratch/scitex"
        "XDG_CACHE_HOME=$scratch/cache"
        "XDG_DATA_HOME=$scratch/xdg-data"
        "XDG_CONFIG_HOME=$scratch/xdg-config"
        "XDG_RUNTIME_DIR=$scratch/runtime"
        "UV_CACHE_DIR=$scratch/uv-cache" "UV_NO_CONFIG=1"
        "PIP_CACHE_DIR=$scratch/pip-cache" "PIP_CONFIG_FILE=/dev/null"
        "PYTHONNOUSERSITE=1" "PYTHONDONTWRITEBYTECODE=1"
        "GIT_CONFIG_GLOBAL=/dev/null" "GIT_CONFIG_NOSYSTEM=1"
        "PGHOST=$refused" "PGPORT=1"
        "PGUSER=release-refused" "PGDATABASE=release-refused"
        "SCITEX_STORE_DSN=postgresql://release-refused@/release-refused?host=$encoded&port=1&connect_timeout=1"
    )
}

scitex_release_run() {
    test "${#SCITEX_RELEASE_ENV[@]}" -gt 0 || {
        echo "::error::release context was not initialized" >&2
        return 1
    }
    env -i "${SCITEX_RELEASE_ENV[@]}" "$@"
}
