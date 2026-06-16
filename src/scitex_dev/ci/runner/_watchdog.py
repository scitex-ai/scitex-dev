"""``scitex-dev ci runner watchdog`` — observe-and-alert (NO silent fallback).

Run this on a schedule on the OPERATOR side (a systemd-timer / cron / agent
on your own host) — NOT as an HPC cron. Each tick checks, over the network,
that the self-hosted runner is ONLINE and the SLURM lease is alive.

Design (per operator directive 2026-06-16): fail loud, fail fast, no silent
fallback. On any problem the watchdog writes a single ``[ALERT]`` line to
stderr and exits non-zero. It DELIBERATELY never flips CI to a hosted
runner: a silent auto-switch would hide the outage — we would never realise
the self-hosted runner died. Switching to hosted stays a manual, announced
``scitex-dev ci runner use github``.
"""

from __future__ import annotations

import json as _json
import subprocess

import click

from . import config

_SQUEUE = "/apps/slurm/latest/bin/squeue"


def assess_health(
    online_runner_labels: list[list[str]],
    lease_running: bool,
    want_label: str = "scitex-ci",
) -> tuple[bool, list[str]]:
    """Pure health decision — no I/O, so it is unit-testable without mocks.

    Parameters
    ----------
    online_runner_labels : list[list[str]]
        Label lists of the currently-ONLINE runners.
    lease_running : bool
        Whether a RUNNING CI lease job exists.
    want_label : str
        The label CI workflows target (default ``scitex-ci``).

    Returns
    -------
    (healthy, alerts) : tuple[bool, list[str]]
        ``healthy`` is True only when a matching online runner AND a running
        lease are both present. ``alerts`` lists every problem found.
    """
    alerts: list[str] = []
    if not any(want_label in labels for labels in online_runner_labels):
        alerts.append(f"no ONLINE runner carrying label {want_label!r}")
    if not lease_running:
        alerts.append("no RUNNING SLURM CI lease")
    return (not alerts), alerts


def _online_runner_labels(repo: str) -> list[list[str]]:
    out = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/actions/runners",
            "--jq",
            '[.runners[] | select(.status=="online") | [.labels[].name]]',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        raise click.ClickException(f"gh api runners failed: {out.stderr.strip()}")
    return _json.loads(out.stdout.strip() or "[]")


def _lease_running(cfg: dict) -> bool:
    user = cfg["hpc"]["user"]
    jobname = cfg["ci_lease"]["jobname"]
    r = config.ssh_run(
        cfg,
        f"{_SQUEUE} -u {user} --name={jobname} --states=R --noheader -o '%i'",
    )
    if r.returncode != 0:
        raise click.ClickException(f"squeue over ssh failed: {r.stderr.strip()}")
    return bool(r.stdout.strip())


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit a JSON health report on stdout.",
    )
    @click.option(
        "--notify-cmd",
        default=None,
        help="Shell command run on ALERT, with the message as its "
        "last argument (escalation stays operator-side).",
    )
    def watchdog(as_json: bool, notify_cmd: str | None) -> None:
        """Check runner+lease health; FAIL LOUD on problems. Never flips to hosted.

        \b
        Exit code: 0 healthy, 1 unhealthy (so a scheduler surfaces it).
        Run it operator-side on a schedule — never as an HPC cron.
        """
        cfg = config.load_runner_config()
        repo = cfg["github"]["default_repo"]

        labels = _online_runner_labels(repo)
        lease = _lease_running(cfg)
        healthy, alerts = assess_health(labels, lease)

        if as_json:
            click.echo(
                _json.dumps({"healthy": healthy, "alerts": alerts, "repo": repo})
            )

        if healthy:
            if not as_json:
                click.echo("ok: scitex-ci runner online + SLURM lease running")
            return

        msg = (
            f"[ALERT] scitex-ci runner unhealthy for {repo}: "
            + "; ".join(alerts)
            + " — CI will NOT silently fall back to hosted. Fix the runner "
            "(scitex-dev ci runner renew / up) or switch explicitly with "
            "`scitex-dev ci runner use github`."
        )
        click.echo(msg, err=True)
        if notify_cmd:
            subprocess.run([notify_cmd, msg], timeout=30)
        raise SystemExit(1)
