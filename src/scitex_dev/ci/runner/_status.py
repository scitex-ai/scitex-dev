"""``scitex-dev ci runner status`` — runner state, CI_RUNS_ON, xdist tuning."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess

import click

from . import config


class XdistConstants:
    """Adaptive xdist tuning constants — single source of truth.

    These mirror the logic in ci.yml.template so the CLI and the template
    never drift.
    """

    BINS = [
        (32, 16),
        (128, 32),
    ]
    DEFAULT_FALLBACK = 16


def _runner_status(cfg: dict) -> dict:
    """Query GitHub API for the runner's online status."""
    repo = cfg["github"]["default_repo"]
    # The list-runners endpoint returns an OBJECT {total_count, runners: [...]},
    # so iterate `.runners[]` — a bare `.[]` walks the object's values (the
    # count int + the array) and the per-item object constructor then errors
    # ("expected an object but got: array"), which would make the preflight
    # gate falsely report the runner unreachable.
    gh_cmd = [
        "gh",
        "api",
        f"repos/{repo}/actions/runners",
        "--jq",
        "[.runners[] | {name, status, busy, labels: [.labels[]?.name]}]",
    ]
    result = subprocess.run(gh_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return {"error": result.stderr.strip()[:200]}
    try:
        runners = json.loads(result.stdout.strip()) if result.stdout.strip() else []
    except json.JSONDecodeError:
        return {"error": f"non-JSON from gh api: {result.stdout!r}"}
    return {"runners": runners}


def _ci_runs_on(cfg: dict) -> str:
    """Read the CI_RUNS_ON repo variable."""
    var_name = cfg["github"]["variable_name"]
    repo = cfg["github"]["default_repo"]
    gh_cmd = [
        "gh",
        "api",
        f"repos/{repo}/actions/variables/{var_name}",
        "--jq",
        ".value",
    ]
    result = subprocess.run(gh_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return "(not set)"
    return result.stdout.strip().strip('"')


def _lease_status(cfg: dict) -> dict:
    """Query SLURM for the CI lease job status."""
    user = cfg["hpc"]["user"]
    jobname = cfg["ci_lease"]["jobname"]
    target = config._ssh_target(cfg)
    cmd = (
        f"ssh {config.SSH_MUX_OPTS_STR} "
        f"{target} "
        f"'/apps/slurm/latest/bin/squeue -u {user} --name={jobname} "
        f'--noheader -o "%i %T %M %L"\''
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
    if result.returncode != 0:
        return {"error": result.stderr.strip()[:200]}

    rows = []
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        rows.append(
            {
                "jobid": parts[0],
                "state": parts[1],
                "time_used": parts[2],
                "time_left": parts[3],
            }
        )
    return {"jobs": rows}


def _compute_xdist_n(n_tests: int, nproc: int | None = None) -> int:
    """Compute the adaptive xdist N for a given test count.

    Mirrors the logic in ci.yml.template.
    """
    if nproc is None:
        nproc = _nproc()
    phys_cap = max(1, nproc // 2)
    if n_tests <= 32:
        return min(16, phys_cap)
    elif n_tests <= 128:
        return min(32, phys_cap)
    else:
        return phys_cap


def _nproc() -> int:
    try:
        return max(
            1, len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 4
        )
    except Exception:
        import os  # type: ignore[no-redef]

        return os.cpu_count() or 4


def _xdist_tuning_table() -> list[dict]:
    """Return the xdist tuning table for --explain."""
    nproc = _nproc()
    phys_cap = max(1, nproc // 2)
    rows: list[dict] = []
    for limit, n in XdistConstants.BINS:
        rows.append(
            {
                "test_range": f"≤{limit}",
                "xdist_n": min(n, phys_cap),
                "cap": phys_cap,
            }
        )
    rows.append(
        {
            "test_range": f">{XdistConstants.BINS[-1][0]}",
            "xdist_n": phys_cap,
            "cap": phys_cap,
            "note": f"nproc={nproc} // 2 = {phys_cap}",
        }
    )
    return rows


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Output as structured JSON.",
    )
    @click.option(
        "--explain",
        is_flag=True,
        default=False,
        help="Include the adaptive xdist tuning table.",
    )
    def status_cmd(as_json: bool, explain: bool) -> None:
        """Show runner state, CI_RUNS_ON, lease status, xdist info.

        \b
        Reports per-topic:
          runner     — online/offline status from GitHub API
          ci_runs_on — the active CI_RUNS_ON variable value
          lease      — SLURM CI lease job status (jobid, state, time_left)
          xdist      — adaptive xdist worker table (with --explain)

        \b
        Example:
          $ scitex-dev ci runner status
          $ scitex-dev ci runner status --explain --json
        """
        import os  # noqa: E402

        cfg = config.load_runner_config()
        output: dict = {}

        # Runner status
        output["runner"] = _runner_status(cfg)

        # CI_RUNS_ON
        output["ci_runs_on"] = _ci_runs_on(cfg)

        # Lease status
        output["lease"] = _lease_status(cfg)

        # xdist tuning (always shown; --explain adds context)
        output["xdist_tuning"] = _xdist_tuning_table()

        # Context: nproc
        output["nproc"] = _nproc()
        output["runner_config"] = {
            "name": cfg["runner"]["name"],
            "labels": cfg["runner"]["labels"],
            "xdist_default_fallback": XdistConstants.DEFAULT_FALLBACK,
        }

        if as_json:
            click.echo(json.dumps(output, indent=2, default=str))
            return

        # Human-readable
        click.secho(
            f"runner: {cfg['runner']['name']} ({', '.join(str(l) for l in cfg['runner']['labels'])})",
            bold=True,
        )

        runners_info = output["runner"].get("runners", [])
        online = [r for r in runners_info if r.get("status") == "online"]
        click.echo(f"  runners online: {len(online)}/{len(runners_info)}")
        if output["runner"].get("error"):
            click.echo(f"  gh api error: {output['runner']['error'][:100]}")

        click.echo(f"  CI_RUNS_ON: {output['ci_runs_on']}")

        lease_info = output["lease"].get("jobs", [])
        running = [j for j in lease_info if j["state"] == "RUNNING"]
        pending = [j for j in lease_info if j["state"] == "PENDING"]
        click.echo(f"  lease: {len(running)} running, {len(pending)} pending")
        for j in running:
            click.echo(f"    job {j['jobid']}: {j['state']} (left: {j['time_left']})")

        click.echo()
        click.echo("  xdist tuning:")
        click.secho(
            f"    {'test_range':12s} {'xdist_n':8s} {'cap':6s} {'note'}", fg="cyan"
        )
        for row in output["xdist_tuning"]:
            note = row.get("note", "")
            click.echo(
                f"    {row['test_range']:12s} {row['xdist_n']:8d} {row['cap']:6d} {note}"
            )


# EOF
