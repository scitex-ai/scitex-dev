#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem daemon {list,run}``.

Minimal surface for daemon-kind jobs: list them, and run one in the
foreground (the operator/supervisor is responsible for backgrounding).
"""

from __future__ import annotations

import subprocess

import click


def register(ecosystem) -> None:
    @ecosystem.group("daemon", invoke_without_command=True)
    @click.pass_context
    def daemon(ctx):
        """Federated daemon (long-running) jobs across the ecosystem.

        \b
        Verbs:
          list  — show all discovered daemon-kind jobs
          exec  — run one daemon job in the foreground
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @daemon.command("list")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def daemon_list(as_json):
        """List all discovered daemon-kind jobs.

        \b
        Example:
          $ scitex-dev ecosystem daemon list
        """
        from ....jobs import jobs_of_kind

        jobs = jobs_of_kind("daemon")
        if as_json:
            import json

            click.echo(
                json.dumps(
                    [
                        {
                            "name": j.name,
                            "command": j.command,
                            "description": j.description,
                        }
                        for j in jobs
                    ]
                )
            )
            return
        if not jobs:
            click.echo("No daemon-kind jobs discovered.")
            return
        for j in jobs:
            click.echo(f"  {j.name:30s} {j.command}")
            click.echo(f"  {'':30s} {j.description}")

    @daemon.command("exec")
    @click.argument("name")
    def daemon_exec(name):
        """Execute the daemon job NAME in the foreground.

        \b
        Blocks until the process exits; the caller is responsible for
        backgrounding / supervision (systemd, tmux, &, ...).

        \b
        Example:
          $ scitex-dev ecosystem daemon exec my-pkg.watcher
        """
        from ....jobs import jobs_of_kind

        jobs = {j.name: j for j in jobs_of_kind("daemon")}
        job = jobs.get(name)
        if job is None:
            known = ", ".join(sorted(jobs)) or "(none)"
            raise click.ClickException(
                f"unknown daemon job: {name!r}. Known jobs: {known}"
            )
        click.echo(f"running daemon {name!r}: {job.command}", err=True)
        raise SystemExit(subprocess.call(job.command, shell=True))


# EOF
