#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `branch-hygiene` — the daily two-dimensional branch sweep.

Click only. Every decision lives in :mod:`scitex_dev.branch_hygiene`, so
this verb, the ``scitex-dev-branch-hygiene`` periodic job and any future
caller share ONE predicate rather than three drifting copies.

DRY RUN IS THE DEFAULT. ``--execute`` opts in, and says so in the
summary line, because the number this verb prints on a real fleet is in
the hundreds and "would delete 251" must never be mistaken for
"deleted 251" — nor the reverse.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand

_MARK = {True: "x", False: "-"}


def _render(outcome, skips) -> None:
    verb = "DELETED" if outcome.executed else "would delete"
    for result in outcome.results:
        head = f"{result.package or result.repo}"
        if result.error:
            click.echo(f"  ! {head}: {result.error}")
            continue
        click.echo(f"  {head}  checkout={result.checkout.action}")
        for verdict in result.local + result.remote:
            note = f" [{verdict.worktree_action}]" if verdict.worktree_action else ""
            err = f" ERROR: {verdict.error}" if verdict.error else ""
            click.echo(
                f"    {_MARK[verdict.drop]} {verdict.name}: {verdict.reason}{note}{err}"
            )
        for record in result.discarded:
            click.echo(f"    ! discarded uncommitted work in {record.path}:")
            for entry in record.entries:
                click.echo(f"        {entry}")
        if result.backup_restore:
            click.echo(f"    restore: {result.backup_restore}")
    for host, why in skips:
        click.echo(f"  ~ {host}: {why}")
    click.echo(f"{verb}: {outcome.summary_line()}")


def register(ecosystem):
    @ecosystem.command(
        "branch-hygiene",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Daily branch sweep across every package and host (dry-run default).",
            description=(
                "Three legs. CHECKOUTS: put every registered checkout back "
                "on develop, refusing a dirty tree — reported and skipped, "
                "never stashed, never forced. LOCAL BRANCHES: delete "
                "anything that is not main / master / develop / "
                "cla-signatures by EXACT name, is not an open PR's head, "
                "and either merged into develop or went untouched for "
                "--max-age-hours. A worktree holding a finished branch is "
                "removed with it: cleanly when the tree is clean, with "
                "--force ONLY when it carries uncommitted work whose FILES "
                "have also gone untouched past the window, and every such "
                "discard is printed. REMOTE BRANCHES: the same rule, run "
                "ONCE for the fleet — remote refs are shared, so a per-host "
                "pass is N times the API calls for one effect. Anything "
                "that could not be measured is KEPT and says which signal "
                "was missing. A verified git bundle of every doomed local "
                "branch is written before the first deletion and the "
                "restore command is printed; if the bundle cannot be "
                "verified, nothing is deleted."
            ),
            examples=(
                Example(
                    "{prog} ecosystem branch-hygiene",
                    "Dry run on this host: the full plan, deleting nothing.",
                ),
                Example(
                    "{prog} ecosystem branch-hygiene --package scitex-dev",
                    "Rehearse one package before trusting the fleet pass.",
                ),
                Example(
                    "{prog} ecosystem branch-hygiene --execute",
                    "Run it for real on this host, local refs only.",
                ),
                Example(
                    "{prog} ecosystem branch-hygiene --remote --execute",
                    "Add the fleet-wide remote leg. Run this on ONE host.",
                ),
                Example(
                    "{prog} ecosystem branch-hygiene --all-hosts --execute",
                    "Fan out over ssh; the remote leg still runs only here.",
                ),
            ),
        ),
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Limit to specific ecosystem packages (repeat the flag).",
    )
    @click.option(
        "--execute",
        "execute",
        is_flag=True,
        help="Actually delete. Without it this verb only prints the plan.",
    )
    @click.option(
        "--local/--no-local",
        "do_local",
        default=True,
        help="Sweep this host's checkouts. --no-local leaves only the remote leg.",
    )
    @click.option(
        "--remote/--no-remote",
        "do_remote",
        default=False,
        help="Also sweep origin's branches. Run on ONE host, never per-host.",
    )
    @click.option(
        "--all-hosts",
        "all_hosts",
        is_flag=True,
        help="Also run the LOCAL leg on every registered host over ssh.",
    )
    @click.option(
        "--max-age-hours",
        "max_age_hours",
        type=float,
        default=None,
        help="Staleness window in hours (default 24).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def ecosystem_branch_hygiene(
        package, execute, do_local, do_remote, all_hosts, max_age_hours, as_json
    ):
        import json as _json
        import sys as _sys

        from ....branch_hygiene import (
            DEFAULT_MAX_AGE_HOURS,
            SweepOutcome,
            exit_code_for,
            fan_out,
            sweep_local_host,
        )

        window = DEFAULT_MAX_AGE_HOURS if max_age_hours is None else max_age_hours
        names = list(package) or None
        outcome = sweep_local_host(
            execute=execute,
            do_local=do_local,
            do_remote=do_remote,
            packages=names,
            max_age_hours=window,
        )
        skips: list[tuple[str, str]] = []
        if all_hosts:
            rows, skips = fan_out(
                execute=execute, packages=names, max_age_hours=window
            )
            outcome = SweepOutcome(
                results=outcome.results + tuple(rows),
                executed=outcome.executed,
                remote_pass=outcome.remote_pass,
                host=outcome.host,
            )

        if as_json:
            payload = outcome.to_dict()
            payload["skipped_hosts"] = [
                {"host": host, "reason": why} for host, why in skips
            ]
            click.echo(_json.dumps(payload, indent=2, default=str))
            _sys.exit(exit_code_for(outcome))

        _render(outcome, skips)
        _sys.exit(exit_code_for(outcome))


# EOF
