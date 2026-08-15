#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Branch lifecycle — the THREE DAYS RULE, as code rather than as a habit.

A pure re-export façade, so the import path a caller pins never moves when the
internals are rearranged. The judgement lives in :mod:`._sweep` and reads
nothing: git and GitHub plumbing is the caller's job, which is what makes the
rule reviewable without running the destructive half.
"""

from __future__ import annotations

from ._sweep import (
    MAX_AGE_DAYS,
    PROTECTED_BRANCHES,
    BranchFacts,
    Decision,
    SweepPlan,
    Verdict,
    classify,
    plan_sweep,
    render_plan,
)

__all__ = [
    "MAX_AGE_DAYS",
    "PROTECTED_BRANCHES",
    "BranchFacts",
    "Decision",
    "SweepPlan",
    "Verdict",
    "classify",
    "plan_sweep",
    "render_plan",
]

# EOF
