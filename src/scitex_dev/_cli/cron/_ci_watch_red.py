#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/cron/_ci_watch_red.py
"""ci-watch: which workflows are RED on develop, per repo.

The `gh` seam lives here. `_default_gh_runner` is injected so tests
pass their own fake rather than shelling out.
"""

from __future__ import annotations

import json
import subprocess
from typing import Callable

from ._ci_watch_types import FailingRun

# ---------------------------------------------------------------------------
# gh layer
# ---------------------------------------------------------------------------


def _default_gh_runner(args: list[str]) -> subprocess.CompletedProcess:
    """Real ``gh`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def red_runs_for(
    repo: str,
    *,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> list[FailingRun]:
    """Return one :class:`FailingRun` per workflow whose latest develop run is ``failure``.

    Parses the JSON output of

        gh -R <repo> run list --branch develop --limit 12 \
            --json conclusion,workflowName,databaseId,headSha

    Only the most recent run per workflow is considered — ``gh`` returns
    runs newest-first, so the first occurrence of each ``workflowName``
    wins. Pure helper; no side-effects.

    The ``headSha`` field is needed downstream by
    :func:`_create_todo_if_new` for its idempotency key (a re-poll on
    the same failing SHA must NOT spawn a duplicate todo). ``databaseId``
    becomes ``run_id`` so the todo can link straight to the failing
    run's logs page.

    Raises ``RuntimeError`` if ``gh`` exits non-zero — the cron job
    swallows the error per-repo so one bad repo doesn't kill the loop.
    """
    run = gh_runner or _default_gh_runner
    args = [
        "-R",
        repo,
        "run",
        "list",
        "--branch",
        "develop",
        "--limit",
        "12",
        "--json",
        "conclusion,workflowName,databaseId,headSha",
    ]
    r = run(args)
    if r.returncode != 0:
        raise RuntimeError(
            f"`gh {' '.join(args)}` failed (rc={r.returncode}): "
            f"{(r.stderr or r.stdout).strip()}"
        )
    try:
        data = json.loads(r.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned non-JSON for {repo}: {exc}") from exc

    seen: set[str] = set()
    reds: list[FailingRun] = []
    for entry in data:
        name = entry.get("workflowName")
        if not name or name in seen:
            continue
        seen.add(name)
        if entry.get("conclusion") == "failure":
            reds.append(
                FailingRun(
                    workflow=name,
                    run_id=int(entry.get("databaseId") or 0),
                    head_sha=str(entry.get("headSha") or ""),
                )
            )
    return reds


def red_workflows_for(
    repo: str,
    *,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> list[str]:
    """Return the workflow names whose latest develop run is ``failure``.

    Thin name-only wrapper around :func:`red_runs_for`, preserved as the
    historical wire shape (``list[str]``) so existing callers and tests
    keep working unchanged after the rich-tuple refactor that lets the
    scitex-todo hook see ``head_sha`` / ``run_id``.
    """
    return [r.workflow for r in red_runs_for(repo, gh_runner=gh_runner)]




# EOF
