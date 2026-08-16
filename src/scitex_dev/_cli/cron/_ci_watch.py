#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ci-watch`` cron job — poll sac-agent repos for CI red, dispatch A2A.

Ports ``scripts/ci-watch.sh`` (lives in scitex-lead) to Python so it can
be installed via ``scitex-dev cron install ci-watch``. Behaviour matches
the bash prototype:

  * Iterate the agent → repo map (see ``AGENTS_TO_REPOS`` below).
  * For each repo, ask ``gh`` for the last 12 develop-branch runs and
    take the latest one per workflow name. Workflows whose latest run is
    ``failure`` are "red".
  * Red workflows → dispatch a fix-forward turn via ``sac agents send``.

When ``--dry-run`` is set, no ``sac agents send`` is fired — the would-be
prompt is printed instead. This is what the cron operator uses to verify
the loop without firing A2A turns (e.g. while the lead's Claude
credentials need re-rsync to Spartan).

The module exposes its key seams (``gh_runner``, ``sac_runner``) as
keyword arguments on every function so tests can pass real fakes
instead of monkey-patching ``subprocess``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


# ---------------------------------------------------------------------------
# Re-exports — the layers above were extracted for the 512-line limit.
# Every existing `from ._ci_watch import X` keeps resolving.
# ---------------------------------------------------------------------------
from ._ci_watch_types import (  # noqa: E402,F401
    AGENTS_TO_REPOS,
    FIX_PROMPT_TEMPLATE,
    AgentResult,
    FailingRun,
)
from ._ci_watch_red import (  # noqa: E402,F401
    _default_gh_runner,
    red_runs_for,
    red_workflows_for,
)
from ._ci_watch_cards import (  # noqa: E402,F401
    _TodoApi,
    _create_todo_if_new,
    _resolve_todo_api,
    _todo_task_id_for,
)

# ---------------------------------------------------------------------------
# sac dispatch layer
# ---------------------------------------------------------------------------


