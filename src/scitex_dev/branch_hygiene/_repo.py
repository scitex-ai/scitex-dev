#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One repository, swept: checkout to develop, then branches, then prune.

DRY RUN IS THE DEFAULT AND ``execute`` IS THE OPT-IN. Both of the two
worst rules this sweep has ever carried — a pattern that would have
erased every contributor signature in 36 repositories, and its repair
that swallowed the agent branches it was meant to collect — were caught
by a rehearsal, not by review. A verb that deletes several hundred
branches across seven hosts on its first invocation with no way to see
the plan is a footgun however correct its rules are.

THE THREE LEGS, AND WHY THEY ARE IN THIS ORDER
----------------------------------------------
1. Put the checkout on ``develop``, refusing a dirty tree.
2. Collect local branches, removing the worktrees that hold finished
   ones.
3. Prune the administrative records the removals left behind.

Leg 1 runs first because a branch that is the primary checkout's HEAD
can never be collected; moving the checkout to ``develop`` is what makes
yesterday's topic branch collectable at all. Leg 3 runs last because a
stale registration reports "in use by a worktree" for a directory that
no longer exists, and that answer keeps branches nothing is holding.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from ..hygiene._branch_gc_backup import create_backup
from ..hygiene._branch_gc_model import BranchInfo
from . import _probe
from ._decide import decide, decide_remote
from ._model import (
    DEFAULT_MAX_AGE_HOURS,
    KEEP_MOVED,
    KEEP_WORKTREE_REFUSED,
    PROTECTED_EXACT,
    WT_REMOVE,
    WT_REMOVE_FORCE,
    BranchFacts,
    BranchVerdict,
    CheckoutResult,
    Discarded,
    RepoResult,
)

DEVELOP = "develop"

#: ``(repo, state) -> {head branch names}`` or ``None`` when nobody
#: answered. Injectable for the same reason :mod:`scitex_dev.hygiene`
#: injects its own ``pr_merged`` / ``pr_open``: the tests build REAL
#: repositories with no GitHub remote, so the honest live answer there
#: is ``None`` for every branch, which keeps everything and would leave
#: the delete path untested. The seam is on the OBSERVATION, never on
#: the decision function under test.
HeadLookup = Callable[..., "set[str] | None"]


def align_checkout(
    repo: Path, *, package: str = "", execute: bool = False, branch: str = DEVELOP
) -> CheckoutResult:
    """Put ``repo``'s primary checkout on ``branch``, or say why not.

    A DIRTY TREE IS REPORTED AND SKIPPED. Never stashed, never forced:
    both of those move somebody's uncommitted work somewhere they did
    not put it, and this job runs unattended once a day.
    """
    row = {"package": package, "repo": str(repo)}
    if not (repo / ".git").exists():
        return CheckoutResult(**row, action="missing", detail=str(repo))
    current = _probe.current_branch(repo)
    if current == branch:
        return CheckoutResult(**row, action="on-develop")
    dirty = _probe.is_dirty(repo)
    if dirty is None:
        return CheckoutResult(**row, action="failed", detail="cannot read status")
    if dirty:
        return CheckoutResult(
            **row,
            action="dirty",
            detail=f"on {current or '(detached)'}, uncommitted changes",
        )
    if _probe.head_sha(repo, f"refs/heads/{branch}") is None:
        return CheckoutResult(**row, action="no-develop", detail=f"no {branch} branch")
    if not execute:
        return CheckoutResult(
            **row, action="would-switch", detail=f"from {current or '(detached)'}"
        )
    ok, detail = _probe.switch_to(repo, branch)
    if not ok:
        return CheckoutResult(**row, action="failed", detail=detail)
    return CheckoutResult(**row, action="switched", detail=f"from {current}")


def _merged_set(
    repo: Path, base: str, pattern: str, *, pr_heads: HeadLookup
) -> set[str] | None:
    """Ancestry-merged branches, unioned with MERGED-PR heads.

    Two sources because neither is sufficient. Ancestry is local, free
    and cannot lie, and is blind to every squash merge. The pull-request
    listing sees squashes and needs GitHub to answer. When only one of
    them answers, the union is that one; when neither does, the answer
    is ``None`` and the age rule decides alone.
    """
    ancestry = _probe.merged_names(repo, base, pattern=pattern)
    merged_prs = pr_heads(repo, "merged")
    if ancestry is None and merged_prs is None:
        return None
    return set(ancestry or set()) | set(merged_prs or set())


