#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Periodic repo-hygiene primitives. Config-gated, DEFAULT OFF.

One engine, several front-ends: the CLI verb
(``scitex-dev ecosystem prune-branches``), the managed cron job
(``scitex-dev cron exec branch-gc``) and any future sweep all call into
this package rather than each growing their own copy of the predicate.
That is why it is a top-level domain package and not a module buried
under ``_cli/cron/`` — the existing ``worktree-gc`` job made the other
choice and grew to 530 lines with no reusable surface.

The first sweep is BRANCH GC. Its whole reason to exist is a 2026-08-08
incident: an ad-hoc cleanup deleted 7 local branches that were the live
substrate of an in-flight operator mission. Every property in
``_branch_gc_*`` is a direct answer to one of the things that went wrong,
and the asymmetry behind all of them is stated once, here:

    A false KEEP leaves a dead ref in a listing. A false DELETE destroys
    work that exists nowhere else. We pick the cluttered listing.

Read :mod:`._branch_gc_model` for the vocabulary,
:mod:`._branch_gc_config` for the four independent OFF gates,
:mod:`._branch_gc_predicate` for the five-leg safety predicate, and
:mod:`._branch_gc_backup` for the bundle-before-delete contract.
"""

from __future__ import annotations

from ._branch_gc import gc_repo, gc_repos
from ._branch_gc_config import CleanupConfig, load_branch_cleanup_config
from ._branch_gc_model import (
    DEFAULT_BRANCH_CAP,
    DEFAULT_MIN_AGE_DAYS,
    HARD_MIN_AGE_DAYS,
    BranchGcOutcome,
    BranchInfo,
    BranchVerdict,
    RepoBranchGcResult,
    exit_code_for,
)

__all__ = [
    "DEFAULT_BRANCH_CAP",
    "DEFAULT_MIN_AGE_DAYS",
    "HARD_MIN_AGE_DAYS",
    "BranchGcOutcome",
    "BranchInfo",
    "BranchVerdict",
    "CleanupConfig",
    "RepoBranchGcResult",
    "exit_code_for",
    "gc_repo",
    "gc_repos",
    "load_branch_cleanup_config",
]

# EOF
