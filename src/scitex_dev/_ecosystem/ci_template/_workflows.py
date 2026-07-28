#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workflow-file housekeeping policy for ``ci-template apply``.

Extracted from ``_apply`` so the "which files does apply touch, and why"
decision lives in ONE readable place — and so the answer can be reported
in full, per file, instead of leaking out as three partial lists.

Two invariants this module exists to hold:

1. **Every workflow file lands in exactly one bucket.** ``plan_workflow_changes``
   partitions ``.github/workflows/`` into *delete* / *protected* / *skipped*
   (the caller adds *written* for the file it emits) and records a REASON for
   each kept file. Silence about a file is indistinguishable from never having
   looked at it, which is exactly how a PS-224-violating leftover survived a
   "successful" apply unnoticed (measured 2026-07-28, fleet migration).

2. **Protection is conditional when the emitted ci.yml supersedes the file.**
   ``rtd-sphinx-*.yml`` was protected unconditionally, but the thin caller now
   emits an ``rtd-sphinx-build:`` job that does the same work. Keeping the
   standalone file meant every migrated repo retained a
   ``runs-on: ubuntu-latest`` workflow — a PS-224 ERROR that the tool itself
   guaranteed, then handed to a human to delete by hand. Protection is now
   lifted for a prefix ONLY when the rendered ci.yml genuinely carries the
   superseding caller job (see ``SUPERSEDING_CALLER_JOB``); a template that
   ever drops that job re-protects the files automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import yaml

# The one canonical per-repo workflow this mechanism emits.
CANONICAL_WORKFLOW = "ci.yml"

# Hardcoded prefix list for the delete-on-apply step. ONLY files matching
# one of these prefixes are eligible for deletion; unknown workflows are
# left alone. Keep this list narrow.
DELETABLE_WORKFLOW_PREFIXES: Tuple[str, ...] = (
    # Retired consolidated pair (the losing canonical mechanism).
    "pr-ci.yml",
    "release-ci.yml",
    # Granular pre-consolidation files.
    "import-smoke-",
    "pytest-matrix-",
    "dep-hygiene-smoke",
    # Operator-ordered fleet-wide removal (2026-07-21).
    "newb-docs",
    # `<pkg>-quality-audit*` is covered by the live-check in
    # ``eligible_for_delete``: filename contains "quality-audit".
)

# Workflows that MUST be preserved no matter what (operator-edited).
PROTECTED_WORKFLOWS: Tuple[str, ...] = (
    CANONICAL_WORKFLOW,
    "cla.yml",
    "auto-merge-to-develop.yaml",
    "auto-merge-to-develop.yml",
)

# Prefix-based preservation. Protection may be CONDITIONAL — see
# ``SUPERSEDING_CALLER_JOB``.
PROTECTED_WORKFLOW_PREFIXES: Tuple[str, ...] = (
    "pypi-publish-",
    "rtd-sphinx-",
)

# Protected prefix -> the caller job id in the emitted ci.yml that SUPERSEDES
# those standalone files. When (and only when) the rendered ci.yml actually
# declares that job, the prefix's protection is lifted and its files become
# deletable: the work still happens, org-side, on a registered runner.
#
# `pypi-publish-` is deliberately absent: the thin caller emits no publish
# job, so those files are genuinely non-superseded and stay protected.
SUPERSEDING_CALLER_JOB: Dict[str, str] = {
    "rtd-sphinx-": "rtd-sphinx-build",
}

# Reason strings — surfaced verbatim in the dry-run output, so they are
# written for an operator reading a terminal, not for a log grep.
REASON_PROTECTED_EXACT = "protected: operator-owned workflow, never removed by apply"
REASON_PROTECTED_PREFIX = (
    "protected: prefix `{prefix}` and the emitted ci.yml carries no "
    "superseding caller job"
)
REASON_NOT_ELIGIBLE = (
    "kept: not on the delete prefix list (unknown / operator-owned workflow)"
)


def caller_job_ids(ci_yml_body: str) -> frozenset:
    """Job ids declared by a rendered ci.yml body.

    Parses the YAML rather than string-matching, so a job that is merely
    MENTIONED in the template's comment header (which lists the required
    status-check contexts) can never be mistaken for one that is emitted.
    Returns an empty set for anything that does not parse as a mapping with
    a ``jobs:`` mapping — the safe direction, since an unreadable template
    then supersedes nothing and every protection stays in force.
    """
    try:
        doc = yaml.safe_load(ci_yml_body)
    except yaml.YAMLError:
        return frozenset()
    if not isinstance(doc, dict):
        return frozenset()
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return frozenset()
    return frozenset(str(k) for k in jobs)