def _facts_for_local(
    repo: Path,
    rows: list[tuple[str, str, float | None]],
    *,
    open_heads: set[str] | None,
    merged: set[str] | None,
    worktrees: dict[str, tuple[str, bool]] | None,
) -> list[BranchFacts]:
    facts: list[BranchFacts] = []
    for name, sha, stamp in rows:
        held = (worktrees or {}).get(name)
        path = held[0] if held else None
        dirty = _probe.is_dirty(path) if path else None
        touch = _probe.worktree_touch_epoch(path) if path and dirty else None
        facts.append(
            BranchFacts(
                name=name,
                sha=sha,
                last_commit_epoch=stamp,
                last_move_epoch=_probe.reflog_epoch(repo, name),
                merged=None if merged is None else name in merged,
                has_open_pr=None if open_heads is None else name in open_heads,
                worktree_path=path,
                worktree_is_primary=bool(held and held[1]),
                worktree_dirty=dirty if path else None,
                worktree_touch_epoch=touch,
            )
        )
    return facts


def _clear_worktree(
    repo: Path, verdict: BranchVerdict
) -> tuple[BranchVerdict, Discarded | None]:
    """Remove the worktree holding a finished branch, or refuse to.

    ``git worktree remove`` without ``--force`` is the safety net, and a
    precise one: it fires on uncommitted work rather than on the mere
    existence of a tree. ``--force`` is reached only when the decision
    layer has already established that the tree's FILES have gone
    untouched past the window, and the entries it discards are captured
    BEFORE the removal so the report can name them afterwards.
    """
    path = verdict.worktree_path
    if not path:
        return verdict, None
    force = verdict.worktree_action == WT_REMOVE_FORCE
    entries = _probe.status_entries(path) if force else ()
    ok, detail = _probe.worktree_remove(repo, path, force=force)
    if not ok:
        blocked = BranchVerdict(
            name=verdict.name,
            sha=verdict.sha,
            drop=False,
            reason=KEEP_WORKTREE_REFUSED,
            worktree_path=path,
            worktree_action=verdict.worktree_action,
            error=detail,
        )
        return blocked, None
    record = Discarded(branch=verdict.name, path=path, entries=entries) if force else None
    return verdict, record


def _delete_local(repo: Path, verdict: BranchVerdict) -> BranchVerdict:
    """Re-confirm the SHA, then delete. Never delete what has moved."""
    if _probe.head_sha(repo, f"refs/heads/{verdict.name}") != verdict.sha:
        return BranchVerdict(
            name=verdict.name,
            sha=verdict.sha,
            drop=False,
            reason=KEEP_MOVED,
            worktree_path=verdict.worktree_path,
        )
    ok, detail = _probe.delete_local_branch(repo, verdict.name)
    if not ok:
        return BranchVerdict(
            name=verdict.name,
            sha=verdict.sha,
            drop=True,
            reason=verdict.reason,
            worktree_path=verdict.worktree_path,
            worktree_action=verdict.worktree_action,
            error=detail,
        )
    return BranchVerdict(
        name=verdict.name,
        sha=verdict.sha,
        drop=True,
        reason=verdict.reason,
        worktree_path=verdict.worktree_path,
        worktree_action=verdict.worktree_action,
        executed=True,
    )


def sweep_local(
    repo: Path,
    *,
    execute: bool = False,
    now: float | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
    pr_heads: HeadLookup = _probe.pr_heads,
) -> tuple[tuple[BranchVerdict, ...], tuple[Discarded, ...], str, str]:
    """``(verdicts, discarded, backup restore command, error)``.

    A verified git bundle of every branch about to go is written first,
    and if it cannot be verified NOTHING is deleted. That is cheap
    insurance for the leg that removes work which never landed anywhere.
    """
    moment = time.time() if now is None else now
    ok, rows, error = _probe.list_local_rows(repo)
    if not ok:
        return (), (), "", error
    facts = _facts_for_local(
        repo,
        rows,
        open_heads=pr_heads(repo, "open"),
        merged=_merged_set(repo, DEVELOP, "refs/heads/", pr_heads=pr_heads),
        worktrees=_probe.worktree_map(repo),
    )
    planned = [
        decide(f, now=moment, max_age_hours=max_age_hours, protected=protected)
        for f in facts
    ]
    if not execute:
        return tuple(planned), (), "", ""

    doomed = [v for v in planned if v.drop]
    restore = ""
    if doomed:
        backup = create_backup(
            repo, [BranchInfo(name=v.name, sha=v.sha) for v in doomed]
        )
        if not backup.ok:
            return tuple(planned), (), "", f"backup refused: {backup.error}"
        restore = backup.restore_command

    final: list[BranchVerdict] = []
    discarded: list[Discarded] = []
    for verdict in planned:
        if not verdict.drop:
            final.append(verdict)
            continue
        cleared, record = _clear_worktree(repo, verdict)
        if record is not None:
            discarded.append(record)
        if not cleared.drop:
            final.append(cleared)
            continue
        final.append(_delete_local(repo, cleared))
    return tuple(final), tuple(discarded), restore, ""


