#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev.branch_hygiene`` — the fleet's daily branch sweep.

Two dimensions, because scitex-dev already knows both: every package in
the ECOSYSTEM registry, on every host in the host registry.

    checkouts -> develop      refuse a dirty tree, never stash, never force
    local branches            collect what is finished, worktree and all
    remote branches           the same rule, run ONCE for the whole fleet

WHAT IS KEPT, IN ONE LIST
-------------------------
``main`` / ``master`` / ``develop`` / ``cla-signatures`` by EXACT name;
any branch with an OPEN pull request; anything touched inside the window
that has not already merged into develop; and anything at all that could
not be measured. Everything else is finished work.

RELATIONSHIP TO :mod:`scitex_dev.hygiene`
-----------------------------------------
They are different rules for different jobs and both are wanted.
``hygiene`` is the conservative, config-gated collector: it deletes only
branches it can PROVE landed, no earlier than a 14-day floor that no
configuration may lower, local refs only. This module implements the
operator's daily rule, which is deliberately more aggressive — a
one-day window, and stale-but-unlanded branches go too — and adds the
two legs ``hygiene`` explicitly declines to have: remote refs and
worktree removal.

Sharing the primitives rather than the policy is the point. The git and
GitHub plumbing that both need (``run_git``, ``reflog_epoch``) and the
verified bundle written before any deletion are imported from
``hygiene``; only the decision function is new.
"""

from __future__ import annotations

from ._decide import age_hours, classify, decide, decide_remote, is_protected, worktree_plan
from ._model import (
    AMBIGUOUS_REMOTE_NAMES,
    DEFAULT_MAX_AGE_HOURS,
    DROP_MERGED,
    DROP_STALE,
    KEEP_AGE_UNKNOWN,
    KEEP_AMBIGUOUS_NAME,
    KEEP_CURRENT_HEAD,
    KEEP_MOVED,
    KEEP_OPEN_PR,
    KEEP_PR_UNKNOWN,
    KEEP_PROTECTED,
    KEEP_RECENT,
    KEEP_WORKTREE_BUSY,
    KEEP_WORKTREE_REFUSED,
    KEEP_WORKTREE_UNKNOWN,
    PROTECTED_EXACT,
    WT_KEEP,
    WT_NONE,
    WT_REMOVE,
    WT_REMOVE_FORCE,
    BranchFacts,
    BranchVerdict,
    CheckoutResult,
    Discarded,
    RepoResult,
    SweepOutcome,
    exit_code_for,
)
from ._repo import align_checkout, sweep_local, sweep_remote, sweep_repo
from ._sweep import fan_out, fleet_hosts, registry_repos, sweep_local_host

__all__ = [
    "AMBIGUOUS_REMOTE_NAMES",
    "DEFAULT_MAX_AGE_HOURS",
    "DROP_MERGED",
    "DROP_STALE",
    "KEEP_AGE_UNKNOWN",
    "KEEP_AMBIGUOUS_NAME",
    "KEEP_CURRENT_HEAD",
    "KEEP_MOVED",
    "KEEP_OPEN_PR",
    "KEEP_PR_UNKNOWN",
    "KEEP_PROTECTED",
    "KEEP_RECENT",
    "KEEP_WORKTREE_BUSY",
    "KEEP_WORKTREE_REFUSED",
    "KEEP_WORKTREE_UNKNOWN",
    "PROTECTED_EXACT",
    "WT_KEEP",
    "WT_NONE",
    "WT_REMOVE",
    "WT_REMOVE_FORCE",
    "BranchFacts",
    "BranchVerdict",
    "CheckoutResult",
    "Discarded",
    "RepoResult",
    "SweepOutcome",
    "age_hours",
    "align_checkout",
    "classify",
    "decide",
    "decide_remote",
    "exit_code_for",
    "fan_out",
    "fleet_hosts",
    "is_protected",
    "registry_repos",
    "sweep_local",
    "sweep_local_host",
    "sweep_remote",
    "sweep_repo",
    "worktree_plan",
]

# EOF
