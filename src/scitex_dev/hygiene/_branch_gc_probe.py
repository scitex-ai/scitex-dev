#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OBSERVATION for the branch GC — everything that touches the world.

Kept apart from the decision logic (:mod:`._branch_gc_predicate`) because
every function here can fail for reasons that have nothing to do with the
branch (git missing, ``gh`` unauthenticated, a non-GitHub remote), and each
one converts that failure into an honest ``None`` rather than a convenient
boolean. The predicate then only has to know how to KEEP on an unknown; it
never has to guess whether an answer is real.

NOTHING IN THIS PACKAGE TOUCHES A REMOTE. There is no ``git push
--delete``, no ``gh api -X DELETE``, no remote code path at all — the two
``gh`` calls here are READS. A remote deletion is the one act with no
local bundle to undo it, and ``delete_branch_on_merge`` already prunes
server-side at merge time anyway.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from ._branch_gc_model import BranchInfo

__all__ = [
    "PrLookup",
    "branch_sha",
    "commit_epoch",
    "gh_pr_merged",
    "gh_pr_open",
    "head_branch_names",
    "is_ancestor_of_base",
    "list_local_branches",
    "origin_head_branch",
    "patch_equivalent_to_base",
    "reflog_epoch",
    "run_git",
]

#: (repo, branch) -> True / False / None (unknown).
PrLookup = Callable[[Path, str], "bool | None"]


