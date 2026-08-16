#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `validate-versions` (+ deprecated `check-versions`/`packages` aliases), `fix-mismatches`."""

import json

import click

from ...._ecosystem.click_compat import deprecated_alias
from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "validate-versions",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Audit ecosystem package versions across hosts (3 modes + gate).",
            examples=(
                Example("{prog} ecosystem validate-versions", "Observe (report only)."),
                Example("{prog} ecosystem validate-versions --dry-run", "Preview the sync."),
                Example("{prog} ecosystem validate-versions --apply", "Execute the sync."),
                Example(
                    "{prog} ecosystem validate-versions --gate scitex-todo==0.7.51 --require-full-coverage",
                    "Release-gate mode.",
                ),
            ),
        ),
    )
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Host name(s). Default: all enabled hosts.",
    )
    @click.option(
        "--package",
        "-p",
        "packages",
        multiple=True,
        help="Package name(s). Default: all.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Mode 2: print commands that would run on out-of-sync hosts.",
    )
    @click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        help="Mode 3: actually execute the sync. Mutually exclusive with --dry-run.",
    )
    @click.option(
        "--unsafe",
        is_flag=True,
        help="Skip ahead-check; allow clobbering remote unpushed commits.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--gate",
        "gate_spec",
        default=None,
        metavar="PACKAGE==VERSION",
        help=(
            "Release-gate mode (mutually exclusive with --dry-run/--apply): "
            "report whether PACKAGE is installed at >= VERSION on every "
            "in-scope fleet host. Pair with --require-full-coverage to "
            "hard-fail CI / a pre-tag hook when coverage isn't 100%. See "
            "scitex_dev._ecosystem._release_gate for the protocol-milestone "
            "convention this backs."
        ),
    )
    @click.option(
        "--require-full-coverage",
        "require_full_coverage",
        is_flag=True,
        help="With --gate: exit non-zero unless every in-scope host meets VERSION.",
    )
    @click.pass_context
    def ecosystem_validate_versions(
        ctx,
        hosts,
        packages,
        dry_run,
        do_apply,
        unsafe,
        as_json,
        gate_spec,
        require_full_coverage,
    ):
        if gate_spec is not None:
            if dry_run or do_apply:
                click.echo(
                    "error: --gate is mutually exclusive with --dry-run/--apply",
                    err=True,
                )
                ctx.exit(2)
            pkg_name, sep, min_version = gate_spec.partition("==")
            pkg_name = pkg_name.strip()
            min_version = min_version.strip()
            if not sep or not pkg_name or not min_version:
                click.echo("error: --gate expects PACKAGE==VERSION", err=True)
                ctx.exit(2)

            from ...._ecosystem._release_gate import check_release_gate

            host_list = list(hosts) if hosts else None
            if host_list == ["all"]:
                host_list = None

            result = check_release_gate(pkg_name, min_version, hosts=host_list)

            if as_json:
                click.echo(json.dumps(result, indent=2, default=str))
            else:
                summ = result["summary"]
                click.echo(f"gate: {pkg_name} >= {min_version}")
                for row in result["rows"]:
                    mark = "OK  " if row["meets"] else "FAIL"
                    click.echo(f"  [{mark}] {row['host']}: installed={row['installed']}")
                click.echo(
                    f"{summ['covered']}/{summ['total_hosts']} hosts covered "
                    f"({summ['coverage_pct']:.0f}%)"
                )
                if summ["not_covered"]:
                    click.echo("not covered: " + ", ".join(summ["not_covered"]))
                if summ["total_hosts"] == 0:
                    click.echo(
                        "warning: no in-scope hosts for "
                        f"{pkg_name!r} — is it in any host's synced-package "
                        "set (host.packages / host.exclude in "
                        "~/.scitex/dev/config.yaml)?",
                        err=True,
                    )

            if require_full_coverage:
                ctx.exit(0 if result["passed"] else 1)
            ctx.exit(0)

        if dry_run and do_apply:
            click.echo("error: --dry-run and --apply are mutually exclusive", err=True)
            ctx.exit(2)

        from ...._ecosystem._packages import packages_audit

        host_list = list(hosts) if hosts else None
        pkg_list = list(packages) if packages else None
        if host_list == ["all"]:
            host_list = None

        if do_apply:
            mode = "apply"
        elif dry_run:
            mode = "dry-run"
        else:
            mode = "observe"

        # CAN WE BELIEVE THE VERSION STRINGS AT ALL? Runs BEFORE the comparison,
        # because a comparison against a fossilised `.dist-info` is not a weak
        # signal but a WRONG one, in either direction: it cries "stale" at a
        # current install and blesses a stale one.
        #
        # `_untrustworthy_installs` has answered this question correctly since
        # 2026-07-12 and THIS COMMAND HAS NEVER CALLED IT — a check with no
        # consumer, which is the defect the module was written to prevent,
        # occurring one layer above it. Widening its scope (#653, 3 -> 70
        # packages) moved nothing for anyone running `validate-versions`
        # precisely because of this missing call.
        from ...._ecosystem._drift_report import (
            check_untrustworthy_installs,
            render_untrustworthy_install_banner,
        )

        untrustworthy = check_untrustworthy_installs()

        result = packages_audit(
            mode=mode, hosts=host_list, packages=pkg_list, unsafe=unsafe
        )

        if as_json:
            # Drop the rendered table from JSON; "state" is the structured form.
            payload = {k: v for k, v in result.items() if k != "table"}
            # Machine consumers get the SAME prior question the humans get.
            # Emitting it only on the human path would leave every scripted
            # reader comparing versions it has no reason to trust, with
            # nothing in the payload saying so.
            payload["untrustworthy_installs"] = [w.to_dict() for w in untrustworthy]
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            # BEFORE the table, not after. A reader who has already read a
            # version matrix has formed conclusions; the caveat has to arrive
            # first to prevent them, not afterwards to retract them.
            banner = render_untrustworthy_install_banner(untrustworthy)
            if banner:
                click.echo(banner)
                click.echo()
            if mode == "observe":
                click.echo(result["table"])
                summ = result["summary"]
                click.echo()
                if summ["total"] == 0:
                    # NEVER print a bare `0/0 cells up-to-date`. It sits
                    # under a table whose localhost column may carry dozens
                    # of drift markers, and it reads as "nothing drifted"
                    # when it means "nothing was compared". Same number,
                    # opposite conclusion — the exit code below already
                    # knows the difference (it requires total > 0), so this
                    # only makes the printed line agree with it.
                    click.echo(
                        f"NO CELLS COMPARED — {summ['hosts_in_scope']} remote "
                        f"host(s) in scope, so this run says NOTHING about "
                        f"drift. The `localhost` column above is reference "
                        f"only and is not counted. Name reachable hosts with "
                        f"--host, or run from a machine that can reach the "
                        f"fleet."
                    )
                else:
                    click.echo(
                        f"{summ['matching']}/{summ['total']} cells up-to-date "
                        f"across {summ['hosts_in_scope']} host(s)"
                    )
                if summ["needing_sync"]:
                    click.echo("needing sync:")
                    for n in summ["needing_sync"]:
                        click.echo(f"  - {n['host']}: {n['pkg']}")
            elif mode == "dry-run":
                cmds = result["commands"]
                if not cmds:
                    click.echo("# everything in sync — no commands to preview")
                for host, pkgs_ in cmds.items():
                    for pkg, lines in pkgs_.items():
                        click.echo(f"# {host} :: {pkg}")
                        for line in lines:
                            click.echo(f"  {line}")
            else:  # apply
                click.echo(json.dumps(result, indent=2, default=str))

        # Exit code: observe returns 1 if anything mismatches (or unknown).
        if mode == "observe":
            summ = result["summary"]
            ctx.exit(
                0 if summ["matching"] == summ["total"] and summ["total"] > 0 else 1
            )
        ctx.exit(0)

    # Deprecated alias for the original §1 noun-verb fix (packages →
    # check-versions). check-versions was itself later renamed to
    # validate-versions (§1f: `check` is a non-canonical synonym for the
    # ecosystem-wide `validate` verb) — point straight at the current
    # command rather than hopping through the check-versions alias.
    # Removed in 0.11.0.
    @ecosystem.command(
        "packages",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _ecosystem_packages_deprecated(ctx):
        """(deprecated) Use `ecosystem validate-versions`. Removed in 0.11.0."""
        click.echo(
            "warning: `ecosystem packages` was renamed to "
            "`ecosystem validate-versions`.",
            err=True,
        )
        target = ecosystem.get_command(ctx, "validate-versions")
        if target is None:
            ctx.exit(2)
        ctx.invoke(target, *ctx.args)

    # `check-versions` → `validate-versions` rename (§1f: `check` is a
    # non-canonical synonym for the ecosystem-wide `validate` verb).
    # Internal cross-host RPC calls (ecosystem check-sync's remote-check
    # forwarding, any fleet cron job invoking this by name) keep using
    # the OLD name deliberately during the rolling-upgrade window; the
    # warn-phase alias is what makes that safe regardless of which side
    # of the upgrade a given host is on.
    deprecated_alias(
        ecosystem,
        "check-versions",
        target="validate-versions",
        remove_in="0.32",
        phase="warn",
    )

    @ecosystem.command("fix-mismatches", hidden=True)
    @click.option(
        "--confirm", is_flag=True, help="Apply fixes (default: preview only)."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def ecosystem_fix_mismatches(ctx, confirm, as_json):
        """(deprecated) Renamed to `packages`. Forwards to `packages [--apply]`."""
        click.echo(
            "warning: `ecosystem fix-mismatches` is deprecated; "
            "use `ecosystem packages` (or `packages --apply` to execute).",
            err=True,
        )
        from .... import fix_mismatches
        from ..._utils import wrap_as_cli

        wrap_as_cli(fix_mismatches, as_json=as_json, confirm=confirm)
