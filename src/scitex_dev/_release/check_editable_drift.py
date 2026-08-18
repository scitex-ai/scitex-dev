"""Editable-install drift warning.

Fires once per process (CLI invocation, first `import scitex_dev`, MCP
server boot). It warns ONLY when a NEWER scitex-dev is AVAILABLE — i.e. the
installed one is genuinely BEHIND — never merely because a dev checkout is
ahead of the last release tag (that ahead-of-tag false positive, which also
emitted a bare `git pull --rebase` bomb, is exactly what this fixes).

- Editable (`pip install -e .`) install: HEAD is BEHIND its tracking
  upstream (`origin/<branch>`). Remedy is CWD-independent + non-destructive:
  `git -C <abs-repo-path> pull --ff-only` (NEVER a bare `git pull` or
  `--rebase` — from another CWD those hit the wrong repo / rewrite work).
- Wheel (PyPI) install: installed version < latest, where "latest" comes
  ONLY from a pre-existing version-cache file (no network on the hot path;
  the cache refresher is a separate task). Remedy is `pip install -U`.

Severity is knob-controlled (default `warn`; `error` hard-fails the
command), resolved ECOSYSTEM → config.yaml → knob-state.json.

Designed to be **silent and fast** on the hot path:

- Non-editable installs: single `direct_url.json` read (~1ms), then return.
- Editable, cache hit (`.git/HEAD` mtime unchanged since last check):
  read cached result (~1ms).
- Editable, cache miss: run `git describe`/`rev-list` (~30–50ms),
  write cache. Subsequent invocations are cache hits.

Suppressed entirely when env var `SCITEX_DEV_NO_DRIFT_WARN=1` is set
(useful for CI, scripts, or when the warning becomes noise).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


_CACHE_DIR = Path.home() / ".cache" / "scitex" / "dev"
_CACHE_FILE = _CACHE_DIR / "editable-drift.json"
_ENV_DISABLE = "SCITEX_DEV_NO_DRIFT_WARN"
# Belt-and-braces: only run the check at most once per N seconds even
# across cache invalidations, so a `git checkout` flurry doesn't thrash.
_MIN_INTERVAL_SECONDS = 30


from ._drift_git import (  # noqa: F401 - re-exported for existing callers
    _GIT,
    _behind_upstream,
    _compute_drift,
    _editable_dir_from_meta,
    _editable_source_dir,
    _git_state_key,
    _is_completion_context,
    _run_git,
    _upstream_ref,
)


def _installed_version(distribution: str) -> str | None:
    """The version recorded in the installed dist metadata, or None."""
    try:
        from importlib.metadata import version as _version

        return _version(distribution)
    except Exception:  # noqa: BLE001 — fail-safe: absence must never crash
        return None


def _cached_latest(distribution: str) -> str | None:
    """Latest published version from a pre-existing version-cache file, or None.

    We DO NOT build or refresh the cache here (that is a separate task) and we
    NEVER hit the network on this hot path. If a refresher has already written
    a cache file we read it; otherwise there is no evidence and we stay silent.

    Path resolution: ``$SCITEX_DEV_VERSION_CACHE`` override (injectable for
    tests), else ``~/.scitex/dev/runtime/version-latest.json``. Tolerant of a
    bare ``{"latest": "x"}`` / ``{"version": "x"}`` shape.
    """
    override = os.getenv("SCITEX_DEV_VERSION_CACHE")
    if override:
        path = Path(override).expanduser()
    else:
        try:
            from scitex_config._ecosystem import local_state

            path = local_state.path("dev", "runtime", "version-latest.json")
        except Exception:  # noqa: BLE001 — fail-safe
            return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    val = data.get("latest") or data.get("version")
    return str(val).strip() if val else None


def _is_older(installed: str, latest: str) -> bool:
    """True iff ``installed`` is strictly older than ``latest`` (PEP 440)."""
    try:
        from packaging.version import Version

        return Version(installed) < Version(latest)
    except Exception:  # noqa: BLE001 — never crash on an odd version string
        return installed != latest and installed < latest


def _pypi_drift(distribution: str) -> str | None:
    """Non-editable path — warn when the installed version is behind latest.

    "Latest" comes only from a pre-existing version-cache file; without one we
    stay silent (no network on the hot path). Remedy is ``pip install -U``.
    """
    installed = _installed_version(distribution)
    latest = _cached_latest(distribution)
    if not installed or not latest:
        return None
    if not _is_older(installed, latest):
        return None
    return (
        f"scitex-dev {installed} is behind latest {latest} — run: "
        f"pip install -U {distribution}"
    )


# Exit code used only when the severity knob is `error`. Distinct from
# click's 1/2 so a staleness abort is never mistaken for a usage error.
EXIT_STALE = 3
_SEVERITIES = ("silent", "warn", "error")
_SEVERITY_DEFAULT = "warn"
# Appended to every emitted staleness line (operator request) so the reader
# always sees how to control it: the env kill-switch + the severity knob.
# (Being AHEAD of the remote is silently ignored and needs no note.)
_SUPPRESS_HINT = (
    "suppress: SCITEX_DEV_NO_DRIFT_WARN=1 · severity: staleness_severity knob"
)


def _severity_from_config(key: str = "staleness_severity") -> str | None:
    """``key`` from the hand-authored ``~/.scitex/dev/config.yaml``.

    ``$SCITEX_DEV_CONFIG`` overrides the path (injectable for tests).
    """
    override = os.getenv("SCITEX_DEV_CONFIG")
    if override:
        path = Path(override).expanduser()
    else:
        from scitex_config._ecosystem import local_state

        path = local_state.path("dev", "config.yaml")
    if not path.is_file():
        return None
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    val = data.get(key)
    return str(val).strip().lower() if val else None


def _severity_from_knob_state(key: str = "staleness_severity") -> str | None:
    """``key`` from the machine-managed ``knob-state.json``.

    Reuses the same state file and ``$SCITEX_DEV_KNOB_STATE`` override the
    skills/mcp/test_execution knobs use.
    """
    from scitex_dev._core._knobs import _knob_state_path

    path = _knob_state_path()
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    val = data.get(key)
    return str(val).strip().lower() if val else None


def _resolve_severity(
    key: str = "staleness_severity", default: str = _SEVERITY_DEFAULT
) -> str:
    """`silent` | `warn` (default) | `error`, resolved with the standard
    ECOSYSTEM(default) → config.yaml → knob-state.json precedence.

    ``key``/``default`` parameterize the knob name so the currency gate
    (:mod:`scitex_dev.staleness`, key ``currency_severity``, default
    ``error``) reuses the exact resolution ladder. Only consulted when a
    drift message already exists (off the hot path). Any failure or
    unrecognised value degrades to the default — a bad knob must never
    break the host command.
    """
    severity = default
    for reader in (_severity_from_config, _severity_from_knob_state):
        try:
            value = reader(key)
        except Exception:  # noqa: BLE001 — fail-safe: never break the CLI
            value = None
        if value in _SEVERITIES:
            severity = value  # later readers (knob-state) win — highest precedence
    return severity


def _log_stale(level: str, text: str, stream=None) -> None:
    """Emit the staleness line through scitex-logging (auto ``WARN:``/``ERRO:``
    severity prefix — the operator's requested, uncluttered format).

    Falls back to a plain stderr line with an explicit ``WARN:``/``ERROR:``
    prefix when scitex-logging is unavailable, so a pristine venv still gets a
    severity-tagged message instead of a heavy new dep or a crash.
    """
    try:
        import scitex_logging

        logger = scitex_logging.getLogger("scitex_dev")
        (logger.error if level == "error" else logger.warning)(text)
        return
    except Exception:  # noqa: BLE001 — fail-safe: a warning must never crash
        prefix = "ERROR" if level == "error" else "WARN"
        print(f"{prefix}: {text}", file=stream if stream is not None else sys.stderr)


def _react_to_drift(message: str | None, severity: str, stream=None) -> int:
    """Emit the drift line (if any) at the right level and return an exit code.

    Returns :data:`EXIT_STALE` only when ``severity == "error"`` and there IS
    a message — the caller then aborts non-zero to FORCE the update. ``warn``
    logs at WARNING and returns 0 (continue); ``silent`` stays quiet.
    """
    if not message or severity == "silent":
        return 0
    level = "error" if severity == "error" else "warn"
    _log_stale(level, f"{message}  ({_SUPPRESS_HINT})", stream)
    return EXIT_STALE if severity == "error" else 0


def _read_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(payload: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(payload))
    except OSError:
        pass


def check(distribution: str = "scitex-dev") -> str | None:
    """Return a one-line warning string, or None.

    Cheap on the hot path: returns None in ~1–2ms for non-editable
    installs and ~1ms for editable installs with a fresh cache.
    """
    if os.environ.get(_ENV_DISABLE):
        return None
    src = _editable_source_dir(distribution)
    if src is None:
        # Non-editable (wheel) install: warn only when a pre-existing version
        # cache shows the installed version is behind the latest published one.
        return _pypi_drift(distribution)
    state_key = _git_state_key(src)
    if state_key is None:
        return None
    cache = _read_cache()
    entry = cache.get(distribution, {})
    now = time.time()
    if (
        entry.get("state_key") == state_key
        and now - float(entry.get("checked_at", 0)) < 86400
    ):
        return entry.get("warning")
    if now - float(entry.get("checked_at", 0)) < _MIN_INTERVAL_SECONDS:
        # Avoid thrashing when HEAD/tags are being rewritten in a tight loop.
        return entry.get("warning")
    warning = _compute_drift(src)
    cache[distribution] = {
        # Renamed from 'head_mtime' deliberately rather than reused. The old
        # key held a float mtime and this holds a sha pair, so an existing
        # cache file simply misses on the new name and recomputes once —
        # which is the correct migration. Reusing the name would have made a
        # stale float compare unequal to a string forever, silently disabling
        # the cache instead of refreshing it.
        "state_key": state_key,
        "checked_at": now,
        "warning": warning,
    }
    _write_cache(cache)
    return warning


_SUBPROCESS_MARKER = "_SCITEX_DEV_DRIFT_EMITTED"


def emit_if_drift(distribution: str = "scitex-dev") -> None:
    """Print warning to stderr if there is one. Safe to call repeatedly.

    Suppression is two-layered so a parent process emits at most once and
    every subprocess (e.g. each per-leaf auditor spawned by `audit-all`)
    inherits the suppression via env var instead of re-printing the same
    drift line N times:
    - In-process: function-attribute flag.
    - Across processes: `_SCITEX_DEV_DRIFT_EMITTED=1` env var, set after
      the first emit and inherited by every subprocess.
    """
    if getattr(emit_if_drift, "_emitted", False):
        return
    if os.environ.get(_SUBPROCESS_MARKER) == "1":
        emit_if_drift._emitted = True  # type: ignore[attr-defined]
        return
    # Don't emit when invoked as a Click shell-completion source eval
    # (`.bashrc`/`.zshrc` typically embed
    #  `eval "$(_SCITEX_DEV_COMPLETE=bash_source scitex-dev)"`),
    # otherwise every shell startup prints the drift line.
    if _is_completion_context():
        emit_if_drift._emitted = True  # type: ignore[attr-defined]
        return
    emit_if_drift._emitted = True  # type: ignore[attr-defined]
    msg = check(distribution)
    # Mark for any subprocess we spawn, regardless of whether we printed
    # (no-drift state should also propagate so the env stays consistent).
    os.environ[_SUBPROCESS_MARKER] = "1"
    severity = _resolve_severity() if msg else _SEVERITY_DEFAULT
    code = _react_to_drift(msg, severity)
    if code:
        # severity=error on a genuinely stale checkout: hard-fail the command
        # (after printing the copy-paste remedy) so the update is not ignored.
        # SystemExit is NOT caught by the `except Exception` at the import
        # callsite, so it propagates and the process exits non-zero.
        raise SystemExit(code)
