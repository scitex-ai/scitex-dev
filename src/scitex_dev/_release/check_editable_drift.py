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
_GIT = shutil.which("git")
_ENV_DISABLE = "SCITEX_DEV_NO_DRIFT_WARN"
# Belt-and-braces: only run the check at most once per N seconds even
# across cache invalidations, so a `git checkout` flurry doesn't thrash.
_MIN_INTERVAL_SECONDS = 30


def _editable_dir_from_meta(meta) -> Path | None:
    """Editable source dir from a Distribution's ``direct_url.json`` (PEP 610),
    or None. Shared with :mod:`scitex_dev.staleness` (path-aware callers pass
    their own resolved Distribution instead of a global name lookup)."""
    try:
        raw = meta.read_text("direct_url.json")
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not data.get("dir_info", {}).get("editable"):
        return None
    url = data.get("url", "")
    if url.startswith("file://"):
        return Path(url[len("file://") :])
    return None


def _editable_source_dir(distribution: str) -> Path | None:
    """Return the editable-install source directory, or None if not editable.

    Reads `<dist-info>/direct_url.json` per PEP 610.
    """
    try:
        from importlib.metadata import distribution as _dist
    except ImportError:
        return None
    try:
        meta = _dist(distribution)
    except Exception:
        return None
    return _editable_dir_from_meta(meta)


def _git_state_mtime(repo: Path) -> float | None:
    """Composite mtime so the cache invalidates on commit moves AND tag fetches.

    `git fetch --tags` updates `.git/packed-refs` (and/or files under
    `.git/refs/tags/`) but does NOT touch `.git/HEAD`. Keying the cache
    only on HEAD's mtime made `git fetch --tags --force` invisible to
    the next drift check — the cache returned the stale "ahead of v0.X"
    line until something else (commit, checkout) bumped HEAD.

    Take max(HEAD, packed-refs, refs/tags/) so any of those three
    bumping invalidates the cache.
    """
    git_dir = repo / ".git"
    if not git_dir.exists():
        return None
    candidates: list[float] = []
    for rel in ("HEAD", "packed-refs"):
        p = git_dir / rel
        if p.is_file():
            try:
                candidates.append(p.stat().st_mtime)
            except OSError:
                pass
    refs_tags = git_dir / "refs" / "tags"
    if refs_tags.is_dir():
        try:
            candidates.append(refs_tags.stat().st_mtime)
        except OSError:
            pass
    return max(candidates) if candidates else None


# Backward-compat alias so any external caller that imports the old name
# keeps working — our own callsite uses _git_state_mtime now.
_git_head_mtime = _git_state_mtime


def _run_git(repo: Path, *args: str) -> str | None:
    if _GIT is None:
        return None
    try:
        result = subprocess.run(
            [_GIT, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_completion_context() -> bool:
    """True when the current process is a Click shell-completion source eval.

    `.bashrc`/`.zshrc` typically embed
        eval "$(_SCITEX_DEV_COMPLETE=bash_source scitex-dev)"
    which runs scitex-dev on every shell startup. Emitting the drift line
    in that path produces an unwanted warning every time the user opens a
    new shell or types `bash`. The Click env var is a reliable signal.
    """
    # Match any `_<PROG>_COMPLETE=...` from `eval "$(_FOO_COMPLETE=bash_source foo)"`
    # — scitex-dev's drift checker is imported transitively whenever any
    # downstream tool (scitex-scholar, scitex-io, …) is invoked, including
    # during their own shell-completion sourcing. Without broad matching,
    # the drift line ends up in the completion candidate list and bash
    # treats it as one of the suggestions (symptom: "TAB needed twice").
    return any(k == "_CLICK_COMPLETE" or k.endswith("_COMPLETE") for k in os.environ)


def _upstream_ref(repo: Path) -> str | None:
    """Resolve the tracking upstream for HEAD (e.g. ``origin/develop``).

    Resolution order:
      1. The configured upstream via ``@{u}`` (``origin/<branch>``).
      2. ``origin/<current-branch>`` if such a remote-tracking ref exists.
      3. ``origin/HEAD``, then ``origin/develop`` / ``origin/main``.
    Returns None when nothing resolves (→ AXIS 1 stays silent, fail-safe).
    """
    ref = _run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if ref:
        return ref
    branch = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    candidates: list[str] = []
    if branch and branch != "HEAD":
        candidates.append(f"origin/{branch}")
    head_ref = _run_git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if head_ref:
        candidates.append(head_ref)
    candidates += ["origin/develop", "origin/main"]
    for cand in candidates:
        if _run_git(repo, "rev-parse", "--verify", "--quiet", cand) is not None:
            return cand
    return None


def _behind_upstream(repo: Path) -> int | None:
    """Commits the tracking upstream has that HEAD lacks (i.e. BEHIND count).

    Returns the behind count, 0 if level/ahead, or None when there is no
    resolvable upstream (→ stay silent, fail-safe). Uses only the LOCAL
    remote-tracking ref (as fresh as the last ``git fetch``) — no network.
    """
    upstream = _upstream_ref(repo)
    if not upstream:
        return None
    # `--left-right --count A...B` → "<left-only>\t<right-only>":
    # left = commits in upstream not in HEAD = BEHIND.
    counts = _run_git(
        repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD"
    )
    if not counts:
        return None
    parts = counts.split()
    if len(parts) != 2:
        return None
    return int(parts[0])


def _compute_drift(repo: Path, distribution: str = "scitex-dev") -> str | None:
    """Editable path — warn ONLY when the checkout is BEHIND its remote.

    "Stale" == a newer scitex-dev is available to pull, i.e. HEAD is behind
    ``origin/<branch>``. The remedy is CWD-independent + non-destructive:
    ``git -C <abs-repo-path> pull --ff-only`` — NEVER a bare ``git pull`` or
    ``--rebase`` (from another CWD those hit the wrong repo / rewrite work).

    Being AHEAD of the latest release tag (unreleased dev commits on
    ``develop``) is NORMAL and is NOT flagged — that was the reported false
    positive. Any git error / no upstream / not a repo → None (fail-safe).
    """
    try:
        behind = _behind_upstream(repo)
        if not behind:
            return None
        head = _run_git(repo, "rev-parse", "--short", "HEAD")
        if not head:
            return None
    except (ValueError, OSError):
        return None
    return (
        f"editable {distribution}: HEAD ({head}) is {behind} commit(s) behind "
        f"its remote — run: git -C {repo} pull --ff-only"
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
    state_mtime = _git_state_mtime(src)
    if state_mtime is None:
        return None
    cache = _read_cache()
    entry = cache.get(distribution, {})
    now = time.time()
    if (
        entry.get("head_mtime") == state_mtime
        and now - float(entry.get("checked_at", 0)) < 86400
    ):
        return entry.get("warning")
    if now - float(entry.get("checked_at", 0)) < _MIN_INTERVAL_SECONDS:
        # Avoid thrashing when HEAD/tags are being rewritten in a tight loop.
        return entry.get("warning")
    warning = _compute_drift(src)
    cache[distribution] = {
        # Field name kept as 'head_mtime' for backward compat with existing
        # cache files; semantically it now stores the composite git-state mtime.
        "head_mtime": state_mtime,
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
