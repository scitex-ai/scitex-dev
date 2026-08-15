#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/ecosystem/_cmds/_host_config.py
"""ecosystem ``host-config`` -- the declared host state, checked and applied.

Each scitex leaf declares the HOST-level files it needs via a
``scitex_dev.host_config`` entry-point provider (see
``scitex_dev.host_config``); this command aggregates them and is the ONLY
sanctioned way to change them. Operator ruling 2026-08-12: privileged
host changes typed ad hoc into a shell leave no record of what was
configured or why, so the declaration -- not the shell session -- is the
source of truth.

Three verbs, deliberately asymmetric in privilege:

* ``list``  -- what the ecosystem declares. Never touches the host.
* ``check`` -- compare declaration against this host. UNPRIVILEGED (the
  managed files are world-readable), which is what lets the periodic
  job run as a normal user and still report honestly. Exit 1 on drift.
* ``apply`` -- converge. Needs root. Creates what is ABSENT; refuses to
  silently overwrite what has DRIFTED (``--force`` does that, after
  backing the current file up).
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def _select(provider):
    """Discover + optionally filter to one declaring package."""
    from ....host_config import discover_host_config

    specs = discover_host_config()
    if provider:
        specs = [s for s in specs if s.provider == provider]
    return specs


def _render_records(records) -> int:
    """Print one line per spec; return the count of items needing attention."""
    from rich.console import Console

    console = Console()
    if not records:
        console.print("[yellow]No host config declared by any provider.[/yellow]")
        return 0

    colors = {
        "unchanged": "green",
        "skipped": "dim",
        "created": "cyan",
        "repaired": "cyan",
        "reloaded": "cyan",
        "drift": "red",
        "reload-failed": "red",
        "blocked": "yellow",
    }
    pending = 0
    for rec in records:
        action = rec["action"]
        color = colors.get(action, "yellow")
        if action in ("drift", "reload-failed", "blocked") or action.startswith(
            "would-"
        ):
            pending += 1
        console.print(
            f"[{color}]{action:<14}[/{color}] "
            f"[bold]{rec['name']}[/bold]  {rec['detail']}"
        )
    return pending


def register(ecosystem):
    @ecosystem.group(
        "host-config",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="The ecosystem's declared HOST configuration: list, check, apply.",
            description=(
                "Walks every `scitex_dev.host_config` provider. A "
                "declaration is a file someone can read and diff; the "
                "applier is idempotent and reports what it changed; "
                "drift is reported, never silently corrected. `check` "
                "is unprivileged and is what the periodic job runs; "
                "`apply` needs root and is a deliberate act.",
            ),
            examples=(
                Example("{prog} ecosystem host-config", "What is declared."),
                Example("{prog} ecosystem host-config check", "Compare vs this host."),
                Example(
                    "sudo {prog} ecosystem host-config apply --yes",
                    "Converge (root).",
                ),
            ),
        ),
    )
    @click.pass_context
    def host_config(ctx):
        if ctx.invoked_subcommand is None:
            _list_impl(None, False)

    @host_config.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print every declared host-config spec (no host access).",
            examples=(
                Example("{prog} ecosystem host-config list", "Human table."),
                Example("{prog} ecosystem host-config list --json", "Structured."),
            ),
        ),
    )
    @click.option("--provider", default=None, help="Filter to one declaring package.")
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def host_config_list(provider, as_json):
        return _list_impl(provider, as_json)

    @host_config.command(
        "check",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Compare the declaration against this host. Unprivileged. Exit 1 on drift.",
            description=(
                "The observe-only pass the periodic job runs. Reports "
                "ok / absent / drift per spec and appends the result to "
                "~/.scitex/dev/runtime/logs/host-config.log -- including "
                "when nothing changed, so a converged host is "
                "distinguishable from a job that never ran.",
            ),
            examples=(
                Example("{prog} ecosystem host-config check", "Report."),
                Example("{prog} ecosystem host-config check --json", "For a job."),
            ),
        ),
    )
    @click.option("--provider", default=None, help="Filter to one declaring package.")
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    @click.option(
        "--no-log",
        is_flag=True,
        help="Skip the audit-log append (for ad-hoc inspection).",
    )
    @click.option(
        "--verify",
        is_flag=True,
        help="Also run each spec's verify_command and report what the host "
        "SAYS. These are observations, NOT compliance verdicts: a config "
        "can be correct while the running system legitimately differs "
        "(a requested DHCP address that was not granted). They never "
        "change a verdict.",
    )
    @click.pass_context
    def host_config_check(ctx, provider, as_json, no_log, verify):
        import json as _json

        from ....host_config._apply import apply_specs, observe_specs, write_audit

        specs = _select(provider)
        records = apply_specs(specs, dry_run=True, run_apply_commands=False)
        observations = observe_specs(specs) if verify else []
        if not no_log:
            write_audit(records + observations, mode="check")

        if as_json:
            click.echo(
                _json.dumps(
                    {"verdicts": records, "observations": observations}
                    if verify
                    else records,
                    indent=2,
                )
            )
        else:
            pending = _render_records(records)
            for obs in observations:
                # Printed under its own heading so an observation can
                # never be skimmed as a verdict.
                click.echo(f"observed       {obs['name']}  {obs['detail']}")
                for line in (obs["output"] or "(no output)").splitlines():
                    click.echo(f"                 {line}")
            if not records:
                ctx.exit(0)
            if pending:
                click.echo(
                    f"{pending} spec(s) not in the declared state. "
                    f"`sudo scitex-dev ecosystem host-config apply --yes` "
                    f"creates what is missing; drift needs --force (which "
                    f"backs the current file up first)."
                )
            else:
                click.echo(f"All {len(records)} spec(s) match the declaration.")
        ctx.exit(1 if any(r["action"] != "unchanged" and r["action"] != "skipped" for r in records) else 0)

    @host_config.command(
        "apply",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Converge this host to the declaration (needs root).",
            description=(
                "Mutating verb: previews unless --yes is given. Writes "
                "what is ABSENT. A file that has DRIFTED is reported and "
                "left alone -- --force overwrites it, after copying the "
                "current file to <path>.scitex-bak.<UTC timestamp>. A "
                "spec's apply_command (e.g. a daemon restart) runs only "
                "on a pass that actually changed something.",
            ),
            examples=(
                Example("{prog} ecosystem host-config apply", "Preview."),
                Example(
                    "{prog} ecosystem host-config apply --yes --dry-run",
                    "Rehearse: --dry-run overrides --yes and writes nothing.",
                ),
                Example("sudo {prog} ecosystem host-config apply --yes", "Execute."),
                Example(
                    "sudo {prog} ecosystem host-config apply --yes --force",
                    "Also repair drift (backs up first).",
                ),
            ),
        ),
    )
    @click.option("--provider", default=None, help="Filter to one declaring package.")
    @click.option(
        "--force",
        is_flag=True,
        help="Also overwrite DRIFTED files (backs the current file up first).",
    )
    @click.option("--yes", "-y", "yes", is_flag=True, help="Actually write (root).")
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Force a preview even with --yes. This verb already previews by "
            "default, so the flag exists to make that intent EXPLICIT and "
            "un-overridable in a script, where --yes may arrive from a "
            "variable that is empty by accident rather than by decision."
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    @click.pass_context
    def host_config_apply(ctx, provider, force, yes, dry_run, as_json):
        import json as _json
        import os

        from ....host_config._apply import apply_specs, needs_root, write_audit

        specs = _select(provider)
        # Default is already preview; --dry-run additionally OVERRIDES --yes.
        # The two conflicting resolves to the non-writing side on purpose: a
        # caller who said both asked for a rehearsal and a commit in the same
        # breath, and only one of those is safe to guess at.
        dry_run = dry_run or not yes

        if not dry_run and hasattr(os, "geteuid") and os.geteuid() != 0:
            preview = apply_specs(
                specs, dry_run=True, force=force, run_apply_commands=False
            )
            if needs_root(preview, specs):
                click.echo(
                    "ERROR: apply --yes must write under /etc and needs root. "
                    "Re-run as `sudo scitex-dev ecosystem host-config apply "
                    "--yes`. (`check` is the unprivileged verb and is what "
                    "the periodic job runs.)",
                    err=True,
                )
                ctx.exit(1)

        records = apply_specs(specs, dry_run=dry_run, force=force)
        # A PREVIEW MUST NOT DIE ON ITS OWN TELEMETRY. `write_audit` appends
        # to ~/.scitex/dev/runtime/logs/host-config.log, and on 2026-08-15 a
        # CI runner whose log directory was not writable turned that into a
        # PermissionError that aborted the command BEFORE it printed
        # anything — so `--dry-run` produced an empty stdout and a traceback
        # instead of the preview the user asked for. The record is secondary;
        # the preview is the result.
        #
        # The split is by RISK, not by convenience. A dry run changed nothing,
        # so an unrecorded dry run costs a log line: warn loudly and carry on.
        # A REAL apply changed the host, and an unrecorded change is exactly
        # the "converged or never ran?" ambiguity this log exists to prevent —
        # so that one is still allowed to fail loudly.
        try:
            write_audit(records, mode="apply-dry-run" if dry_run else "apply")
        except OSError as exc:
            if not dry_run:
                raise
            click.echo(
                f"WARN: the host changed nothing (preview) but the audit log "
                f"could not be written: {exc}. The preview below is complete "
                f"and unaffected; fix the log path before running --yes, "
                f"because a REAL apply that cannot be recorded is refused.",
                err=True,
            )

        if as_json:
            click.echo(_json.dumps(records, indent=2))
            ctx.exit(0)

        _render_records(records)
        if dry_run:
            click.echo("(preview -- pass --yes to execute; needs root)")
        ctx.exit(0)

    def _list_impl(provider, as_json):
        import json as _json

        specs = _select(provider)
        if as_json:
            click.echo(
                _json.dumps(
                    [
                        {
                            "name": s.name,
                            "path": s.path,
                            "purpose": s.purpose,
                            "provider": s.provider,
                            "hosts": list(s.hosts),
                            "mode": s.mode,
                            "apply_command": s.apply_command,
                            "verify_command": s.verify_command,
                            "requires_root": s.requires_root,
                        }
                        for s in specs
                    ],
                    indent=2,
                )
            )
            return 0

        from rich.console import Console
        from rich.table import Table

        console = Console()
        if not specs:
            console.print("[yellow]No host config declared by any provider.[/yellow]")
            return 0
        table = Table(show_header=True, header_style="bold")
        table.add_column("name")
        table.add_column("path")
        table.add_column("provider")
        table.add_column("hosts")
        table.add_column("purpose")
        for spec in specs:
            table.add_row(
                spec.name,
                spec.path,
                spec.provider,
                ", ".join(spec.hosts) if spec.hosts else "(all)",
                spec.purpose,
            )
        console.print(table)
        console.print(
            f"[bold]{len(specs)}[/bold] host-config spec(s) across "
            f"{len({s.provider for s in specs})} provider(s)."
        )
        return 0

# EOF
