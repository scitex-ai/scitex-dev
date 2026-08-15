#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The branch-GC engine. Reports by default; deletes only under four OFFs.

FOUR INDEPENDENT GATES STAND BETWEEN THIS MODULE AND A DELETION
---------------------------------------------------------------
1. ``CleanupConfig.enabled`` defaults ``False`` at the dataclass level.
2. The loader FAILS CLOSED — any doubt about the config yields OFF.
3. ``apply`` defaults ``False`` here, independent of config: config-on
   still only reports until an explicit opt-in.
4. The cron job is inert until an operator runs ``cron install branch-gc``.

Four OFFs in series. Any one of them being wrong still leaves three.

WHAT IT DELETES
---------------
Local ``refs/heads/*`` refs, and nothing else. No remote leg exists — not
a flag, not a code path. No tags. Nothing elsewhere in ``refs/``. No
worktree directory, no working-tree file, no stash, no reflog. The engine
runs exactly one additional mutation, ``git worktree prune``, which only
drops administrative records whose directory is ALREADY GONE and so
destroys no files by construction.

DELETE MECHANICS
----------------
``git branch -d`` first — never ``-D``. Git's own refusal is a second,
independent implementation of the landed leg, written by people better at
this than we are, and ``-D`` would disable the only check we did not
write ourselves.

``-d`` understands ANCESTRY only, so it refuses a squash-merge and a
rebase-landing even when the work demonstrably landed. For exactly those
cases — and only when leg 1 proved landing by a PATCH-LEVEL source — we
fall back to::

    git update-ref -d refs/heads/<branch> <sha-from-the-manifest>

which is a compare-and-delete: git refuses if the ref no longer points at
that SHA. Strictly safer than ``-D``, and it is what makes this primitive
useful in a squash-merging repo instead of inert.
"""

from __future__ import annotations

import time
from pathlib import Path

from ._branch_gc_active import ActiveRefs, card_active_tokens
from ._branch_gc_backup import BackupResult, create_backup, sha_still_matches
from ._branch_gc_config import CleanupConfig, load_branch_cleanup_config
from ._branch_gc_model import (
    DEFAULT_BRANCH_CAP,
    KEEP_DEFERRED_BY_LIMIT,
    KEEP_DELETE_FAILED,
    KEEP_MOVED_DURING_PASS,
    SHA_DELETABLE_LANDED_SOURCES,
    BranchGcOutcome,
    BranchVerdict,
    RepoBranchGcResult,
)
from ._branch_gc_predicate import verdict_for
from ._branch_gc_probe import (
    PrLookup,
    gh_pr_merged,
    gh_pr_open,
    head_branch_names,
    list_local_branches,
    origin_head_branch,
    run_git,
)

__all__ = ["gc_repo", "gc_repos"]

#: Stated once, used twice: the abort messages an operator will read in a
#: cron log at 3am, so they say what to DO, not merely what happened.
_ABORT_NO_ACTIVE_SIGNAL = (
    "active-work signal UNAVAILABLE (scitex-cards unreadable) — refusing to "
    "delete: if the fleet's in-flight work cannot be seen, no branch can be "
    "proven not to be its substrate"
)


def gc_repo(
    repo: str | Path,
    *,
    apply: bool = False,
    config: CleanupConfig | None = None,
    home: str | Path | None = None,
    cap: int = DEFAULT_BRANCH_CAP,
    max_delete: int | None = None,
    now: float | None = None,
    pr_merged: PrLookup = gh_pr_merged,
    pr_open: PrLookup = gh_pr_open,
    active_refs: ActiveRefs = card_active_tokens,
) -> RepoBranchGcResult:
    """GC one repo's local branches. Reports by default; mutates only on ``apply``.

    ``config=None`` resolves the repo's own ``cleanup.branches`` block via
    :func:`._branch_gc_config.load_branch_cleanup_config` — which is OFF
    unless BOTH the per-repo and the user-scope config say literally
    ``true``.

    An unreadable repo returns a result carrying ``error`` (UNKNOWN),
    never an empty verdict list: "I could not read this repo" must not
    render as "this repo has no branches".
    """
    now = time.time() if now is None else now
    cfg = config if config is not None else load_branch_cleanup_config(repo, home=home)
    base = RepoBranchGcResult(
        repo=str(repo),
        enabled=cfg.enabled,
        applied=False,
        cap=cap,
        min_age_days=cfg.min_age_days,
        config_source=cfg.repo_source,
        config_error=cfg.error,
    )

    ok, infos, err = list_local_branches(repo)
    if not ok:
        return _replace(base, error=err)

    heads = head_branch_names(repo)
    tokens = _read_active(active_refs)
    # Whatever origin/HEAD resolves to is protected even when it is not one
    # of the built-in names — a repo whose default branch is `trunk` must
    # not be protected only by the coincidence of its name.
    globs = cfg.protect
    default_branch = origin_head_branch(repo)
    if default_branch:
        globs = tuple(globs) + (default_branch,)

    verdicts = [
        verdict_for(
            repo,
            info,
            min_age_days=cfg.min_age_days,
            now=now,
            pr_merged=pr_merged,
            pr_open=pr_open,
            heads=heads,
            active_tokens=tokens,
            extra_globs=globs,
        )
        for info in infos
    ]
    verdicts.sort(key=lambda verdict: verdict.name)

    # ---- Every route to "delete nothing", each one NAMED -----------------
    if tokens is None:
        return _replace(
            base, verdicts=tuple(verdicts), abort_reason=_ABORT_NO_ACTIVE_SIGNAL
        )
    if not cfg.enabled:
        return _replace(base, verdicts=tuple(verdicts))
    if not apply:
        return _replace(base, verdicts=tuple(verdicts))

    candidates = [verdict for verdict in verdicts if verdict.deletable]
    if max_delete is not None and len(candidates) > max_delete:
        # NO SILENT CAPS. The deferred branches stay in the report carrying
        # an explicit reason, so a bounded pass never reads as a complete one.
        deferred = {verdict.name for verdict in candidates[max_delete:]}
        candidates = candidates[:max_delete]
        verdicts = [
            verdict.with_reason(KEEP_DEFERRED_BY_LIMIT)
            if verdict.name in deferred
            else verdict
            for verdict in verdicts
        ]
    if not candidates:
        applied = _replace(base, verdicts=tuple(verdicts), applied=True)
        return _replace(applied, prune_detail=_prune(repo, apply=True))

    backup = create_backup(
        repo,
        [_as_info(verdict) for verdict in candidates],
        config_snapshot={
            "enabled": cfg.enabled,
            "min_age_days": cfg.min_age_days,
            "protect": list(cfg.protect),
            "repo_source": cfg.repo_source,
            "user_source": cfg.user_source,
        },
        keep_report=_keep_report(verdicts, candidates),
    )
    if not backup.ok:
        return _replace(
            base,
            verdicts=tuple(verdicts),
            backup_dir=backup.directory,
            abort_reason=f"backup failed, deleted nothing: {backup.error}",
        )

    verdicts = _delete_all(repo, verdicts, candidates, backup)
    return RepoBranchGcResult(
        repo=str(repo),
        enabled=cfg.enabled,
        applied=True,
        cap=cap,
        min_age_days=cfg.min_age_days,
        verdicts=tuple(verdicts),
        config_source=cfg.repo_source,
        config_error=cfg.error,
        backup_dir=backup.directory,
        bundle_path=backup.bundle_path,
        restore_command=backup.restore_command,
        prune_detail=_prune(repo, apply=True),
    )


def _read_active(active_refs: ActiveRefs) -> set[str] | None:
    try:
        return active_refs()
    except Exception:  # noqa: BLE001 - a raising seam is UNAVAILABLE, not empty
        return None


def _as_info(verdict: BranchVerdict):
    from ._branch_gc_model import BranchInfo

    return BranchInfo(name=verdict.name, sha=verdict.sha)


def _keep_report(
    verdicts: list[BranchVerdict], candidates: list[BranchVerdict]
) -> dict:
    chosen = {verdict.name for verdict in candidates}
    return {
        verdict.name: list(verdict.keep_reasons)
        for verdict in verdicts
        if verdict.name not in chosen
    }


def _delete_all(
    repo: str | Path,
    verdicts: list[BranchVerdict],
    candidates: list[BranchVerdict],
    backup: BackupResult,
) -> list[BranchVerdict]:
    """Delete each candidate, re-confirming its SHA immediately beforehand."""
    outcomes: dict[str, BranchVerdict] = {}
    for verdict in candidates:
        expected = backup.shas.get(verdict.name, "")
        if not sha_still_matches(repo, verdict.name, expected):
            outcomes[verdict.name] = verdict.with_reason(KEEP_MOVED_DURING_PASS)
            continue
        outcomes[verdict.name] = _delete_one(repo, verdict, expected)
    return [outcomes.get(verdict.name, verdict) for verdict in verdicts]


def _delete_one(
    repo: str | Path, verdict: BranchVerdict, expected_sha: str
) -> BranchVerdict:
    """``git branch -d``, with a compare-and-delete fallback. Never ``-D``."""
    ok, detail = run_git(repo, "branch", "-d", verdict.name)
    if ok:
        return _deleted(verdict)
    if verdict.landed_source in SHA_DELETABLE_LANDED_SOURCES:
        ok, detail = run_git(
            repo, "update-ref", "-d", f"refs/heads/{verdict.name}", expected_sha
        )
        if ok:
            return _deleted(verdict)
    return BranchVerdict(
        name=verdict.name,
        sha=verdict.sha,
        keep_reasons=verdict.keep_reasons + (KEEP_DELETE_FAILED,),
        landed_source=verdict.landed_source,
        deleted=False,
        delete_error=detail,
    )


def _deleted(verdict: BranchVerdict) -> BranchVerdict:
    return BranchVerdict(
        name=verdict.name,
        sha=verdict.sha,
        keep_reasons=(),
        landed_source=verdict.landed_source,
        deleted=True,
    )


def _prune(repo: str | Path, *, apply: bool) -> str:
    """``git worktree prune`` — unconditionally safe, so it needs no predicate.

    It only drops administrative records whose directory is already gone.
    ``--verbose`` is not decoration: without it prune prints NOTHING, so the
    pass would claim a prune it cannot evidence. ``merge_stderr`` because
    git writes that report to stderr even on success.
    """
    args = ["worktree", "prune", "--verbose"] + ([] if apply else ["--dry-run"])
    ok, out = run_git(repo, *args, merge_stderr=True)
    return out if ok else f"prune failed: {out}"


def _replace(result: RepoBranchGcResult, **changes) -> RepoBranchGcResult:
    fields = {
        "repo": result.repo,
        "enabled": result.enabled,
        "applied": result.applied,
        "cap": result.cap,
        "min_age_days": result.min_age_days,
        "verdicts": result.verdicts,
        "config_source": result.config_source,
        "config_error": result.config_error,
        "abort_reason": result.abort_reason,
        "backup_dir": result.backup_dir,
        "bundle_path": result.bundle_path,
        "restore_command": result.restore_command,
        "prune_detail": result.prune_detail,
        "error": result.error,
    }
    fields.update(changes)
    return RepoBranchGcResult(**fields)


def gc_repos(
    repos,
    *,
    apply: bool = False,
    home: str | Path | None = None,
    cap: int = DEFAULT_BRANCH_CAP,
    max_delete: int | None = None,
    now: float | None = None,
    pr_merged: PrLookup = gh_pr_merged,
    pr_open: PrLookup = gh_pr_open,
    active_refs: ActiveRefs = card_active_tokens,
) -> BranchGcOutcome:
    """Run :func:`gc_repo` over every repo; one bad repo never stops the rest."""
    return BranchGcOutcome(
        results=tuple(
            gc_repo(
                repo,
                apply=apply,
                home=home,
                cap=cap,
                max_delete=max_delete,
                now=now,
                pr_merged=pr_merged,
                pr_open=pr_open,
                active_refs=active_refs,
            )
            for repo in repos
        )
    )


# EOF
