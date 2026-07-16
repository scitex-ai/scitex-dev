"""Run-level orchestration: resolve a target to run id(s), fetch, distil.

The only network-touching layer. :func:`run_gh` is the default ``gh``
seam; every resolver accepts ``run_gh=None`` and falls back to it, so a
test injects a plain callable and stays offline. :func:`explain_ci_run`
is the public entry a consumer's thin verb calls: a PR number / run id /
branch / nothing in, the distilled failing run(s) out.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Optional

from ._model import CIWhyError, GhRunner, RunFailures
from ._parse import parse_failed_log, split_log_by_job

# --log-failed can be a few MB; give the fetch room but stay bounded.
_GH_TIMEOUT_S = 90

# A PR number is small; a run id is a 10+ digit database id. Anything at
# or above this magnitude is treated as a run id, below it as a PR number.
_RUN_ID_MIN = 10_000_000

_FAILED_JOB_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure"}
_RUN_ID_IN_LINK = re.compile(r"/actions/runs/(\d+)")


def run_gh(args: list[str], *, _run=subprocess.run) -> str:
    """Default ``gh`` seam: run ``gh <args>`` and return stdout text.

    The one place the network is touched. Returns stdout even on a
    non-zero exit *when stdout is non-empty* — ``gh pr checks`` exits
    non-zero precisely when checks fail, yet still prints the JSON we
    want. A non-zero exit with no output (bad run id, auth failure, gh
    missing) raises :class:`CIWhyError`.
    """
    try:
        proc = _run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CIWhyError(
            "gh CLI not found on PATH — install GitHub CLI: https://cli.github.com"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise CIWhyError(f"gh {' '.join(args)} failed to run: {exc}") from exc
    out = proc.stdout or ""
    if proc.returncode != 0 and not out.strip():
        err = (proc.stderr or "").strip() or f"exited {proc.returncode}"
        raise CIWhyError(f"gh {' '.join(args)}: {err}")
    return out


def _resolve_gh(gh: Optional[GhRunner]) -> GhRunner:
    """Fall back to the default :func:`run_gh` seam when none is injected."""
    return gh if gh is not None else run_gh


def _repo_args(repo: Optional[str]) -> list[str]:
    return ["-R", repo] if repo else []


def _current_branch(_run=subprocess.run) -> str:
    try:
        proc = _run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CIWhyError(f"could not determine current branch: {exc}") from exc
    branch = (proc.stdout or "").strip()
    if proc.returncode != 0 or not branch:
        raise CIWhyError(
            "not in a git checkout (or detached HEAD) — pass a PR number, "
            "run id, or branch explicitly"
        )
    return branch


def _pr_failing_run_ids(pr: str, *, gh: GhRunner, repo: Optional[str]) -> list[str]:
    raw = gh(
        ["pr", "checks", pr, *_repo_args(repo), "--json", "name,state,link,bucket"]
    )
    try:
        checks = json.loads(raw or "[]")
    except ValueError as exc:
        raise CIWhyError(f"could not parse gh pr checks JSON for PR {pr}") from exc
    run_ids: list[str] = []
    for c in checks or []:
        failed = c.get("bucket") == "fail" or str(c.get("state", "")).upper() in {
            "FAILURE",
            "ERROR",
            "CANCELLED",
            "TIMED_OUT",
        }
        if not failed:
            continue
        m = _RUN_ID_IN_LINK.search(str(c.get("link", "")))
        if m and m.group(1) not in run_ids:
            run_ids.append(m.group(1))
    return run_ids


def _branch_latest_run_id(
    branch: str, *, gh: GhRunner, repo: Optional[str]
) -> list[str]:
    raw = gh(
        [
            "run",
            "list",
            *_repo_args(repo),
            "-b",
            branch,
            "-L",
            "1",
            "--json",
            "databaseId",
        ]
    )
    try:
        runs = json.loads(raw or "[]")
    except ValueError as exc:
        raise CIWhyError(
            f"could not parse gh run list JSON for branch {branch}"
        ) from exc
    if not runs:
        raise CIWhyError(f"no workflow runs found for branch '{branch}'")
    return [str(runs[0]["databaseId"])]


def resolve_run_ids(
    target: Optional[str],
    *,
    run_gh: Optional[GhRunner] = None,
    repo: Optional[str] = None,
) -> list[str]:
    """Resolve a PR number / run id / branch / nothing to failing run id(s).

    * empty  -> the latest run for the current git branch;
    * a run id (>= 8 digits) -> itself;
    * a PR number -> the run id(s) behind its failing checks;
    * anything else -> the latest run for that branch name.
    """
    gh = _resolve_gh(run_gh)
    target = (target or "").strip()
    if not target:
        return _branch_latest_run_id(_current_branch(), gh=gh, repo=repo)
    if target.isdigit():
        if int(target) >= _RUN_ID_MIN:
            return [target]
        return _pr_failing_run_ids(target, gh=gh, repo=repo)
    return _branch_latest_run_id(target, gh=gh, repo=repo)


def explain_run(
    run_id: str, *, run_gh: Optional[GhRunner] = None, repo: Optional[str] = None
) -> RunFailures:
    """Fetch + distil every failing job of a single run."""
    gh = _resolve_gh(run_gh)
    meta_raw = gh(
        [
            "run",
            "view",
            str(run_id),
            *_repo_args(repo),
            "--json",
            "jobs,displayTitle,headBranch,conclusion,url,workflowName",
        ]
    )
    try:
        meta = json.loads(meta_raw or "{}")
    except ValueError as exc:
        raise CIWhyError(f"could not parse gh run view JSON for run {run_id}") from exc
    run = RunFailures(
        run_id=str(run_id),
        workflow=meta.get("workflowName", ""),
        title=meta.get("displayTitle", ""),
        branch=meta.get("headBranch", ""),
        url=meta.get("url", ""),
    )
    failing = [
        j
        for j in (meta.get("jobs") or [])
        if str(j.get("conclusion", "")).lower() in _FAILED_JOB_CONCLUSIONS
    ]
    if not failing:
        return run

    by_job = split_log_by_job(
        gh(["run", "view", str(run_id), *_repo_args(repo), "--log-failed"])
    )
    for j in failing:
        name = j.get("name", "")
        jf = parse_failed_log(by_job.get(name, ""), job_name=name, url=j.get("url", ""))
        if jf.signal == "none":
            steps = [
                s.get("name", "?")
                for s in (j.get("steps") or [])
                if str(s.get("conclusion", "")).lower() == "failure"
            ]
            if steps:
                jf.errors.append("failed step: " + ", ".join(steps))
        run.failures.append(jf)
    return run


def explain_ci_run(
    target: Optional[str],
    *,
    run_gh: Optional[GhRunner] = None,
    repo: Optional[str] = None,
) -> list[RunFailures]:
    """Resolve ``target`` and distil the failing run(s) behind it.

    A PR number can front more than one failing run (one per matrix
    workflow), so this returns a list; a bare run id yields a one-element
    list. This is the SSOT entry a consumer's thin ``ci why`` verb calls.
    """
    gh = _resolve_gh(run_gh)
    return [
        explain_run(rid, run_gh=gh, repo=repo)
        for rid in resolve_run_ids(target, run_gh=gh, repo=repo)
    ]


def render_text(run: RunFailures) -> str:
    """Render one run's failures as compact human text (per-job blocks)."""
    if not run.failures:
        return "no failures"
    out: list[str] = []
    for jf in run.failures:
        out.append(f"{jf.job}{jf.context()}")
        out.extend(f"  {line}" for line in jf.primary_lines())
        if jf.url:
            out.append(f"  -> {jf.url}")
    return "\n".join(out)


__all__ = [
    "run_gh",
    "resolve_run_ids",
    "explain_run",
    "explain_ci_run",
    "render_text",
]
