#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev host generate-ssh-config | validate-matrix | validate-ssh-config
| corroborate``.

Thin wrapper, same split as ``_hosts.py``: every decision lives in
``scitex_dev.hosts``; this file only renders and picks an exit code.

VERB NAMING. ``validate-*`` rather than the ``check-*`` these commands were
first drafted as: doctrine ``06_noun-verb-catalog`` allows exactly ONE
checking verb ecosystem-wide, and the CLI audit flags `check`/`verify` as
synonyms of it. The audit dict exists for shipped public names that cannot
be moved (`registry-normalize`); a command being added in this same PR is not
one of those, so it conforms instead of being exempted. ``generate-`` /
``validate-ssh-config`` also lands as a matched pair over one object, which
is the shape the doctrine is asking for.

EXIT CODES ARE PART OF THE ANSWER
----------------------------------
Each check verb exits ``0`` only on a ``pass``. ``incomplete`` — a sweep that
mostly did not run, an alias ``ssh -G`` would not answer about, a
corroboration with a signal missing — exits NON-ZERO, deliberately. A cron
entry or a CI step reads the exit code and nothing else, and a check that
could not run must not hand it the same ``0`` a healthy fleet does.
"""

from __future__ import annotations

import json

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand

_HOSTS_FILE_HELP = (
    "Override the hosts.yaml path (default: $SCITEX_DEV_HOSTS_YAML or "
    "~/.scitex/dev/hosts.yaml)."
)

#: `incomplete` is not `pass`. See the module docstring.
_VERDICT_EXIT = {"pass": 0, "incomplete": 1, "fail": 2}


def _hosts_option(fn):
    return click.option(
        "--hosts-file",
        "hosts_file",
        type=click.Path(dir_okay=False),
        default=None,
        help=_HOSTS_FILE_HELP,
    )(fn)


def register_connectivity_commands(host: click.Group) -> None:
    """Attach the connectivity verbs to the existing ``host`` group."""
    _register_ssh_config(host)
    _register_check_matrix(host)
    _register_check_config(host)
    _register_corroborate(host)


def _register_ssh_config(host: click.Group) -> None:
    @host.command(
        "generate-ssh-config",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Generate ssh stanzas (<name> LAN, <name>-net off-LAN).",
            description=(
                "Prints to stdout by default — nothing is written without "
                "--write, and --write itself only reports the plan until you "
                "add --yes. Applied, it replaces only the marked managed "
                "block; every line outside it is preserved. A host is NEVER "
                "dropped for being unreachable; its last_seen ages instead.",
            ),
            examples=(
                Example("{prog} host generate-ssh-config", "Preview the managed block."),
                Example(
                    "{prog} host generate-ssh-config --write ~/.ssh/conf.d/scitex-dev-hosts.conf",
                    "Report what would change; write nothing.",
                ),
                Example(
                    "{prog} host generate-ssh-config --write ~/.ssh/conf.d/scitex-dev-hosts.conf -y",
                    "Apply it, replacing only the managed region.",
                ),
            ),
        ),
    )
    @click.option(
        "--write",
        "write_path",
        type=click.Path(dir_okay=False),
        default=None,
        help="Write into this file's managed block instead of printing.",
    )
    @click.option(
        "--dry-run",
        "dry_run",
        is_flag=True,
        help="Report what --write WOULD change, and change nothing.",
    )
    @click.option(
        "--yes",
        "-y",
        "assume_yes",
        is_flag=True,
        help="Actually write. Without it, --write only reports the plan.",
    )
    @_hosts_option
    def _ssh_config(
        write_path: str | None,
        dry_run: bool,
        assume_yes: bool,
        hosts_file: str | None,
    ) -> None:
        from .._core.errors import ScitexError
        from ..hosts import (
            get_hosts_yaml_path,
            list_hosts,
            render_ssh_config,
            write_managed,
        )

        records = list_hosts(hosts_path=hosts_file)
        block = render_ssh_config(records, source=get_hosts_yaml_path(hosts_file))
        if write_path is None:
            click.echo(block, nl=False)
            return

        # Dry-run is the DEFAULT for --write. This command edits a file inside
        # ~/.ssh, where a surprise is expensive and not obviously reversible;
        # `-y` is the one place the operator says "yes, touch it".
        planning = dry_run or not assume_yes
        try:
            outcome = write_managed(write_path, block, dry_run=planning)
        except ScitexError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(exc.error_code.exit_code)
        if planning:
            click.echo(f"would be {outcome.state}: {outcome.path}")
            if not dry_run:
                click.echo("Nothing written. Re-run with --yes to apply.", err=True)
            return
        click.echo(f"{outcome.state}: {outcome.path}")


def _register_check_matrix(host: click.Group) -> None:
    @host.command(
        "validate-matrix",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Probe every ORDERED host pair and report the denominator.",
            description=(
                "N*(N-1) ordered pairs per transport. A->B succeeding says "
                "nothing about B->A. The summary always names how many pairs "
                "a COMPLETE sweep would be, so a mostly-skipped run cannot "
                "read as a pass — and it exits non-zero when incomplete.",
            ),
            examples=(
                Example("{prog} host validate-matrix", "Sweep lan + net."),
                Example(
                    "{prog} host validate-matrix --transport lan --json",
                    "LAN only, structured output.",
                ),
            ),
        ),
    )
    @click.option(
        "--transport",
        "transport",
        type=click.Choice(("lan", "net", "all")),
        default="all",
        help="Which transport(s) to sweep.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Structured JSON output.")
    @click.option(
        "--timeout", "timeout", type=float, default=20.0, help="Per-probe ceiling (s)."
    )
    @_hosts_option
    def _check_matrix(
        transport: str, as_json: bool, timeout: float, hosts_file: str | None
    ) -> None:
        from ..hosts import check_matrix, list_hosts

        transports = ("lan", "net") if transport == "all" else (transport,)
        result = check_matrix(
            list_hosts(hosts_path=hosts_file), transports=transports, timeout=timeout
        )
        if as_json:
            click.echo(json.dumps(result.to_dict(), indent=2))
        else:
            for probe in result.probes:
                click.echo(
                    f"{probe.status:8s} {probe.transport:4s} "
                    f"{probe.source} -> {probe.target}: {probe.detail}"
                )
            click.echo("")
            click.echo(result.summary_line())
        raise SystemExit(_VERDICT_EXIT[result.verdict])


def _register_check_config(host: click.Group) -> None:
    @host.command(
        "validate-ssh-config",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Compare the registry against what `ssh -G` actually resolves.",
            description=(
                "Two questions a config file cannot answer: does the stanza "
                "that WINS say what the registry says (an Include above the "
                "managed block silently beats it), and does the key a stanza "
                "NAMES actually exist here. The second was the real mesh "
                "failure of 2026-08-13.",
            ),
            examples=(
                Example("{prog} host validate-ssh-config", "Check THIS machine."),
                Example(
                    "{prog} host validate-ssh-config --on scitex-compute-01",
                    "Ask that host about its own config, over ssh.",
                ),
            ),
        ),
    )
    @click.option(
        "--on",
        "hop",
        default=None,
        help="Run the check ON this host (via ssh) instead of locally.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Structured JSON output.")
    @_hosts_option
    def _check_config(hop: str | None, as_json: bool, hosts_file: str | None) -> None:
        from ..hosts import check_ssh_config, list_hosts

        report = check_ssh_config(list_hosts(hosts_path=hosts_file), hop=hop)
        if as_json:
            click.echo(json.dumps(report.to_dict(), indent=2))
        else:
            for check in report.checks:
                resolved = check.effective_hostname or "(unresolved)"
                click.echo(f"{check.alias:24s} -> {resolved}")
                for finding in check.findings:
                    click.echo(f"    [{finding.severity}] {finding.code}: {finding.detail}")
            click.echo("")
            click.echo(report.summary_line())
        raise SystemExit(_VERDICT_EXIT[report.verdict])


def _register_corroborate(host: click.Group) -> None:
    @host.command(
        "corroborate",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Three independent signals must agree before an address is trusted.",
            description=(
                "MAC, ssh host-key continuity, and a live hostname readback. "
                "All three agreeing means an address rewrite is safe. Any "
                "disagreement is escalated, never resolved automatically — a "
                "machine can detect a conflict but cannot decide which source "
                "is true. Fewer than three available reports `insufficient`: "
                "no contradiction found is NOT corroboration.",
            ),
            examples=(
                Example("{prog} host corroborate scitex-nas-01", "Check the observed address."),
                Example(
                    "{prog} host corroborate scitex-compute-01 --address 192.168.11.171",
                    "Ask about the DHCP reservation instead.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option(
        "--address",
        "address",
        default=None,
        help="Address to corroborate (default: the record's observed `lan`).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Structured JSON output.")
    @_hosts_option
    def _corroborate(
        name: str, address: str | None, as_json: bool, hosts_file: str | None
    ) -> None:
        from .._core.errors import ScitexError
        from ..hosts import corroborate, resolve

        try:
            record = resolve(name, hosts_path=hosts_file)
        except ScitexError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(exc.error_code.exit_code)

        result = corroborate(record, address)
        if as_json:
            click.echo(json.dumps(result.to_dict(), indent=2))
        else:
            for signal in result.signals:
                mark = {True: "agree", False: "DISAGREE", None: "not-checked"}[
                    signal.agrees
                ]
                click.echo(f"{signal.name:22s} {mark:12s} {signal.detail}")
            for note in result.notes:
                click.echo(f"note: {note}")
            click.echo("")
            click.echo(result.summary_line())
            escalation = result.escalation()
            if escalation:
                click.echo(escalation, err=True)
        # `may_rewrite` is the only green. `insufficient` exits 1 and
        # `conflict` exits 2 — a caller that wired `&& rewrite` gets neither.
        if result.may_rewrite:
            raise SystemExit(0)
        raise SystemExit(2 if result.verdict == "conflict" else 1)


# EOF
