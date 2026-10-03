"""Read-only organization runner policy; label liveness is not authorization.

Operator 2026-10-03: compute02/03/04 serve organization members only.
Public/external contributions default to hosted. Policy corrections belong to
reviewed workflow/group authority, never a liveness probe's registration loop.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from urllib.parse import urlsplit

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand

ORG = "scitex-ai"
CPU_RUNNERS = ("scitex-ci-02", "scitex-ci-03", "scitex-ci-04")
HOSTED_RUNS_ON = '["ubuntu-latest"]'


def parse_repository(remote: str) -> str:
    """Parse only exact GitHub origins, retaining dot-prefixed repository names."""
    if remote.startswith("git@github.com:"):
        path = remote[len("git@github.com:") :]
    else:
        url = urlsplit(remote)
        if url.scheme not in ("https", "ssh") or url.hostname != "github.com" or url.query or url.fragment:
            raise ValueError("origin is not an exact GitHub repository")
        path = url.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", path) or path.split("/")[1] in (".", ".."):
        raise ValueError("origin has no unambiguous owner/repository")
    return path


def organization_repository(repo: str) -> bool:
    return (bool(re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo))
            and repo.split("/")[1] not in (".", "..") and repo.split("/")[0].lower() == ORG)


def default_runs_on(repo: str) -> str:
    """Registration defaults hosted; self-hosted is an explicit qualified opt-in."""
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo) or repo.split("/")[1] in (".", ".."):
        raise ValueError("invalid owner/repository")
    return HOSTED_RUNS_ON


def assess_pool(runners, groups, group_runner_ids, *, expected_workflows=None) -> dict:
    """Classify observed group/registration ACLs against a reviewed contract.

    Busy is healthy registered processing state. Last actual job timestamps are
    separate observations and stay unknown until a job API supplies evidence.
    """
    report = {"state": "unknown", "violations": [], "unknown": [], "groups": [],
              "activity": {"busy_runners": [], "last_completed_job_at": None,
                           "completed_job_evidence": "not-observed"}}
    if not isinstance(runners, list) or not isinstance(groups, list):
        report["unknown"].append("organization runner/group inventory unavailable")
        return report
    selected = [r for r in runners if isinstance(r, dict) and r.get("name") in CPU_RUNNERS]
    for name in CPU_RUNNERS:
        matches = [r for r in selected if r.get("name") == name]
        if len(matches) != 1 or type(matches[0].get("id")) is not int:
            report["violations"].append(f"{name}: exactly one organization registration required")
            continue
        runner = matches[0]
        if runner.get("status") != "online":
            report["violations"].append(f"{name}: organization runner is not online")
        if runner.get("busy") is True:
            report["activity"]["busy_runners"].append(name)
        elif runner.get("busy") is not False:
            report["unknown"].append(f"{name}: busy state unavailable")
        ids = []
        for group in groups:
            gid = group.get("id") if isinstance(group, dict) else None
            members = group_runner_ids.get(gid)
            if not isinstance(members, list):
                report["unknown"].append(f"group {gid}: runner membership unavailable")
            elif runner["id"] in members:
                ids.append(gid)
        if len(ids) != 1:
            if not report["unknown"]:
                report["violations"].append(f"{name}: exactly one organization group required")
            continue
        group = next(g for g in groups if g["id"] == ids[0])
        if not any(g["id"] == group["id"] for g in report["groups"]):
            report["groups"].append({k: group.get(k) for k in (
                "id", "name", "visibility", "allows_public_repositories",
                "restricted_to_workflows", "selected_workflows")})
    expected = tuple(expected_workflows or ())
    for group in report["groups"]:
        if (group.get("id") != 6 or group.get("name") != "Organization"
                or group.get("visibility") != "all" or group.get("allows_public_repositories") is not True):
            report["violations"].append("organization group identity/repository availability differs from reviewed policy")
        refs = group.get("selected_workflows")
        if group.get("restricted_to_workflows") is not True or not isinstance(refs, list) or not refs:
            report["violations"].append(f"group {group['id']}: unrestricted workflow access")
            continue
        if any(not isinstance(ref, str) or not re.fullmatch(
                rf"{ORG}/\.github/\.github/workflows/[A-Za-z0-9_-]+\.ya?ml@[a-f0-9]{{40}}", ref)
               for ref in refs):
            report["violations"].append(f"group {group['id']}: workflow access is not pinned to organization revisions")
        if not expected:
            report["unknown"].append("reviewed membership-admission workflow contract absent")
        elif set(refs) != set(expected):
            report["violations"].append(f"group {group['id']}: selected workflows differ from reviewed membership contract")
    report["state"] = "violation" if report["violations"] else "unknown" if report["unknown"] else "conformant"
    return report


def _api(endpoint: str):
    """Capture credentials/error bodies privately; persist only fixed diagnostics."""
    try:
        p = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=7)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode:
        return None
    try:
        return json.loads(p.stdout)
    except (ValueError, TypeError):
        return None


def _rows(payload, key):
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        return None
    if payload.get("total_count") != len(payload[key]):
        return None  # Incomplete/paginated inventory is UNKNOWN, not empty.
    return payload[key]


def collect_activity(runners, api) -> dict:
    """Bounded public Dev CI sample; never imply an organization-wide history.

    The runner API supplies present busy state, not a last-job timestamp. Three
    latest runs in this package's public repository provide independent job
    evidence when available. Missing samples stay unknown, including age.
    """
    result = {"repository": f"{ORG}/scitex-dev", "run_limit": 3,
              "organization_wide": False, "sample_complete": False, "jobs": [],
              "last_completed_job_at": None, "last_completed_job_age_s": None,
              "completed_job_evidence": "not-observed"}
    payload = api(f"repos/{ORG}/scitex-dev/actions/runs?per_page=3")
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list) or len(runs) > 3:
        return result
    ids = {r["id"]: r["name"] for r in runners or []
           if isinstance(r, dict) and type(r.get("id")) is int and r.get("name") in CPU_RUNNERS}
    complete = True
    now = dt.datetime.now(dt.timezone.utc)
    latest = None
    for run in runs:
        if not isinstance(run, dict) or type(run.get("id")) is not int:
            complete = False
            continue
        jobs = _rows(api(f"repos/{ORG}/scitex-dev/actions/runs/{run['id']}/jobs?per_page=100"), "jobs")
        if jobs is None:
            complete = False
            continue
        for job in jobs:
            if (not isinstance(job, dict) or type(job.get("id")) is not int
                    or type(job.get("runner_id")) is not int or job["runner_id"] not in ids
                    or job.get("status") != "completed"):
                continue
            try:
                completed = dt.datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
                if completed.tzinfo is None or completed > now:
                    raise ValueError
            except (KeyError, AttributeError, TypeError, ValueError):
                complete = False
                continue
            result["jobs"].append({"run_id": run["id"], "job_id": job["id"],
                "runner_id": job["runner_id"], "runner_name": ids[job["runner_id"]],
                "completed_at": completed.isoformat()})
            if latest is None or completed > latest:
                latest = completed
    result["sample_complete"] = complete
    if latest is not None:
        result.update(last_completed_job_at=latest.isoformat(),
                      last_completed_job_age_s=(now - latest).total_seconds(),
                      completed_job_evidence="public-job-api-sample")
    return result


def collect_policy() -> dict:
    from ._policy_contract import qualify_workflows
    runners = _rows(_api(f"orgs/{ORG}/actions/runners?per_page=100"), "runners")
    groups = _rows(_api(f"orgs/{ORG}/actions/runner-groups?per_page=100"), "runner_groups")
    memberships = {}
    for group in groups or []:
        if not isinstance(group, dict) or type(group.get("id")) is not int:
            groups = None
            break
        rows = _rows(_api(f"orgs/{ORG}/actions/runner-groups/{group['id']}/runners?per_page=100"), "runners")
        memberships[group["id"]] = None if rows is None else [r.get("id") for r in rows if isinstance(r, dict)]
    cpu_ids = {r.get("id") for r in runners or [] if isinstance(r, dict) and r.get("name") in CPU_RUNNERS}
    selected_groups = [g for g in groups or [] if isinstance(memberships.get(g["id"]), list)
                       and cpu_ids.intersection(memberships[g["id"]])]
    contract = qualify_workflows(selected_groups, _api)
    report = assess_pool(runners, groups, memberships, expected_workflows=contract["expected"])
    report["violations"].extend(contract["violations"])
    report["unknown"].extend(contract["unknown"])
    report["state"] = "violation" if report["violations"] else "unknown" if report["unknown"] else "conformant"
    report["workflow_source"] = contract["source"]
    report["activity"].update(collect_activity(runners, _api))
    report["organization"] = ORG
    report["observed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["registrations"] = [{k: r.get(k) for k in ("id", "name", "status", "busy")}
                               for r in runners or [] if isinstance(r, dict) and r.get("name") in CPU_RUNNERS]
    return report


def register(group: click.Group) -> None:
    @group.command("validate-policy", cls=SpecCommand, help_spec=CliHelp(
        summary="Observe organization runner identity and reviewed workflow access.",
        description="Read-only, cron-safe: unknown observations and policy violations exit nonzero. No registration, ACL, workflow or runner lifecycle mutation.",
        examples=(Example("{prog} ci runner validate-policy --json", "Record the current policy and independent activity observations."),)))
    @click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable policy receipt.")
    def validate_policy_cmd(as_json: bool) -> None:
        report = collect_policy()
        if as_json:
            click.echo(json.dumps(report, sort_keys=True))
        else:
            click.echo(f"[{report['state'].upper()}] {ORG} organization runner policy")
            for reason in report["violations"] + report["unknown"]:
                click.echo(f"  {reason}")
            click.echo(f"  busy: {', '.join(report['activity']['busy_runners']) or 'none observed'}")
            click.echo(f"  last completed job (bounded public Dev sample): {report['activity']['last_completed_job_at'] or 'unknown'}")
        if report["state"] != "conformant":
            raise click.exceptions.Exit(1)
