#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OBSERVATION — every call that touches git, GitHub or the filesystem.

Kept apart from :mod:`._decide` because each of these can fail for
reasons that have nothing to do with the branch (no git, ``gh``
unauthenticated, a non-GitHub remote, an unreadable worktree), and every
one of them converts that into an honest ``None`` rather than a
convenient boolean. The decision layer then only has to know how to keep
on an unknown; it never has to guess whether an answer is real.

``run_git`` and ``reflog_epoch`` are imported from
:mod:`scitex_dev.hygiene._branch_gc_probe` rather than rewritten. They
are the same two primitives, already tested there, and a second copy is
a second thing to keep in agreement.

BATCHED BY REPOSITORY, NOT BY BRANCH
------------------------------------
The pull-request questions are asked ONCE per repository — one ``gh``
call for the open heads and one for the merged heads — rather than twice
per branch. On the measured fleet (roughly 180 repositories, several
hundred branches each pass) the per-branch shape is tens of thousands of
API calls a day for an answer that a single listing already contains.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..hygiene._branch_gc_probe import reflog_epoch, run_git

__all__ = [
    "current_branch",
    "delete_local_branch",
    "delete_remote_branch",
    "fetch_prune",
    "head_sha",
    "is_dirty",
    "list_local_rows",
    "list_remote_rows",
    "merged_names",
    "pr_heads",
    "prune_worktrees",
    "reflog_epoch",
    "run_git",
    "status_entries",
    "switch_to",
    "worktree_map",
    "worktree_remove",
    "worktree_touch_epoch",
]

#: ``--limit`` for the pull-request listings. Above the largest repository
#: measured on the fleet, so a truncated page cannot silently turn a
#: "has an open PR" into a "no open PR" — the one confusion that deletes
#: reviewed work.
PR_LIST_LIMIT = 1_000

#: Directories never walked when dating a worktree's files. ``.git`` is
#: rewritten by git itself, so including it dates every worktree as
#: "touched just now" and no worktree is ever collectable.
UNDATED_DIRS = frozenset({".git"})

_ROW_FORMAT = "%(refname:short)%09%(objectname)%09%(committerdate:unix)"


def _rows(out: str) -> list[tuple[str, str, float | None]]:
    parsed: list[tuple[str, str, float | None]] = []
    for raw in out.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        name, sha = parts[0].strip(), parts[1].strip()
        stamp: float | None = None
        if len(parts) > 2 and parts[2].strip():
            try:
                stamp = float(parts[2].strip())
            except ValueError:
                stamp = None
        parsed.append((name, sha, stamp))
    return parsed


def list_local_rows(repo: str | Path) -> tuple[bool, list[tuple[str, str, float | None]], str]:
    """``refs/heads/*`` as ``(name, sha, committer-epoch)``.

    Scoped by the ref pattern itself, which is what keeps tags,
    ``refs/remotes/``, ``refs/notes/`` and ``refs/stash`` structurally
    out of reach — they are never enumerated, so no later bug can delete
    one. ``ok=False`` means the path is not a readable repository, and
    the caller reports that rather than assuming "no branches".
    """
    ok, out = run_git(repo, "for-each-ref", f"--format={_ROW_FORMAT}", "refs/heads/")
    if not ok:
        return False, [], out
    return True, _rows(out), ""


def list_remote_rows(
    repo: str | Path, *, remote: str = "origin"
) -> tuple[bool, list[tuple[str, str, float | None]], str]:
    """Remote-tracking refs as ``(short-name, sha, committer-epoch)``.

    Names are returned WITHOUT the ``<remote>/`` prefix so they can be
    compared with pull-request head names and pushed as delete refspecs
    directly. ``<remote>/HEAD`` is dropped: it is a symbolic pointer, not
    a branch, and pushing a delete for it is meaningless.
    """
    ok, out = run_git(
        repo, "for-each-ref", f"--format={_ROW_FORMAT}", f"refs/remotes/{remote}/"
    )
    if not ok:
        return False, [], out
    prefix = f"{remote}/"
    rows: list[tuple[str, str, float | None]] = []
    for name, sha, stamp in _rows(out):
        short = name[len(prefix) :] if name.startswith(prefix) else name
        if not short or short == "HEAD":
            continue
        rows.append((short, sha, stamp))
    return True, rows, ""


def fetch_prune(repo: str | Path, *, remote: str = "origin") -> tuple[bool, str]:
    """Refresh remote-tracking refs and drop the ones origin no longer has.

    Read-only against the remote, and it must run before the remote leg:
    a stale tracking ref names a branch that was deleted days ago, and
    pushing a delete for it fails for a reason that has nothing to do
    with this sweep.
    """
    return run_git(repo, "fetch", "--prune", remote, timeout=120)


def current_branch(repo: str | Path) -> str:
    """The primary checkout's branch, or ``""`` when detached."""
    ok, out = run_git(repo, "branch", "--show-current")
    return out.strip() if ok else ""


def head_sha(repo: str | Path, ref: str) -> str | None:
    """``ref``'s current object, or ``None`` when it does not resolve."""
    ok, out = run_git(repo, "rev-parse", "--verify", "--quiet", ref)
    if not ok or not out.strip():
        return None
    return out.strip().splitlines()[0]


def is_dirty(path: str | Path) -> bool | None:
    """Does this tree carry uncommitted work? ``None`` when unreadable.

    UNTRACKED FILES COUNT. ``git worktree remove`` refuses on them, so a
    definition that ignored them would predict "clean, removable" for a
    tree git is about to refuse — and the prediction, not the refusal,
    is what the force decision is made from.
    """
    ok, out = run_git(path, "status", "--porcelain")
    if not ok:
        return None
    return bool(out.strip())


