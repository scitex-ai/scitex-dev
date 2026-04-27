"""Dry-run gate via temporal lock file.

Systematic guard that rejects ``execute_rename`` unless a matching
``preview_rename`` (dry-run) has been conducted recently.

Lock storage hierarchy (most-specific wins):

    1. ``<project-root>/.scitex/dev/runtime/rename-locks/``
       Used when ``directory`` is inside a git repo — keeps locks
       co-located with the codebase they affect, so cross-project
       state never leaks.

    2. ``~/.scitex/dev/runtime/rename-locks/``
       Fallback when not in a git repo.

The lock key is the SHA1 of ``(pattern, replacement, abspath(root))``
plus the matching flag set (``regex``, ``word_boundary``). This means:

    - Running --dry-run for ``foo -> bar`` in repo A only authorises the
      execute for the SAME (pattern, replacement, root, flags) tuple.
    - Different flags (e.g. forgot ``-w``) → no match → execute blocked.
    - Different repo or different replacement → no match → blocked.

The TTL is short (default 10 min) so a forgotten lock from earlier in
the session doesn't authorise an unrelated execute. If the user
genuinely wants to bypass the gate (CI, scripted batch with own audit),
``--force`` skips both the uncommitted-changes check and the dry-run
gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .config import RenameConfig

# Honour the dry-run for this many seconds. Long enough to read the
# preview and decide; short enough that a stale lock from earlier in
# the day doesn't authorise an unrelated rename.
LOCK_TTL_SECONDS = 600  # 10 minutes


def _find_project_root(start: Path) -> Path | None:
    """Walk upward from ``start`` looking for a ``.git`` marker."""
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _lock_dir_for(directory: str) -> Path:
    """Return the rename-locks dir to use for renames rooted at ``directory``.

    Per-project under ``<root>/.scitex/dev/runtime/rename-locks/`` when
    inside a git repo; otherwise ``~/.scitex/dev/runtime/rename-locks/``.
    """
    root = _find_project_root(Path(directory))
    if root is not None:
        base = root / ".scitex" / "dev" / "runtime" / "rename-locks"
    else:
        base = Path.home() / ".scitex" / "dev" / "runtime" / "rename-locks"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _lock_key(config: RenameConfig) -> str:
    """Hash the rename signature (pattern, replacement, root, flags)."""
    parts = [
        config.pattern,
        config.replacement,
        os.path.abspath(config.directory),
        f"regex={int(config.regex)}",
        f"wb={int(config.word_boundary)}",
    ]
    digest = hashlib.sha1("\0".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def write_dry_run_lock(config: RenameConfig) -> Path:
    """Record that ``--dry-run`` was conducted for this rename signature.

    Called by ``preview_rename`` after a successful preview so the
    matching ``execute_rename`` can verify the user saw the change list.
    """
    path = _lock_dir_for(config.directory) / f"{_lock_key(config)}.json"
    path.write_text(
        json.dumps(
            {
                "pattern": config.pattern,
                "replacement": config.replacement,
                "directory": os.path.abspath(config.directory),
                "regex": config.regex,
                "word_boundary": config.word_boundary,
                "ts": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def find_recent_lock(config: RenameConfig) -> Path | None:
    """Return the lock path if a fresh dry-run record exists for this
    rename signature, else None."""
    path = _lock_dir_for(config.directory) / f"{_lock_key(config)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ts = data.get("ts")
    if not isinstance(ts, (int, float)):
        return None
    if time.time() - ts > LOCK_TTL_SECONDS:
        return None
    return path


def lock_path_hint(config: RenameConfig) -> str:
    """User-facing hint pointing at the expected lock file."""
    return str(_lock_dir_for(config.directory) / f"{_lock_key(config)}.json")
