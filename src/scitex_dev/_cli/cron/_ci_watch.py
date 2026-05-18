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
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Mapping

# ---------------------------------------------------------------------------
# Agent → owned repo map
# ---------------------------------------------------------------------------
# Edit this in-place when a new sac agent joins the fleet. Move to a
# config file when the list grows past ~10 entries (the bash prototype's
# threshold).
AGENTS_TO_REPOS: Mapping[str, str] = {
    "proj-scitex-stats": "ywatanabe1989/scitex-stats",
    "proj-scitex-types": "ywatanabe1989/scitex-types",
    "proj-scitex-dict": "ywatanabe1989/scitex-dict",
    "proj-scitex-str": "ywatanabe1989/scitex-str",
    "proj-scitex-datetime": "ywatanabe1989/scitex-datetime",
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

    def is_red(self) -> bool:
        return bool(self.red_workflows)


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


def red_workflows_for(
    repo: str,
    *,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> list[str]:
    """Return the workflow names whose latest develop run is ``failure``.

    Parses the JSON output of

        gh -R <repo> run list --branch develop --limit 12 \
            --json conclusion,workflowName,databaseId

    Only the most recent run per workflow is considered — ``gh`` returns
    runs newest-first, so the first occurrence of each ``workflowName``
    wins. Pure helper; no side-effects.

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
        "conclusion,workflowName,databaseId",
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
    reds: list[str] = []
    for entry in data:
        name = entry.get("workflowName")
        if not name or name in seen:
            continue
        seen.add(name)
        if entry.get("conclusion") == "failure":
            reds.append(name)
    return reds


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
    out=None,
) -> list[AgentResult]:
    """Run one ci-watch pass over every (or the named) agent.

    Returns a list of ``AgentResult`` so callers (and tests) can inspect
    what happened. Prints progress to ``out`` (default ``sys.stdout``) in
    the same human-readable format as the bash prototype.
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
            reds = red_workflows_for(repo, gh_runner=gh_runner)
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
            print(f"    - {r}", file=out)

        if dry_run:
            prompt = build_fix_prompt(repo, reds)
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
                    red_workflows=tuple(reds),
                    dispatched=False,
                    dispatch_output=prompt,
                )
            )
            continue

        print(f"  dispatching fix turn to {agent} ...", file=out)
        try:
            output = dispatch_fix_turn(agent, repo, reds, sac_runner=sac_runner)
        except RuntimeError as exc:
            print(f"  error: {exc}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=tuple(reds),
                    dispatched=False,
                    dispatch_output="",
                    error=str(exc),
                )
            )
            continue

        for line in output.splitlines()[-3:]:
            print(f"    {line}", file=out)
        results.append(
            AgentResult(
                agent=agent,
                repo=repo,
                red_workflows=tuple(reds),
                dispatched=True,
                dispatch_output=output,
            )
        )

    return results


# EOF
