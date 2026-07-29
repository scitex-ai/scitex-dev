#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Target resolution for MUTATING ecosystem verbs.

A verb that WRITES must not resolve its target the way a verb that READS
does. A read that guesses wrong costs a session; a write that guesses
wrong modifies a repo nobody named, possibly on a protected branch, with
no diff shown first.

Measured 2026-07-29: `install-cross-package-gate`, run from inside
scitex-hpc's worktree, resolved via the ECOSYSTEM `~/proj/<name>` guess
and wrote into a DIFFERENT checkout sitting on `develop`, leaving it
modified — and printed the resolved path only AFTER the write. It also
computed 3 cross-package imports where that branch had 4: wrong tree in,
wrong content out. `install-audit-gate` shared the identical shape and
additionally appends to an existing `tests/conftest.py`.

The contract every mutating verb here must satisfy:

  1. An explicit ``--path`` exists, so a caller can aim it.
  2. Resolution is least-speculative-first, and a speculative source
     ANNOUNCES itself.
  3. The target is VERIFIED against the argument — a tree's own
     ``[project].name`` must equal the requested distribution. Refuse on
     mismatch, and refuse a tree that cannot identify itself.
  4. Target (and payload, where there is one) is printed BEFORE writing.
  5. The guard precedes ``--dry-run``, so it cannot be reached past.

Point 3 is the one that matters and is easy to get wrong: an earlier cut
of this fix merely PREFERRED the cwd repo, which "fixed" the reported
case by inventing a sibling — `install-cross-package-gate scitex-hpc`
run from scitex-dev's worktree computed SCITEX-DEV's imports and offered
to write them. Argument and target disagreed and nothing objected.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click


def enclosing_repo(start: Path) -> Path | None:
    """Return the git WORKTREE root containing *start*, or None.

    ``--show-toplevel`` resolves to the worktree root, so a caller standing
    in ``.worktrees/<topic>`` gets that worktree rather than the main
    checkout. That distinction is the point: the reporter was inside a
    worktree when the guess sent the write elsewhere.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return Path(out) if out else None


def resolve_write_target(
    distribution: str, explicit: str | None
) -> tuple[Path | None, str]:
    """Pick the tree to write into, preferring the LEAST speculative source.

    Order: ``--path`` (the caller said so) > the cwd's enclosing repo (the
    caller is standing in it) > the ECOSYSTEM ``~/proj/<name>`` guess. The
    guess is last and is announced by :func:`assert_target_is_distribution`,
    because it is the one that can silently name a tree nobody mentioned.
    """
    from ...._ecosystem import get_local_path

    if explicit:
        return Path(explicit).expanduser().resolve(), "--path"
    cwd_repo = enclosing_repo(Path.cwd())
    if cwd_repo is not None:
        return cwd_repo, "cwd repository"
    return get_local_path(distribution), "ECOSYSTEM registry guess (~/proj/<name>)"


def assert_target_is_distribution(
    target: Path, distribution: str, source: str
) -> None:
    """Announce the target, then REFUSE unless the tree IS *distribution*.

    Exits 2 on mismatch or on a tree with no readable ``[project].name``.
    Callers must invoke this BEFORE any write and before honouring
    ``--dry-run``.
    """
    from ...audit._project._check_umbrella_dep_and_integration import (
        _pyproject_distribution_name,
    )

    click.echo(f"target: {target}  (resolved via {source})", err=True)

    declared = _pyproject_distribution_name(target)
    if declared is None:
        click.echo(
            f"error: {target} has no readable [project].name in pyproject.toml, "
            f"so it cannot be confirmed to be '{distribution}'. Refusing to "
            "write into an unidentifiable tree.",
            err=True,
        )
        raise SystemExit(2)
    if declared != distribution:
        click.echo(
            f"error: refusing to write — the target tree is NOT "
            f"'{distribution}'.\n"
            f"  requested : {distribution}\n"
            f"  target    : {target}  (via {source})\n"
            f"  tree is   : {declared}  (its own [project].name)\n"
            "Run from inside the tree you mean to modify, or pass --path "
            "pointing at it. Distribution-name resolution guesses "
            "`~/proj/<name>`, which on a shared host is somebody else's "
            "checkout or the wrong commit of your own.",
            err=True,
        )
        raise SystemExit(2)


__all__ = [
    "assert_target_is_distribution",
    "enclosing_repo",
    "resolve_write_target",
]

# EOF
