#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/cron/_ci_watch_types.py
"""Shared shapes for the ci-watch job.

Extracted so `_ci_watch_red` and `_ci_watch_cards` can both depend on
them WITHOUT importing the orchestrator, which would be a cycle. The
types are the only thing those two layers genuinely share.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# ---------------------------------------------------------------------------
# Agent → owned repo map
# ---------------------------------------------------------------------------
# Edit this in-place when a new sac agent joins the fleet. Move to a
# config file when the list grows past ~10 entries (the bash prototype's
# threshold).
#
# THE KEYS ARE sac AGENT NAMES AND MUST RESOLVE IN sac's REGISTRY. They
# were `proj-scitex-*` until the fleet renamed its agents to the bare
# form; this map was not migrated with them, so every dispatch went to a
# name that does not exist. MEASURED 2026-08-23 on compute-04: 140 agents
# defined, all five bare names present, all five `proj-` forms absent,
# and exactly one `proj-`-prefixed agent survives fleet-wide
# (proj-scitex-hub, which is not in this map).
#
# The cost was not the failed dispatch. ci-watch kept WORKING -- it found
# real red CI on scitex-str (ci) and scitex-types (docs) -- and then could
# not tell anybody, for five days, because the agent it tried to hand the
# work to had no spec.yaml. sac's own error says it plainly: "If a
# SCHEDULED JOB is sending here, it is dispatching to a name that does not
# exist -- fix the job's target list rather than this agent."
#
# So: when renaming an agent, grep for its OLD name before considering the
# rename done. A published name is a contract, and this map is a caller.
AGENTS_TO_REPOS: Mapping[str, str] = {
    "scitex-stats": "ywatanabe1989/scitex-stats",
    "scitex-types": "ywatanabe1989/scitex-types",
    "scitex-dict": "ywatanabe1989/scitex-dict",
    "scitex-str": "ywatanabe1989/scitex-str",
    "scitex-datetime": "ywatanabe1989/scitex-datetime",
}

# The fix-forward prompt dispatched to the responsible agent. Ported
# verbatim from scripts/ci-watch.sh — keep the agent-facing wording
# consistent so the agent's behaviour is identical regardless of which
# loop fired the turn (cron vs. on-demand).
FIX_PROMPT_TEMPLATE = """\
CI red on `{repo}` develop. The following workflow(s) report failure on the latest run:

{reds}

Investigate the root cause:
  1. `gh -R {repo} run list --branch develop --limit 5` to see recent runs.
  2. For each failing workflow, `gh -R {repo} run view <id> --log-failed` (or grep ERRO / FAILED in the logs).
  3. Pull develop, fix the root cause, commit on a fix branch, push, open a PR (`gh pr create --base develop`), and merge after CI confirms green.

If the failure is a pre-existing issue out of your scope (e.g. credentials missing on the runner), reply BLOCKED with a one-line reason. Otherwise reply with the PR URL on completion."""


@dataclass(frozen=True)
class AgentResult:
    """Per-agent outcome of one ci-watch pass."""

    agent: str
    repo: str
    red_workflows: tuple[str, ...]
    dispatched: bool
    dispatch_output: str
    error: str | None = None
    # Per-pass todo bookkeeping: the (workflow, sha) identities that
    # were filed into scitex-todo on this round, and the identities
    # that were already on file (idempotent skip). Both empty when
    # scitex-todo is unavailable (fail-open) or when there were no
    # red workflows to file in the first place.
    todos_filed: tuple[str, ...] = ()
    todos_already_open: tuple[str, ...] = ()

    def is_red(self) -> bool:
        return bool(self.red_workflows)


@dataclass(frozen=True)
class FailingRun:
    """One workflow whose latest develop run is ``failure``.

    Carries the identity tuple (``workflow``, ``run_id``, ``head_sha``)
    that the scitex-todo hook uses as its idempotency key — same
    (workflow, head_sha) re-detected on a later cron round must NOT
    create a duplicate todo. ``run_id`` is fetched alongside so the
    todo can link the operator at the failing run's GitHub Actions
    page directly.
    """

    workflow: str
    run_id: int
    head_sha: str



# EOF