def sweep_remote(
    repo: Path,
    *,
    execute: bool = False,
    now: float | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
    remote: str = "origin",
    pr_heads: HeadLookup = _probe.pr_heads,
) -> tuple[tuple[BranchVerdict, ...], str]:
    """``(verdicts, error)`` for ``<remote>``'s branches.

    RUN ONCE FOR THE FLEET, never once per host. A remote ref is shared:
    seven hosts sweeping it is seven times the API calls for one effect,
    and six of those passes find the branch already gone and report a
    failure for it.
    """
    moment = time.time() if now is None else now
    _probe.fetch_prune(repo, remote=remote)
    ok, rows, error = _probe.list_remote_rows(repo, remote=remote)
    if not ok:
        return (), error
    open_heads = pr_heads(repo, "open")
    merged = _merged_set(
        repo,
        f"refs/remotes/{remote}/{DEVELOP}",
        f"refs/remotes/{remote}/",
        pr_heads=pr_heads,
    )
    prefix = f"{remote}/"
    merged_short = (
        None
        if merged is None
        else {n[len(prefix) :] if n.startswith(prefix) else n for n in merged}
    )
    verdicts: list[BranchVerdict] = []
    for name, sha, stamp in rows:
        facts = BranchFacts(
            name=name,
            sha=sha,
            last_commit_epoch=stamp,
            merged=None if merged_short is None else name in merged_short,
            has_open_pr=None if open_heads is None else name in open_heads,
        )
        verdict = decide_remote(
            facts, now=moment, max_age_hours=max_age_hours, protected=protected
        )
        if not (execute and verdict.drop):
            verdicts.append(verdict)
            continue
        pushed, detail = _probe.delete_remote_branch(repo, name, remote=remote)
        verdicts.append(
            BranchVerdict(
                name=name,
                sha=sha,
                drop=True,
                reason=verdict.reason,
                executed=pushed,
                error="" if pushed else detail,
            )
        )
    return tuple(verdicts), ""


def sweep_repo(
    repo: str | Path,
    *,
    package: str = "",
    execute: bool = False,
    do_local: bool = True,
    do_remote: bool = False,
    now: float | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
    pr_heads: HeadLookup = _probe.pr_heads,
) -> RepoResult:
    """The whole pass for one repository.

    The two legs are independent flags rather than one mode because the
    fleet runs them on different populations: the LOCAL leg on every
    host (each machine has its own checkouts), the REMOTE leg on exactly
    one (origin has one set of refs).
    """
    path = Path(repo)
    if not (path / ".git").exists():
        return RepoResult(
            package=package,
            repo=str(path),
            checkout=CheckoutResult(
                package=package, repo=str(path), action="missing", detail=str(path)
            ),
            error="not a repository",
        )
    checkout = CheckoutResult(package=package, repo=str(path), action="skipped")
    local: tuple[BranchVerdict, ...] = ()
    discarded: tuple[Discarded, ...] = ()
    restore = ""
    error = ""
    prune = ""
    if do_local:
        checkout = align_checkout(path, package=package, execute=execute)
        local, discarded, restore, error = sweep_local(
            path,
            execute=execute,
            now=now,
            max_age_hours=max_age_hours,
            protected=protected,
            pr_heads=pr_heads,
        )
        prune = _probe.prune_worktrees(path, dry_run=not execute)
    remote: tuple[BranchVerdict, ...] = ()
    remote_error = ""
    if do_remote:
        remote, remote_error = sweep_remote(
            path,
            execute=execute,
            now=now,
            max_age_hours=max_age_hours,
            protected=protected,
            pr_heads=pr_heads,
        )
    return RepoResult(
        package=package,
        repo=str(path),
        checkout=checkout,
        local=local,
        remote=remote,
        discarded=discarded,
        backup_restore=restore,
        prune=prune,
        error=error or remote_error,
    )


# EOF