def _default_sac_runner(
    args: list[str],
    *,
    input_text: str,
) -> subprocess.CompletedProcess:
    """Real ``sac`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["sac", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# sac sidecar busy probe
# ---------------------------------------------------------------------------
#
# The cron job dispatches via ``sac agents send``, which has a hard 120 s
# server-side timeout. When an agent is mid-turn from a previous round,
# the new send blocks for the full 120 s before failing — and the next
# agent's send is delayed in turn. Three busy agents = 6 minutes lost,
# and the 10-minute cron interval starts to overflow.
#
# sac's A2A sidecar exposes a non-spec observability route at
# ``/agents/<name>/_active`` returning ``{"tasks": [...]}``. We probe it
# before each ``dispatch_fix_turn`` and skip the agent if any task is
# active. The check is fail-open: any HTTP / parse / timeout error
# returns False (treat as not-busy) — under-skipping is recoverable
# (one wasted 120 s send), over-skipping silently mutes the watcher.

# Short on purpose. The endpoint is in-process on the sidecar and
# returns instantly when reachable; a long wait defeats the whole point
# of probing before the 120 s send.
_BUSY_PROBE_TIMEOUT_S = 5.0


def _default_http_runner(url: str, timeout: float) -> tuple[int, bytes]:
    """Real ``urllib`` GET. Tests pass their own fake.

    Returns ``(status_code, body_bytes)``. Raises on transport failure
    (connection refused, timeout, etc.) — :func:`_is_agent_busy`
    catches everything and reports not-busy.
    """
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.getcode(), resp.read()


def _is_agent_busy(
    host: str,
    a2a_port: int,
    agent: str,
    *,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
) -> bool:
    """True iff the sac sidecar's /_active route reports any tasks for ``agent``.

    Endpoint: ``http://{host}:{a2a_port}/agents/{agent}/_active``.

    Response shape: ``{"tasks": [{"id", "state", "last_event_at"}, ...]}``.
    Non-empty ``tasks`` → busy.

    Fail-open contract: on any request failure (timeout, 404, non-200,
    JSON parse error, missing ``tasks`` key, runner exception of any
    kind) return ``False``. Better to over-dispatch (and eat one 120 s
    sac-send timeout) than silently skip every round because the probe
    is misconfigured.
    """
    runner = http_runner or _default_http_runner
    url = f"http://{host}:{a2a_port}/agents/{agent}/_active"
    try:
        status, body = runner(url, _BUSY_PROBE_TIMEOUT_S)
    except Exception:  # stx-allow: fallback (reason: fail-open per docstring)
        return False
    if status != 200:
        return False
    try:
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return False
    return len(tasks) > 0


# ---------------------------------------------------------------------------
# state.db resolution — agent → (host, a2a_port)
# ---------------------------------------------------------------------------


def _resolve_agent_endpoint(
    agent: str,
    *,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[str, int] | None:
    """Return ``(host, a2a_port)`` for ``agent``'s live state.db row, or None.

    Uses ``sac db query --table=instances --where=... --json``. None is
    returned when the agent has no live row, no a2a_port, or sac db
    fails — the caller treats None as "can't probe, assume not busy"
    (fail-open, consistent with :func:`_is_agent_busy`).
    """
    runner = sac_runner or _default_sac_runner
    where = f"name='{agent}' AND ended_at IS NULL"
    args = [
        "db",
        "query",
        "--table",
        "instances",
        "--where",
        where,
        "--json",
        "--limit",
        "1",
    ]
    try:
        r = runner(args, input_text="")
    except Exception:  # stx-allow: fallback (reason: probe fail-open)
        return None
    if r.returncode != 0:
        return None
    try:
        rows = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    host = row.get("host")
    port = row.get("a2a_port")
    if not isinstance(host, str) or not host:
        return None
    if not isinstance(port, int) or port <= 0:
        return None
    return host, port


def build_fix_prompt(repo: str, reds: list[str]) -> str:
    """Return the agent-facing fix prompt for a red repo."""
    body = "\n".join(reds)
    return FIX_PROMPT_TEMPLATE.format(repo=repo, reds=body)


def dispatch_fix_turn(
    agent: str,
    repo: str,
    reds: list[str],
    *,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """Fire ``sac agents send <agent> <prompt>``. Returns combined output."""
    runner = sac_runner or _default_sac_runner
    prompt = build_fix_prompt(repo, reds)
    # Keep the same call shape as the bash prototype: prompt as a single
    # positional argument. sac's send command treats arg as the message
    # body. We don't pipe via stdin so quoting stays simple.
    r = runner(["agents", "send", agent, prompt], input_text="")
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(
            f"sac agents send {agent!r} failed (rc={r.returncode}): {out.strip()}"
        )
    return out


# ---------------------------------------------------------------------------
# Top-level pass
# ---------------------------------------------------------------------------


def run_once(
    *,
    only_agent: str | None = None,
    agents_to_repos: Mapping[str, str] | None = None,
    dry_run: bool = False,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    todo_api: _TodoApi | None = None,
    out=None,
) -> list[AgentResult]:
    """Run one ci-watch pass over every (or the named) agent.

    Returns a list of ``AgentResult`` so callers (and tests) can inspect
    what happened. Prints progress to ``out`` (default ``sys.stdout``) in
    the same human-readable format as the bash prototype.

    The ``todo_api`` seam lets tests pass a hand-rolled fake to verify
    the CI-fail → scitex-todo bookkeeping without importing scitex-todo
    at all (PA-306 / STX-NM* — no ``unittest.mock``). In production
    callers leave it ``None`` so :func:`_resolve_todo_api` lazy-imports
    scitex-todo on first need; if scitex-todo is not installed the hook
    short-circuits to no-op and the rest of the loop is unaffected.
    """
    if out is None:
        out = sys.stdout
    table = agents_to_repos if agents_to_repos is not None else AGENTS_TO_REPOS

    results: list[AgentResult] = []
    for agent in sorted(table):
        if only_agent and agent != only_agent:
            continue
        repo = table[agent]
        print(f"=== {agent} <- {repo} ===", file=out)
        try:
            reds = red_runs_for(repo, gh_runner=gh_runner)
        except RuntimeError as exc:
            print(f"  error: {exc}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=(),
                    dispatched=False,
                    dispatch_output="",
                    error=str(exc),
                )
            )
            continue

        red_names = [r.workflow for r in reds]

        if not reds:
            print("  all green", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=(),
                    dispatched=False,
                    dispatch_output="",
                )
            )
            continue

        print("  red workflows:", file=out)
        for r in reds:
            print(f"    - {r.workflow}", file=out)

        # CI-fail → scitex-todo. Fail-open so a scitex-todo glitch never
        # blocks the sac dispatch / fix-forward turn below. We file the
        # todo even in dry-run + agent-busy paths because the todo is
        # the *durable* record of the failure; the sac dispatch is the
        # *live* nudge. Either being skipped doesn't excuse the other.
        todos_filed: list[str] = []
        todos_already_open: list[str] = []
        for failing_run in reds:
            try:
                created = _create_todo_if_new(
                    agent=agent,
                    repo=repo,
                    failing_run=failing_run,
                    todo_api=todo_api,
                )
            except Exception as exc:  # stx-allow: fallback (reason: todo hook fail-open)
                # Surface a one-line diagnostic so the operator notices
                # if scitex-todo starts rejecting every call, but keep
                # the loop alive.
                print(f"  todo-hook: {failing_run.workflow}: {exc}", file=out)
                continue
            task_id = _todo_task_id_for(
                repo, failing_run.workflow, failing_run.head_sha
            )
            if created:
                todos_filed.append(task_id)
                print(f"  todo: filed {task_id}", file=out)
            else:
                todos_already_open.append(task_id)

        if dry_run:
            prompt = build_fix_prompt(repo, red_names)
            print(
                f"  [dry-run] would dispatch to {agent}:",
                file=out,
            )
            for line in prompt.splitlines():
                print(f"    | {line}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=tuple(red_names),
                    dispatched=False,
                    dispatch_output=prompt,
                    todos_filed=tuple(todos_filed),
                    todos_already_open=tuple(todos_already_open),
                )
            )
            continue

        # Skip when the agent has active work — prevents the 120s
        # sac-send timeout from cascading and overflowing the 10-min
        # cron interval. Endpoint and lookup are both fail-open so a
        # broken probe degrades to over-dispatch, not silent muting.
        endpoint = _resolve_agent_endpoint(agent, sac_runner=sac_runner)
        if endpoint is not None:
            host, port = endpoint
            if _is_agent_busy(host, port, agent):
                print(f"  skip: {agent} has active task(s)", file=out)
                results.append(
                    AgentResult(
                        agent=agent,
                        repo=repo,
                        red_workflows=tuple(red_names),
                        dispatched=False,
                        dispatch_output="",
                        todos_filed=tuple(todos_filed),
                        todos_already_open=tuple(todos_already_open),
                    )
                )
                continue

        print(f"  dispatching fix turn to {agent} ...", file=out)
        try:
            output = dispatch_fix_turn(agent, repo, red_names, sac_runner=sac_runner)
        except RuntimeError as exc:
            print(f"  error: {exc}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=tuple(red_names),
                    dispatched=False,
                    dispatch_output="",
                    error=str(exc),
                    todos_filed=tuple(todos_filed),
                    todos_already_open=tuple(todos_already_open),
                )
            )
            continue

        for line in output.splitlines()[-3:]:
            print(f"    {line}", file=out)
        results.append(
            AgentResult(
                agent=agent,
                repo=repo,
                red_workflows=tuple(red_names),
                dispatched=True,
                dispatch_output=output,
                todos_filed=tuple(todos_filed),
                todos_already_open=tuple(todos_already_open),
            )
        )

    return results


# EOF
