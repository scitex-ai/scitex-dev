#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev host`` — CLI surface for the SciTeX host registry.

Thin wrapper: all resolution logic lives in ``scitex_dev.hosts`` (mirrors
the ``registry-normalize`` / ``trace-env-vars`` CLI/engine split — see
those modules' docstrings). Other **packages** should prefer the Python
API (``scitex_dev.hosts.resolve`` / ``list_hosts``) over shelling out to
this CLI; the ``resolve --field`` leaf exists for callers that can't
import Python (e.g. a bash provisioning script):

    SPARTAN_ROOT=$(scitex-dev host resolve spartan --field scitex_root)
"""

from __future__ import annotations

import json

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup

_FIELD_CHOICES = ("name", "kind", "ssh_alias", "scitex_root")

_HOSTS_FILE_HELP = (
    "Override the hosts.yaml path (default: $SCITEX_DEV_HOSTS_YAML or "
    "~/.scitex/dev/hosts.yaml)."
)


def register_host_commands(main: click.Group) -> click.Group:
    """Attach the ``host`` noun group to the top-level click group."""

    @main.group(
        "host",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="SciTeX host registry — where is host X, and what's its ~/.scitex root?",
            description=(
                "The shared port other scitex-* packages (sac, "
                "scitex-hub, scitex-storage, ...) resolve host paths "
                "through instead of inventing their own host config or "
                "hardcoding a host-specific path. Backed by "
                "~/.scitex/dev/hosts.yaml, seeded with the operator's "
                "known hosts on first use. Python API: "
                "scitex_dev.hosts.resolve / list_hosts.",
            ),
            examples=(
                Example("{prog} host list", "Table of every registered host."),
                Example("{prog} host show spartan", "Full record for one host."),
                Example(
                    "{prog} host resolve spartan --field scitex_root",
                    "Just the scitex_root field, for shell scripting.",
                ),
            ),
        ),
    )
    @click.pass_context
    def host(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _register_list(host)
    _register_show(host)
    _register_resolve(host)
    return host


def _fail(exc) -> None:
    click.echo(str(exc), err=True)
    raise SystemExit(exc.error_code.exit_code)


def _register_list(host: click.Group) -> None:
    @host.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List every registered host.",
            examples=(
                Example("{prog} host list", "Table of name/kind/ssh_alias/scitex_root."),
                Example("{prog} host list --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--hosts-file",
        "hosts_file",
        type=click.Path(dir_okay=False),
        default=None,
        help=_HOSTS_FILE_HELP,
    )
    def _list(as_json: bool, hosts_file: str | None) -> None:
        from ..hosts import list_hosts

        records = list_hosts(hosts_path=hosts_file)
        if as_json:
            click.echo(
                json.dumps({"hosts": [r.to_dict() for r in records]}, indent=2)
            )
            return
        if not records:
            click.echo("(no hosts registered)")
            return
        click.echo(f"{'NAME':20s} {'KIND':12s} {'SSH_ALIAS':12s} SCITEX_ROOT")
        for r in records:
            click.echo(
                f"{r.name:20s} {r.kind:12s} {(r.ssh_alias or '-'):12s} {r.scitex_root}"
            )


def _register_show(host: click.Group) -> None:
    @host.command(
        "show",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show the full record for one host.",
            examples=(
                Example("{prog} host show spartan", "Human-readable record."),
                Example("{prog} host show spartan --json", "Structured JSON output."),
            ),
        ),
    )
    @click.argument("name")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--hosts-file",
        "hosts_file",
        type=click.Path(dir_okay=False),
        default=None,
        help=_HOSTS_FILE_HELP,
    )
    def _show(name: str, as_json: bool, hosts_file: str | None) -> None:
        from .._core.errors import ScitexError
        from ..hosts import is_local, resolve

        try:
            record = resolve(name, hosts_path=hosts_file)
        except ScitexError as exc:
            _fail(exc)
            return

        if as_json:
            click.echo(json.dumps(record.to_dict(), indent=2))
            return
        click.echo(f"name:        {record.name}")
        click.echo(f"kind:        {record.kind}")
        # NOT "(local — no SSH hop)". That printed a topology claim derived
        # from an ABSENT value, and it was false for `ywata-note-win` on
        # every machine except the laptop the registry was authored on.
        # An empty field means the alias was not recorded; locality is a
        # separate question, answered below by comparing against this host.
        click.echo(f"ssh_alias:   {record.ssh_alias or '(no alias recorded)'}")
        click.echo(f"local:       {'yes' if is_local(record) else 'no'}")
        click.echo(f"scitex_root: {record.scitex_root}")


def _register_resolve(host: click.Group) -> None:
    @host.command(
        "resolve",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print one field of a host record (for shell scripting).",
            description=(
                "Exits non-zero with an actionable message on stderr if "
                "the host isn't found — never a silent empty string.",
            ),
            examples=(
                Example(
                    "SPARTAN_ROOT=$({prog} host resolve spartan --field scitex_root)",
                    "Capture the field into a shell variable.",
                ),
                Example(
                    "{prog} host resolve spartan --field ssh_alias",
                    "Print the SSH alias.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option(
        "--field",
        "field",
        type=click.Choice(_FIELD_CHOICES),
        required=True,
        help="Which field to print.",
    )
    @click.option(
        "--hosts-file",
        "hosts_file",
        type=click.Path(dir_okay=False),
        default=None,
        help=_HOSTS_FILE_HELP,
    )
    def _resolve(name: str, field: str, hosts_file: str | None) -> None:
        from .._core.errors import ScitexError
        from ..hosts import resolve

        try:
            record = resolve(name, hosts_path=hosts_file)
        except ScitexError as exc:
            _fail(exc)
            return

        value = getattr(record, field)
        click.echo(value if value is not None else "")


# EOF
