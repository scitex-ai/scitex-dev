"""Editable-install drift warning.

Fires once per process (CLI invocation, first `import scitex_dev`, MCP
server boot) when:

1. The package is installed editable (`pip install -e .`), AND
2. The working-tree HEAD differs from the latest release tag.

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


def _git_head_mtime(repo: Path) -> float | None:
    head = repo / ".git" / "HEAD"
    if not head.is_file():
        return None
    try:
        return head.stat().st_mtime
    except OSError:
        return None


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


def _compute_drift(repo: Path) -> str | None:
    """Return a one-line warning, or None if up-to-date / unknown."""
    latest_tag = _run_git(repo, "describe", "--tags", "--abbrev=0")
    head = _run_git(repo, "rev-parse", "--short", "HEAD")
    if not latest_tag or not head:
        return None
    ahead = _run_git(repo, "rev-list", "--count", f"{latest_tag}..HEAD")
    behind = _run_git(repo, "rev-list", "--count", f"HEAD..{latest_tag}")
    try:
        n_ahead = int(ahead or "0")
        n_behind = int(behind or "0")
    except ValueError:
        return None
    if n_ahead == 0 and n_behind == 0:
        return None
    if n_ahead and n_behind:
        return (
            f"editable scitex-dev: HEAD ({head}) diverged from latest tag "
            f"{latest_tag} (+{n_ahead}/−{n_behind}). `git pull --rebase`?"
        )
    if n_ahead:
        return (
            f"editable scitex-dev: HEAD ({head}) is {n_ahead} commit(s) "
            f"ahead of latest tag {latest_tag} — uncommitted release work."
        )
    return (
        f"editable scitex-dev: HEAD ({head}) is {n_behind} commit(s) behind "
        f"latest tag {latest_tag} — `git pull` or `pip install -U scitex-dev`."
    )


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
        return None
    head_mtime = _git_head_mtime(src)
    if head_mtime is None:
        return None
    cache = _read_cache()
    entry = cache.get(distribution, {})
    now = time.time()
    if (
        entry.get("head_mtime") == head_mtime
        and now - float(entry.get("checked_at", 0)) < 86400
    ):
        return entry.get("warning")
    if now - float(entry.get("checked_at", 0)) < _MIN_INTERVAL_SECONDS:
        # Avoid thrashing if HEAD is being rewritten in a tight loop.
        return entry.get("warning")
    warning = _compute_drift(src)
    cache[distribution] = {
        "head_mtime": head_mtime,
        "checked_at": now,
        "warning": warning,
    }
    _write_cache(cache)
    return warning


def emit_if_drift(distribution: str = "scitex-dev") -> None:
    """Print warning to stderr if there is one. Safe to call repeatedly
    (cache + once-per-process flag prevent duplicate noise)."""
    if getattr(emit_if_drift, "_emitted", False):
        return
    emit_if_drift._emitted = True  # type: ignore[attr-defined]
    msg = check(distribution)
    if msg:
        print(f"[scitex-dev] {msg}", file=sys.stderr)