def status_entries(path: str | Path) -> tuple[str, ...]:
    """The porcelain lines a forced removal would discard."""
    ok, out = run_git(path, "status", "--porcelain")
    if not ok:
        return ()
    return tuple(line for line in out.splitlines() if line.strip())


def worktree_map(repo: str | Path) -> dict[str, tuple[str, bool]] | None:
    """``branch -> (worktree path, is-primary)``, or ``None`` if unread.

    ``git worktree list --porcelain`` reports the primary checkout FIRST
    and every linked worktree after it, wherever on disk they live. The
    primary is flagged because it is the one tree this sweep may never
    remove — removing it would delete the repository.
    """
    ok, out = run_git(repo, "worktree", "list", "--porcelain")
    if not ok:
        return None
    mapping: dict[str, tuple[str, bool]] = {}
    path = ""
    index = -1
    for raw in out.splitlines():
        key, _, value = raw.rstrip().partition(" ")
        if key == "worktree":
            path = value
            index += 1
            continue
        if key == "branch" and value and path:
            name = value.replace("refs/heads/", "", 1)
            mapping[name] = (path, index == 0)
    return mapping


def worktree_touch_epoch(path: str | Path) -> float | None:
    """Newest file mtime under ``path``, ignoring ``.git``.

    THE INSTRUMENT FOR UNCOMMITTED WORK. The branch's committer date
    cannot see an edit that was never committed, so a tree whose files
    were changed an hour ago reads as ancient by that measure — and
    under a rule that forces removal of "untouched" trees, an hour-old
    edit is exactly what gets destroyed. This asks the files instead.

    ``None`` when nothing could be stat'ed at all, which keeps the tree.
    """
    root = Path(path)
    if not root.is_dir():
        return None
    newest: float | None = None
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in UNDATED_DIRS]
            for name in filenames:
                try:
                    stamp = (Path(dirpath) / name).lstat().st_mtime
                except OSError:
                    continue
                if newest is None or stamp > newest:
                    newest = stamp
    except OSError:
        return newest
    return newest


def _gh_heads(repo: str | Path, state: str) -> set[str] | None:
    """Head branch names of ``state`` PRs, or ``None`` on ANY doubt."""
    try:
        res = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                state,
                "--json",
                "headRefName",
                "--limit",
                str(PR_LIST_LIMIT),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    try:
        payload = json.loads(res.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return {
        row.get("headRefName", "")
        for row in payload
        if isinstance(row, dict) and row.get("headRefName")
    }


def pr_heads(repo: str | Path, state: str) -> set[str] | None:
    """Every head branch with a ``state`` pull request. ``None`` = unknown.

    ``None`` — never an empty set — on gh missing, unauthenticated,
    offline, rate-limited, a non-GitHub remote, or any non-zero exit.
    An empty set says "GitHub answered: none"; ``None`` says nobody
    answered, and those license opposite actions.
    """
    return _gh_heads(repo, state)


def merged_names(
    repo: str | Path, base: str, *, pattern: str = "refs/heads/"
) -> set[str] | None:
    """Branches whose tip is an ANCESTOR of ``base``. ``None`` if no base.

    One call for the whole repository. Blind to squash merges by
    construction — a squash commit is a new commit, so its source branch
    is nobody's ancestor — which is why the caller unions this with the
    MERGED-PR head set. Neither source alone is sufficient and the
    union's failure mode is a missed drop, not a wrong one.
    """
    if head_sha(repo, base) is None:
        return None
    ok, out = run_git(
        repo, "for-each-ref", "--merged", base, "--format=%(refname:short)", pattern
    )
    if not ok:
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def switch_to(repo: str | Path, branch: str) -> tuple[bool, str]:
    """``git checkout <branch>``. Never forced, never with a stash."""
    return run_git(repo, "checkout", branch)


def worktree_remove(
    repo: str | Path, path: str, *, force: bool = False
) -> tuple[bool, str]:
    """``git worktree remove [--force] <path>``.

    WITHOUT ``--force`` the refusal IS the check, and a better one than
    "is it a worktree at all": it fires on uncommitted work — the
    property worth protecting — rather than on mere existence. ``force``
    is passed only for a tree whose FILES have gone untouched past the
    window, and every such call is named in the report.
    """
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(path))
    return run_git(repo, *args, timeout=120)


def prune_worktrees(repo: str | Path, *, dry_run: bool = False) -> str:
    """Drop administrative records for directories that are already gone.

    A stale registration reports a branch as "in use by a worktree" when
    no worktree exists, so without this the sweep keeps refusing to
    collect branches nothing is holding.
    """
    args = ["worktree", "prune", "--verbose"]
    if dry_run:
        args.append("--dry-run")
    ok, out = run_git(repo, *args, merge_stderr=True)
    return out if ok else f"prune failed: {out}"


def delete_local_branch(repo: str | Path, branch: str) -> tuple[bool, str]:
    """``git branch -D <branch>``.

    ``-D`` rather than ``-d`` because this sweep deliberately collects
    branches that never landed. Git's own "checked out in a worktree"
    refusal still applies to ``-D``, and it is kept as the backstop
    behind this module's own worktree accounting.
    """
    return run_git(repo, "branch", "-D", branch)


def delete_remote_branch(
    repo: str | Path, branch: str, *, remote: str = "origin"
) -> tuple[bool, str]:
    """``git push <remote> --delete <branch>``."""
    return run_git(repo, "push", remote, "--delete", branch, timeout=120)


# EOF