def run_git(
    cwd: str | Path, *args: str, timeout: int = 60, merge_stderr: bool = False
) -> tuple[bool, str]:
    """``git -C <cwd> <args>`` -> ``(ok, stdout-or-stderr)``. Never raises.

    Env drift (no git binary, an unreadable cwd, a hung git) degrades to
    ``(False, "<reason>")`` so every caller can route it to an UNKNOWN
    verdict instead of an exception. An unreadable repo must be a KEEP,
    not a traceback out of a scheduled pass.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        return False, f"git invocation failed ({type(exc).__name__}): {exc}"
    if res.returncode == 0:
        if merge_stderr:
            return True, "\n".join(
                part for part in (res.stdout.strip(), res.stderr.strip()) if part
            )
        return True, res.stdout.strip()
    return False, (res.stderr or res.stdout).strip()


def list_local_branches(repo: str | Path) -> tuple[bool, list[BranchInfo], str]:
    """Enumerate ``refs/heads/*`` -> ``(ok, infos, error)``.

    Scoped to ``refs/heads/`` by the ref pattern itself, which is what
    keeps tags, ``refs/remotes/``, ``refs/notes/``, ``refs/stash`` and
    ``refs/pull/`` structurally out of reach: they are never enumerated,
    so no later bug can reach them.

    ``ok=False`` means the path is not a readable git repo, and the caller
    reports UNKNOWN rather than assuming "no branches".
    """
    ok, out = run_git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)%09%(objectname)",
        "refs/heads/",
    )
    if not ok:
        return False, [], out
    infos: list[BranchInfo] = []
    for raw in out.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        name, _, sha = line.partition("\t")
        if name.strip():
            infos.append(BranchInfo(name=name.strip(), sha=sha.strip()))
    return True, infos, ""


def head_branch_names(repo: str | Path) -> set[str] | None:
    """Branches checked out in the main checkout OR any linked worktree.

    Parses ``git worktree list --porcelain``, which is authoritative: it
    reports every worktree registered to the repo wherever it lives on
    disk. ``None`` means the listing could not be read at all — an UNKNOWN
    that keeps every branch, never an empty set that keeps none.
    """
    ok, out = run_git(repo, "worktree", "list", "--porcelain")
    if not ok:
        return None
    names: set[str] = set()
    for raw in out.splitlines():
        key, _, value = raw.rstrip().partition(" ")
        if key == "branch" and value:
            names.add(value.replace("refs/heads/", "", 1))
    return names


def origin_head_branch(repo: str | Path) -> str | None:
    """Whatever ``refs/remotes/origin/HEAD`` resolves to, or None."""
    ok, out = run_git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if not ok or not out.strip():
        return None
    return out.strip().replace("refs/remotes/origin/", "", 1) or None


def branch_sha(repo: str | Path, branch: str) -> str | None:
    """Current SHA of ``refs/heads/<branch>``, or None if unreadable."""
    ok, out = run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    if not ok or not out.strip():
        return None
    return out.strip().splitlines()[0]


def _base_exists(repo: str | Path, base: str) -> bool:
    ok, _ = run_git(repo, "rev-parse", "--verify", "--quiet", base)
    return ok


def is_ancestor_of_base(
    repo: str | Path, branch: str, base: str
) -> tuple[bool | None, bool]:
    """``(landed, base_was_evaluated)`` for the ANCESTOR source.

    Local, free, and cannot lie — which is why it runs first. It is also
    blind to squash-merges by construction (a squash commit is a NEW
    commit, so the branch is not an ancestor of anything), and that
    blindness is precisely why it is one source of three rather than the
    predicate.
    """
    if not _base_exists(repo, base):
        return None, False
    ok, out = run_git(repo, "rev-list", "--count", f"{base}..{branch}")
    if not ok:
        return None, False
    return out.strip() == "0", True


def patch_equivalent_to_base(
    repo: str | Path, branch: str, base: str
) -> tuple[bool | None, bool]:
    """``(landed, base_was_evaluated)`` for the PATCH-EQUIVALENCE source.

    ``git cherry <base> <branch>`` marks each commit ``-`` when an
    equivalent patch already exists on the base and ``+`` when it does not.
    All-``-`` means every commit landed by some route git can recognise.

    HONEST LIMIT, stated because it is the reason the third source is not
    optional: this catches cherry-picks, rebase-landings and SINGLE-commit
    squashes. It does NOT catch a MULTI-commit squash — the squashed
    commit's patch equals the SUM of the members, not any individual
    member, so every member still reads as ``+``.
    """
    if not _base_exists(repo, base):
        return None, False
    ok, out = run_git(repo, "cherry", "-v", base, branch)
    if not ok:
        return None, False
    marks = [line[:1] for line in out.splitlines() if line[:1] in ("+", "-")]
    if not marks:
        # No commits ahead of the base at all. The ancestor source already
        # covers this shape; report it as landed rather than inventing a
        # disagreement between two sources looking at the same fact.
        return True, True
    return all(mark == "-" for mark in marks), True


def commit_epoch(repo: str | Path, ref: str) -> float | None:
    """Committer time of ``ref``'s tip, or None.

    COMMIT TIME, NOT DIRECTORY MTIME. An mtime moves when anything writes
    into the tree (a build, a linter, a stray editor swap file), so it
    answers "was this touched?" rather than "is this in flight?".
    """
    ok, out = run_git(repo, "log", "-1", "--format=%ct", ref)
    if not ok or not out.strip():
        return None
    try:
        return float(out.strip().splitlines()[0])
    except ValueError:
        return None


def reflog_epoch(repo: str | Path, ref: str) -> float | None:
    """When the ref was last MOVED IN THIS CLONE, or None.

    The second age signal, and the one that catches the shape the incident
    had: a branch created locally an hour ago off an ancient base has an
    old tip commit and a brand-new reflog entry. A ref with no reflog
    (expired, or fetched rather than created here) simply contributes
    nothing.
    """
    ok, out = run_git(repo, "reflog", "show", "--date=unix", "--format=%gd", ref)
    if not ok or not out.strip():
        return None
    first = out.strip().splitlines()[0]
    # Format is `<ref>@{<unix>}`; take what is between the braces.
    start = first.find("{")
    end = first.find("}", start + 1)
    if start == -1 or end == -1:
        return None
    try:
        return float(first[start + 1 : end])
    except ValueError:
        return None


def _gh_pr_count(repo: Path, branch: str, state: str) -> bool | None:
    if not branch:
        return None
    try:
        res = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                state,
                "--json",
                "number",
                "--limit",
                "1",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
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
    return bool(payload)


def gh_pr_merged(repo: Path, branch: str) -> bool | None:
    """Does ``branch`` have a MERGED PR? True / False / None (unknown).

    The squash-merge half of the landed leg. Returns ``None`` — never
    ``False`` — on ANY doubt: gh missing, unauthenticated, offline, not a
    GitHub remote, rate-limited, or any other non-zero exit. That
    distinction is the point. ``False`` means "GitHub answered: no merged
    PR", which (paired with a base we actually read) licenses a definite
    NOT-LANDED. ``None`` means nobody answered, which keeps the branch.
    """
    return _gh_pr_count(repo, branch, "merged")


def gh_pr_open(repo: Path, branch: str) -> bool | None:
    """Does ``branch`` have an OPEN PR? True / False / None (unknown).

    ``None`` keeps the branch, matching the conservative behaviour the
    existing ``_prune_merged._has_open_pr`` already chose (it returns True
    on any gh failure, for the same reason and to the same effect).
    """
    return _gh_pr_count(repo, branch, "open")


# EOF
