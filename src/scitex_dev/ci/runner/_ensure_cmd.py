#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ci runner ensure`` — the click layer for the lifecycle SOLVER.

Holds ONLY the CLI wiring: the command's options, its :class:`CliHelp` spec,
and the rendering of an :class:`~._ensure.EnsureResult`. The solver itself
(pool resolution, lease decisions, restart orchestration) lives in
:mod:`._ensure` and stays independently importable + testable.
"""

from __future__ import annotations

import json

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from . import _fleet, config
from ._ensure import _ensure_dry_run, desired_runners, run_ensure


def register(group: click.Group) -> None:
    @group.command(
        "ensure",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Keep CI runners alive across the SLURM walltime (the SOLVER).",
            description=(
                "\b\n"
                "Idempotent + cron-safe. One pass:\n"
                "  1. Ensure a scitex-hpc *persistent* reservation backs CI\n"
                "     (book if absent; cancel+rebook if the allocation died;\n"
                "     the persistent reservation's own SIGUSR1 auto-resubmit\n"
                "     + this pass's `reservations refresh` bridge the 7-day\n"
                "     walltime).\n"
                "  2. For each desired runner GitHub reports offline/missing,\n"
                "     restart it on the reservation's node via the launcher\n"
                "     (same path as `up`).\n"
                "  3. No-op when the reservation is healthy and N runners are\n"
                "     online.\n"
                "\n"
                "With --fleet (or reservation.fleet: true in config), ALSO "
                "keep every per-repo runner on the lease alive: in ONE "
                "`reservations exec` to the node, auto-discover each "
                "actions-runner-* home and relaunch any whose Runner.Listener "
                "process is dead — so the ~60-runner self-hosted fleet "
                "doesn't erode as runners die. One cron tick -> lease + ALL "
                "runners.\n"
                "\n"
                "\b\n"
                "Suggested cron (well inside the 7-day window):\n"
                "  */30 * * * *  scitex-dev ci runner ensure --fleet"
            ),
            examples=(
                Example("{prog} ci runner ensure", "One idempotent solver pass."),
                Example(
                    "{prog} ci runner ensure --dry-run --json",
                    "Report decisions without acting.",
                ),
                Example(
                    "{prog} ci runner ensure --fleet",
                    "Lease + every per-repo runner on the node.",
                ),
                Example(
                    "{prog} ci runner ensure --fleet --dry-run",
                    "Report fleet decisions only.",
                ),
            ),
        ),
    )
    @click.option(
        "--launcher",
        default=None,
        help="Path to launcher.sh on the HPC host. Default: shipped copy.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Report the decisions (book/rebook/noop + which runners are "
        "offline) WITHOUT booking or restarting anything.",
    )
    @click.option(
        "--fleet",
        "fleet",
        is_flag=True,
        default=False,
        help="ALSO sweep ALL per-repo runners on the lease node: in ONE "
        "`reservations exec`, auto-discover every actions-runner-* home and "
        "relaunch any whose Runner.Listener is dead (keeps the ~60-runner "
        "self-hosted fleet alive). Auto-on when reservation.fleet: true.",
    )
    @click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
    def ensure_cmd(
        launcher: str | None, dry_run: bool, fleet: bool, as_json: bool
    ) -> None:
        cfg = config.load_runner_config()
        pool = desired_runners(cfg)

        if dry_run:
            result = _ensure_dry_run(cfg, pool)
        else:
            result = run_ensure(cfg, pool, launcher_path=launcher)

        # Fleet pass: keep ALL per-repo runners on the lease alive (one
        # `reservations exec` to the node — no per-repo ssh from this host).
        # Runs when --fleet is passed OR the config opts in (reservation.fleet:
        # true), so the existing */30 cron picks it up once the knob is set.
        fleet_result = None
        if fleet or _fleet.fleet_enabled(cfg):
            if result.lease_node:
                fleet_result = _fleet.run_fleet_ensure(
                    cfg,
                    node=result.lease_node,
                    dry_run=dry_run,
                    launcher_path=launcher,
                )
            else:
                # No allocated node yet (freshly booked / PENDING); the
                # fleet sweep needs a node to ssh to. Defer to the next tick.
                click.echo(
                    "fleet: lease has no allocated node yet; deferring fleet "
                    "sweep to the next pass.",
                    err=True,
                )

        if as_json:
            payload = {
                "lease_action": result.lease_action,
                "lease_node": result.lease_node,
                "restarted": result.restarted,
                "online": result.online,
                "desired": [d.name for d in pool],
                "dry_run": dry_run,
            }
            if fleet_result is not None:
                payload["fleet"] = {
                    "alive": fleet_result.alive,
                    "restarted": fleet_result.restarted,
                    "would_restart": fleet_result.would_restart,
                    "failed": fleet_result.failed,
                }
            click.echo(json.dumps(payload, indent=2))
            return

        click.echo(f"lease: {result.lease_action} (node={result.lease_node or '-'})")
        if result.restarted:
            click.echo(f"restarted: {', '.join(result.restarted)}")
        click.echo(
            f"online: {len(result.online)}/{len(pool)} "
            f"({', '.join(result.online) or 'none'})"
        )
        if fleet_result is not None:
            fr = fleet_result
            n_total = fr.total
            if dry_run:
                click.echo(
                    f"fleet: alive={len(fr.alive)} "
                    f"would_restart={len(fr.would_restart)} "
                    f"failed={len(fr.failed)} (of {n_total} discovered)"
                )
            else:
                click.echo(
                    f"fleet: alive={len(fr.alive)} "
                    f"restarted={len(fr.restarted)} "
                    f"failed={len(fr.failed)} (of {n_total} discovered)"
                )


# EOF
