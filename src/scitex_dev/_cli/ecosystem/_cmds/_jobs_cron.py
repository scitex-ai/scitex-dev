#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem cron {list,install,uninstall}``.

Federated cron management: aggregates cron-kind ``JobSpec``s from every
ecosystem package (via the ``scitex_dev.jobs`` entry-point group plus
scitex-dev's own built-ins) and materialises them into an idempotent
BEGIN/END managed crontab block.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register(ecosystem) -> None:
    @ecosystem.group(
        "cron",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Federated cron jobs across the SciTeX ecosystem.",
            description=(
                "Aggregates cron-kind jobs from every package registered "
                "under the `scitex_dev.jobs` entry-point group (plus "
                "scitex-dev's built-ins) and materialises them into a "
                "single idempotent crontab block. Verbs: `list` shows "
                "all discovered cron jobs + source package; `install` "
                "writes the managed crontab block (idempotent); "
                "`uninstall` removes the managed block (or one line); "
                "`exec` runs one federated job's body directly.",
            ),
        ),
    )
    @click.pass_context
    def cron(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @cron.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List all discovered cron-kind jobs.",
            examples=(
                Example("{prog} ecosystem cron list", "Human-readable list."),
                Example("{prog} ecosystem cron list --json", "Structured JSON."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def cron_list(as_json):
        from ....jobs import jobs_of_kind

        jobs = jobs_of_kind("cron")
        if as_json:
            import json

            click.echo(
                json.dumps(
                    [
                        {
                            "name": j.name,
                            "schedule": j.schedule,
                            "description": j.description,
                            "source": _source_of(j.name),
                        }
                        for j in jobs
                    ]
                )
            )
            return
        if not jobs:
            click.echo("No cron-kind jobs discovered.")
            return
        for j in jobs:
            click.echo(f"  {j.name:30s} {j.schedule:16s} [{_source_of(j.name)}]")
            click.echo(f"  {'':30s} {j.description}")

    @cron.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Write the managed crontab block for cron-kind jobs.",
            description=(
                "Idempotent: the block delimited by `# >>> "
                "scitex-dev-ecosystem ... >>>` / `# <<< ... <<<` is "
                "replaced in place — re-running never duplicates lines.",
            ),
            examples=(
                Example("{prog} ecosystem cron install --dry-run", "Preview only."),
                Example("{prog} ecosystem cron install --yes", "Write the block."),
                Example(
                    "{prog} ecosystem cron install --name ci-watch --yes",
                    "Install just one job.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Install only the named job.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the managed block that would be written; do not touch crontab.",
    )
    @click.option(
        "-y", "--yes", is_flag=True, default=False, help="Confirm the crontab write."
    )
    def cron_install(name, dry_run, yes):
        from ....jobs import jobs_of_kind
        from ....jobs import _cron_block as cb
        from ...cron import _crontab

        jobs = jobs_of_kind("cron")
        if name is not None:
            jobs = [j for j in jobs if j.name == name]
            if not jobs:
                raise click.ClickException(f"no cron-kind job named {name!r}")

        if dry_run:
            click.echo(cb.render_block(jobs))
            return

        if not yes:
            click.echo("Refusing to write to crontab without --yes/-y.", err=True)
            raise SystemExit(2)

        try:
            current = _crontab.read_crontab()
            new = cb.upsert_block(current, jobs)
            _crontab.write_crontab(new)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(f"installed {len(jobs)} cron job(s) into managed block.")

    @cron.command(
        "uninstall",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Remove the managed crontab block (or one line).",
            examples=(
                Example("{prog} ecosystem cron uninstall --dry-run", "Preview only."),
                Example("{prog} ecosystem cron uninstall --yes", "Remove the block."),
                Example(
                    "{prog} ecosystem cron uninstall --name ci-watch --yes",
                    "Remove just one line.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Remove only the named line.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the crontab that would result; do not touch crontab.",
    )
    @click.option(
        "-y", "--yes", is_flag=True, default=False, help="Confirm the crontab write."
    )
    def cron_uninstall(name, dry_run, yes):
        from ....jobs import _cron_block as cb
        from ...cron import _crontab

        if dry_run:
            current = _crontab.read_crontab()
            if name is not None:
                new, _ = cb.remove_line(current, name)
            else:
                new = cb.upsert_block(current, [])
            click.echo(new, nl=False)
            return

        if not yes:
            click.echo("Refusing to write to crontab without --yes/-y.", err=True)
            raise SystemExit(2)

        try:
            current = _crontab.read_crontab()
            if name is not None:
                new, removed = cb.remove_line(current, name)
                if removed == 0:
                    raise click.ClickException(f"no managed line named {name!r}")
                _crontab.write_crontab(new)
                click.echo(f"removed managed line {name!r}.")
            else:
                new = cb.upsert_block(current, [])
                _crontab.write_crontab(new)
                click.echo("removed managed cron block.")
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

    @cron.command(
        "exec",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Execute the body of the federated cron job NAME.",
            description=(
                "Discovers the JobSpec via the `scitex_dev.jobs` "
                "entry-point federation (the SAME aggregator that "
                "`ecosystem cron install` uses), then dispatches to the "
                "owning module's run_once. This is the verb the "
                "materialised crontab line invokes; operators can also "
                "run it interactively to test a job without waiting "
                "for the next cron tick.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem cron exec deploy-freshness",
                    "Dry-run the job body.",
                ),
                Example(
                    "{prog} ecosystem cron exec deploy-freshness --apply",
                    "Actually repair drift.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option(
        "--apply",
        is_flag=True,
        default=False,
        help=(
            "(deploy-freshness) Repair drift instead of dry-run. WHEEL "
            "leaf (installed version trails latest PyPI): run `pip install "
            "-U <pkg>` + `systemctl --user restart <unit>`. EDITABLE leaf "
            "(PEP 660 install whose git source is newer than the unit's "
            "last start): `systemctl --user restart <unit>` only (no pip)."
        ),
    )
    @click.option(
        "--no-log",
        "no_log",
        is_flag=True,
        default=False,
        help="Write output to the terminal instead of the job's runtime log "
        "file. For interactive testing — cron/systemd always want the default.",
    )
    def cron_exec(name: str, apply: bool, no_log: bool) -> None:
        from ....jobs import jobs_of_kind

        # Verify the named job is in the federation. Both cron-kind (crontab)
        # and timer-kind (systemd) scitex-dev jobs route their body through
        # THIS verb so the log sink (mkdir + rotate + fd-level redirect) lives
        # in one place; a timer's `ExecStart=scitex-dev ecosystem cron exec
        # <name>` resolves cleanly, unlike the old inline shell string that a
        # systemd exec (no shell) mangled.
        all_jobs = jobs_of_kind("cron") + jobs_of_kind("timer")
        names = {j.name for j in all_jobs}
        if name not in names:
            known = ", ".join(sorted(names)) or "(none)"
            raise click.ClickException(
                f"unknown federated cron/timer job: {name!r}. Discovered: {known}"
            )

        if no_log:
            _dispatch_federated_job(name, apply=apply, all_jobs=all_jobs)
            return

        # The verb OWNS logging: mkdir + rotate + fd-level (os.dup2) redirect
        # of stdout+stderr into $HOME/.scitex/<pkg>/runtime/logs/<slug>.log,
        # so child processes (ssh/rsync/sac/git the bodies spawn) are captured
        # too — that is what operators grep. FAIL LOUD: a LogSinkError means
        # the job does NOT run unlogged.
        from ...._ecosystem_jobs._provider import log_path_for
        from ....jobs._logsink import LogSinkError, redirect_to_log

        log = log_path_for(name)
        try:
            with redirect_to_log(log):
                _dispatch_federated_job(name, apply=apply, all_jobs=all_jobs)
        except LogSinkError as exc:
            raise click.ClickException(str(exc)) from exc


def _dispatch_federated_job(name: str, *, apply: bool, all_jobs) -> None:
    """Run federated job ``name``'s body. Raises on failure.

    Split out of the Click callback so the log-sink wrapper stays a single
    ``with`` block around ONE call (mirrors ``_cli.cron.run._run_body``).
    """
    if name == "deploy-freshness":
        from ...._ecosystem_jobs import _deploy_freshness

        result = _deploy_freshness.run_once(apply=apply)
        if result.error is not None:
            raise click.ClickException(result.error)
        return

    # Pure shell-body job (host script / console-script pipeline). The body
    # carries NO mkdir / redirect / rotation — the caller's log sink supplies
    # all three; the child inherits fds 1/2, already redirected at fd level.
    from ...._ecosystem_jobs._provider import JOB_SHELL_BODIES

    if name in JOB_SHELL_BODIES:
        import subprocess

        completed = subprocess.run(
            JOB_SHELL_BODIES[name], shell=True, check=False
        )
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        return

    # Defensive — a JobSpec is discovered but no dispatch branch exists. That
    # is expected for the OTHER leaves' cron jobs: their crontab line invokes
    # the leaf's OWN CLI directly (never `ecosystem cron exec`), so we only
    # reach here if someone runs `ecosystem cron exec <leaf-job>` by hand.
    # Shell out to the JobSpec.command rather than crash.
    import shlex
    import subprocess

    spec = next(j for j in all_jobs if j.name == name)
    cmd_str = spec.command.split(";")[-1].strip()
    for redir in (" >> ", " > ", " 2>>", " 2>"):
        idx = cmd_str.find(redir)
        if idx > 0:
            cmd_str = cmd_str[:idx].strip()
    argv = shlex.split(cmd_str)
    if not argv:
        raise click.ClickException(
            f"cron job {name!r}: empty command after wrapper strip"
        )
    r = subprocess.run(argv, check=False)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _source_of(name: str) -> str:
    """Best-effort source label: package prefix before the first dot."""
    if "." in name:
        return name.split(".", 1)[0]
    return "scitex-dev"


# EOF