def superseded_protected_prefixes(rendered: Mapping[str, str]) -> Tuple[str, ...]:
    """Protected prefixes whose protection the emitted ci.yml lifts.

    *rendered* is ``apply``'s ``{repo-relative-path: content}`` map. A prefix
    is returned only when the emitted ``ci.yml`` genuinely declares the
    caller job registered for it in ``SUPERSEDING_CALLER_JOB``.
    """
    body = rendered.get(f".github/workflows/{CANONICAL_WORKFLOW}")
    if not body:
        return ()
    job_ids = caller_job_ids(body)
    return tuple(
        prefix
        for prefix, job_id in sorted(SUPERSEDING_CALLER_JOB.items())
        if job_id in job_ids
    )


def eligible_for_delete(
    workflow_filename: str,
    *,
    superseded_prefixes: Sequence[str] = (),
) -> bool:
    """True iff *workflow_filename* may be deleted by this apply.

    A protected PREFIX yields to deletion only when it appears in
    *superseded_prefixes* — i.e. the emitted ci.yml provides the replacement.
    Everything else keeps the original narrow behaviour: match the hardcoded
    delete list, or be left alone.
    """
    if workflow_filename in PROTECTED_WORKFLOWS:
        return False
    for prefix in PROTECTED_WORKFLOW_PREFIXES:
        if workflow_filename.startswith(prefix):
            return prefix in superseded_prefixes
    if any(workflow_filename.startswith(p) for p in DELETABLE_WORKFLOW_PREFIXES):
        return True
    # `<pkg>-quality-audit*` heuristic.
    if "quality-audit" in workflow_filename:
        return True
    return False


def keep_reason(
    workflow_filename: str,
    *,
    superseded_prefixes: Sequence[str] = (),
) -> str:
    """Why *workflow_filename* is being kept. Only meaningful for a file
    ``eligible_for_delete`` refused."""
    if workflow_filename in PROTECTED_WORKFLOWS:
        return REASON_PROTECTED_EXACT
    for prefix in PROTECTED_WORKFLOW_PREFIXES:
        if workflow_filename.startswith(prefix) and prefix not in superseded_prefixes:
            return REASON_PROTECTED_PREFIX.format(prefix=prefix)
    return REASON_NOT_ELIGIBLE


def is_protected(
    workflow_filename: str,
    *,
    superseded_prefixes: Sequence[str] = (),
) -> bool:
    """True iff the file is kept because it is PROTECTED (as opposed to
    merely not matching the delete list)."""
    if workflow_filename in PROTECTED_WORKFLOWS:
        return True
    return any(
        workflow_filename.startswith(prefix) and prefix not in superseded_prefixes
        for prefix in PROTECTED_WORKFLOW_PREFIXES
    )


def list_workflows(repo_dir: Path) -> List[Path]:
    """Every file under ``.github/workflows/``, sorted.

    ``.github`` is a HIDDEN directory: the path is built explicitly rather
    than discovered by a walker, because a walker that skips dotted dirs
    returns zero files — indistinguishable from "this repo has none".
    """
    wf_dir = repo_dir / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(p for p in wf_dir.iterdir() if p.is_file())


@dataclass
class WorkflowPlan:
    """Partition of ``.github/workflows/`` into what apply will do to it.

    ``to_delete`` / ``protected`` / ``skipped`` are DISJOINT, and together
    with the caller's written paths they cover the whole directory — the
    invariant that makes a dry-run a complete statement of blast radius
    rather than a selective one.
    """

    to_delete: List[Path] = field(default_factory=list)
    protected: List[Path] = field(default_factory=list)
    skipped: List[Path] = field(default_factory=list)
    #: str(path) -> operator-facing reason, for every KEPT file.
    reasons: Dict[str, str] = field(default_factory=dict)


def plan_workflow_changes(
    existing: Iterable[Path],
    *,
    rendered_paths: Iterable[Path],
    superseded_prefixes: Sequence[str] = (),
) -> WorkflowPlan:
    """Partition *existing* workflow files into delete / protected / skipped.

    Files in *rendered_paths* (the ones apply is about to (re-)write) are
    excluded entirely — the caller reports them as WRITTEN.
    """
    written = set(rendered_paths)
    plan = WorkflowPlan()
    for wf in existing:
        if wf in written:
            continue
        name = wf.name
        if eligible_for_delete(name, superseded_prefixes=superseded_prefixes):
            plan.to_delete.append(wf)
            continue
        reason = keep_reason(name, superseded_prefixes=superseded_prefixes)
        plan.reasons[str(wf)] = reason
        if is_protected(name, superseded_prefixes=superseded_prefixes):
            plan.protected.append(wf)
        else:
            plan.skipped.append(wf)
    return plan


# EOF
