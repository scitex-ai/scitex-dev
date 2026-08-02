#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Git-worktree staging for the diff-aware audit.

Split out of `._diff` because staging a baseline ref is a VCS concern,
not a parsing one: `._diff` turns audit output into comparable keys, and
this module produces the TREE that output is generated from. They share
no state and change for different reasons.

Re-exported from `._diff` so existing importers keep working.
"""

from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

__all__ = ["DiffAwareSetupError", "worktree_at"]


class DiffAwareSetupError(RuntimeError):
    """Raised when the base-ref worktree cannot be staged."""


@contextmanager
def worktree_at(repo: Path, ref: str) -> Iterator[Path]:
    """Stage ``ref`` as a temporary git worktree; yield its path.

    The caller's HEAD never moves — ``git worktree add`` clones the
    on-disk index of ``ref`` into a fresh dir under ``$TMPDIR``. On exit
    (success or failure) we always run ``git worktree remove --force``
    so the staging dir doesn't leak and the worktree registry stays
    clean.

    Raises ``DiffAwareSetupError`` on add failure (e.g. ref not found,
    locked worktree, dirty index) so the diff-aware caller can degrade
    gracefully (fall back to strict audit + a warning).
    """
    if not (repo / ".git").exists():
        raise DiffAwareSetupError(
            f"{repo} is not a git repository — diff-aware audit needs one."
        )
    stage = Path(tempfile.mkdtemp(prefix="audit-base-"))
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(stage), ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise DiffAwareSetupError(
                f"`git worktree add {ref}` failed (rc={r.returncode}): "
                f"{r.stderr.strip()}"
            )
        yield stage
    finally:
        # Best-effort teardown: --force survives a working tree with
        # local changes (the auditor occasionally writes pytest cache
        # files into the worktree). Worktree registry is reaped via
        # `prune` so a missed remove doesn't accumulate stubs.
        try:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(stage)],
                capture_output=True,
                check=False,
            )
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "prune"],
                capture_output=True,
                check=False,
            )


# EOF
