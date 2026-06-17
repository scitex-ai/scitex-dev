#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ephemeral CI-runner POOL — serve the whole ecosystem's CI from one booked
Spartan lease, load-balanced + queued.

Problem: ``ywatanabe1989`` is a User account → GitHub self-hosted runners are
REPO-scoped (no org/shared pool), and the ecosystem has ~67 repos that all run
the same heavy ``pytest-matrix`` CI. 67 persistent runners on one node is
unworkable; the github-hosted alternative hits the Actions spending cap.

Design (operator directive 2026-06-17: "use the already-booked running Spartan
nodes for CI for all the ecosystem, with load balancing in a queued manner"):
a DISPATCHER polls every ecosystem repo for QUEUED jobs that want the
``spartan-cpu`` label, and for each — up to a concurrency cap ``max_concurrent``
— mints a **just-in-time (ephemeral) runner** for that repo and launches it on
the already-running ``srun --overlap`` lease. An ephemeral runner runs exactly
ONE job then deregisters itself, so a small fixed pool of slots cycles through
the whole fleet. GitHub's own queue holds jobs until a slot frees → that is the
"queued + load-balanced" behaviour, for free, with no webhook (poll-only, which
suits the loopback-only constraint).

Safety: ``dispatch_once`` defaults to ``dry_run=True`` — it reports what it WOULD
launch without launching. Phase rollout flips it on for one repo first.

Seams (PA-306 / STX-NM*): the GitHub call (``gh_caller``), the active-runner
count (``count_active``) and the launch (``launcher``) are injected, so the
decision + orchestration logic is tested against fakes — no mocks, no live infra.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable

# Label every pooled runner carries; ecosystem workflows target it via
# ``runs-on: [self-hosted, spartan-cpu]``.
POOL_LABEL = "spartan-cpu"


@dataclass(frozen=True)
class QueuedJob:
    """A workflow job waiting for a ``spartan-cpu`` runner."""

    repo: str  # owner/repo
    run_id: int
    title: str = ""


@dataclass
class DispatchResult:
    """Outcome of one dispatcher cycle."""

    active: int = 0
    queued: list = field(default_factory=list)
    launched: list = field(default_factory=list)  # QueuedJob list actually launched
    dry_run: bool = True


def _default_gh(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    return p.returncode, p.stdout


def find_queued_jobs(
    repos: list[str], *, gh_caller: Callable[[list[str]], tuple[int, str]] | None = None
) -> list[QueuedJob]:
    """Return QUEUED workflow runs across ``repos`` (one ``gh api`` call each).

    A queued run with no available matching runner is exactly what the pool
    exists to serve. We don't filter by label here — every ecosystem workflow
    targets ``spartan-cpu`` once migrated, so a queued run == a job for us.
    """
    gh = gh_caller or _default_gh
    out: list[QueuedJob] = []
    for repo in repos:
        rc, body = gh([f"repos/{repo}/actions/runs?status=queued&per_page=20"])
        if rc != 0:
            continue
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            continue
        for run in data.get("workflow_runs", []):
            out.append(
                QueuedJob(
                    repo=repo, run_id=run.get("id", 0), title=run.get("name", "")[:40]
                )
            )
    return out


def decide_launches(
    queued: list[QueuedJob], active: int, max_concurrent: int
) -> list[QueuedJob]:
    """Pure: pick the queued jobs to launch this cycle (FIFO, up to free slots).

    ``free = max(0, max_concurrent - active)``. Returns at most ``free`` jobs.
    This is the whole load-balancing rule: a fixed pool of ``max_concurrent``
    slots, oldest-queued-first, the rest left in GitHub's queue.
    """
    free = max(0, max_concurrent - active)
    return list(queued[:free])


def dispatch_once(
    repos: list[str],
    *,
    max_concurrent: int,
    count_active: Callable[[], int],
    launcher: Callable[[QueuedJob], bool],
    gh_caller: Callable[[list[str]], tuple[int, str]] | None = None,
    dry_run: bool = True,
    out=None,
) -> DispatchResult:
    """One dispatcher cycle: poll → decide → (launch unless dry-run).

    Cron-safe: never raises on a per-repo poll error or a single launch
    failure; both are logged and the cycle continues. Returns a
    :class:`DispatchResult` for the caller/tests to inspect.
    """
    if out is None:
        out = sys.stdout
    active = count_active()
    queued = find_queued_jobs(repos, gh_caller=gh_caller)
    picks = decide_launches(queued, active, max_concurrent)
    result = DispatchResult(active=active, queued=queued, launched=[], dry_run=dry_run)

    print(
        f"ci-pool: active={active}/{max_concurrent} queued={len(queued)} "
        f"to-launch={len(picks)}{' (DRY-RUN)' if dry_run else ''}",
        file=out,
    )
    for job in picks:
        if dry_run:
            print(
                f"ci-pool: WOULD launch ephemeral runner for {job.repo} run={job.run_id}",
                file=out,
            )
            continue
        try:
            ok = launcher(job)
        except (
            Exception
        ) as exc:  # stx-allow: fallback (reason: never crash the dispatcher loop)
            print(
                f"ci-pool: launch FAILED for {job.repo} run={job.run_id}: {exc}",
                file=out,
            )
            ok = False
        if ok:
            result.launched.append(job)
            print(
                f"ci-pool: launched ephemeral runner for {job.repo} run={job.run_id}",
                file=out,
            )
    return result


def generate_jit_config(
    repo: str,
    name: str,
    *,
    labels=(POOL_LABEL,),
    gh_caller: Callable[[list[str]], tuple[int, str]] | None = None,
) -> str | None:
    """Mint an encoded just-in-time (ephemeral) runner config for ``repo``.

    POST ``/repos/{repo}/actions/runners/generate-jitconfig``; the returned
    ``encoded_jit_config`` is passed to ``./run.sh --jitconfig <cfg>`` on the
    Spartan node — the runner registers, runs ONE job, and deregisters itself
    (no removal token, no leaked registration). Returns None on failure.
    """
    gh = gh_caller or _default_gh
    args = [
        "-X",
        "POST",
        f"repos/{repo}/actions/runners/generate-jitconfig",
        "-f",
        f"name={name}",
        "-F",
        "runner_group_id=1",
    ]
    for lb in labels:
        args += ["-f", f"labels[]={lb}"]
    rc, body = gh(args)
    if rc != 0:
        return None
    try:
        return json.loads(body).get("encoded_jit_config")
    except (json.JSONDecodeError, TypeError):
        return None
