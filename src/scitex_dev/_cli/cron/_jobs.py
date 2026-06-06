#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registry of managed cron jobs for `scitex-dev cron`.

A "managed job" is identified by a short slug (the ``name`` argument
passed to ``install`` / ``remove`` / ``status``). The registry maps that
slug to a 5-field cron schedule and the literal shell command that gets
materialised into the user's crontab — tagged with
``# scitex-dev cron: <name>`` so we can find it again.

Why a registry (vs. a free-form ``add <schedule> <command>``):

  * Ecosystem-wide cron jobs are *known* artifacts that other parts of
    the ecosystem expect to be present (e.g. the ci-watch loop is part of
    how sac agents notice they have a fix-forward turn to take).
  * Operators install / remove by *name*, not by reconstructing the
    schedule + command line from memory.
  * Adding a new job is a one-entry diff here, plus the implementation
    module under this package. Nothing else in the CLI changes.

To add a new managed job:

  1. Implement the job. Either as a Python entry point invoked via the
     console script (``scitex-dev cron run <name>``) or as a standalone
     shell command — either is fine; the registry just records the
     resulting cron line.
  2. Add an entry to ``JOB_REGISTRY`` below: ``name → (schedule, command,
     description)``. Keep the schedule conservative (every 5-15 minutes
     is plenty for poll loops).
  3. Write the unit test that pins the registry entry — see
     ``tests/scitex_dev/_cli/cron/test__jobs.py``.

The registry is intentionally a module-level dict (no YAML loader, no
dynamic discovery): one diff, one commit, one PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class JobSpec:
    """One managed cron job."""

    name: str
    schedule: str
    command: str
    description: str


def _ci_watch_command() -> str:
    """The shell line installed for the ``ci-watch`` cron job.

    We invoke the console script (``scitex-dev cron exec ci-watch``) so
    the line stays stable across virtual-env shuffles — ``scitex-dev`` is
    on PATH wherever this CLI is installed.

    Output is appended to ``~/.scitex/dev/logs/cron-ci-watch.log``; size
    rotation is intentionally not done here (cron-watch is low-volume
    and the log is operator-facing, not a hot path).
    """
    log = "$HOME/.scitex/dev/logs/cron-ci-watch.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec ci-watch >> {log} 2>&1"


def _worktree_gc_command() -> str:
    """The shell line installed for the ``worktree-gc`` cron job.

    Same shape as ``ci-watch`` / ``quota-keepalive``: invoke the console
    script so the line stays stable across virtual-env shuffles,
    ``mkdir -p`` the log dir first, append output to a per-job log.

    Schedule rationale: every 6 hours is conservative — a single sweep
    is short (find git dirs, ``git worktree list``, mtime check), and
    proj-scitex-agent-container is concurrently working on the
    RELOCATION half (stopping ``.claude/worktrees`` from being created
    in the first place), so the cleanup loop's load will fall over
    time. Until that ships, 4 sweeps per day keeps the orphan count
    bounded without spending CI on a constant background walk.
    """
    log = "$HOME/.scitex/dev/logs/cron-worktree-gc.log"
    return (
        f"mkdir -p $(dirname {log}); scitex-dev cron exec worktree-gc >> {log} 2>&1"
    )


def _quota_keepalive_command() -> str:
    """The shell line installed for the ``quota-keepalive`` cron job.

    Same shape as ``ci-watch``: invoke the console script so the line
    stays stable across virtual-env shuffles, ``mkdir -p`` the log dir
    first, append output to a per-job log.

    The crontab schedule is ``*/30 * * * *`` (every 30 minutes), but the
    body self-gates to fire only every 2.5 hours — see
    ``_quota_keepalive.run_once`` for why 2.5 h cannot be one cron
    interval and how the timestamp gate enforces exact spacing.
    """
    log = "$HOME/.scitex/dev/logs/cron-quota-keepalive.log"
    return (
        f"mkdir -p $(dirname {log}); scitex-dev cron exec quota-keepalive >> {log} 2>&1"
    )


JOB_REGISTRY: Mapping[str, JobSpec] = {
    "ci-watch": JobSpec(
        name="ci-watch",
        schedule="*/10 * * * *",
        command=_ci_watch_command(),
        description=(
            "Poll each sac agent's owned repo for CI red on develop; "
            "dispatch a fix-forward A2A turn to the responsible agent "
            "when failures are seen."
        ),
    ),
    "quota-keepalive": JobSpec(
        name="quota-keepalive",
        # Crontab ticks every 30 min; the body self-gates to a 2.5-hour
        # cadence (2.5 h is not expressible as a single cron interval).
        schedule="*/30 * * * *",
        command=_quota_keepalive_command(),
        description=(
            "Fire a trivial 'hello' turn every 2.5 hours (self-gated) to "
            "pre-start Claude's rolling 5-hour quota window, so real work "
            "begins against a window that is already partway elapsed."
        ),
    ),
    "worktree-gc": JobSpec(
        name="worktree-gc",
        # Every 6 hours: 4 sweeps per day, generous headroom over the
        # mtime threshold (default 3 days). See _worktree_gc_command's
        # docstring for the schedule rationale.
        schedule="0 */6 * * *",
        command=_worktree_gc_command(),
        description=(
            "Periodic cleanup of stale `.claude/worktrees/` directories "
            "left behind by subagents. mtime-gated, git-worktree-aware, "
            "never touches the operator's `.worktrees/`. See _worktree_gc."
        ),
    ),
    # Future entries land here. Suggested naming pattern: short
    # action-noun like `rotate-all`, `audit-sweep`, `pypi-publish-watch`.
}


def get_job(name: str) -> JobSpec:
    """Return the registered ``JobSpec`` for ``name`` or raise KeyError."""
    try:
        return JOB_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(JOB_REGISTRY)) or "(none)"
        raise KeyError(f"unknown cron job: {name!r}. Known jobs: {known}") from None


def list_jobs() -> list[JobSpec]:
    """Return every registered ``JobSpec`` sorted by name."""
    return [JOB_REGISTRY[k] for k in sorted(JOB_REGISTRY)]


# EOF
