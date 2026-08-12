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

#: Fields `host resolve --field` can print. The connectivity ones are read
#: off `record.connectivity`; `net_alias` is a property that is None for a
#: LAN-only machine, which prints as an empty line — the honest answer, since
#: there is no off-LAN name to hand anyone.
_CONNECTIVITY_FIELDS = (
    "lan",
    "reserved",
    "mac",
    "host_key_fingerprint",
    "reported_hostname",
    "ssh_user",
    "identity_file",
    "last_seen",
)
_FIELD_CHOICES = (
    "name",
    "kind",
    "ssh_alias",
    "scitex_root",
    "net_alias",
) + _CONNECTIVITY_FIELDS

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
            summary="SciTeX host registry — where is host X, and how do I reach it?",
            description=(
                "The shared port other scitex-* packages (sac, "
                "scitex-hub, scitex-storage, ...) resolve host paths "
                "through instead of inventing their own host config or "
                "hardcoding a host-specific path. Backed by "
                "~/.scitex/dev/hosts.yaml, seeded with the operator's "
                "known hosts on first use. Python API: "
                "scitex_dev.hosts.resolve / list_hosts.\n\n"
                "Records also carry CONNECTIVITY — the observed LAN address, "
                "the DHCP reservation (a separate fact), the off-LAN `net` "
                "route, MAC, ssh host-key fingerprint and last_seen. "
                "generate-ssh-config turns that into `<name>` (LAN) and "
                "`<name>-net` (off-LAN) stanzas; validate-matrix probes the "
                "ordered pairs; validate-ssh-config asks `ssh -G` what "
                "actually wins; corroborate requires three independent "
                "signals to agree before an address may be rewritten.",
            ),
            examples=(
                Example("{prog} host list", "Table of every registered host."),
                Example("{prog} host show spartan", "Full record for one host."),
                Example(
                    "{prog} host resolve spartan --field scitex_root",
                    "Just the scitex_root field, for shell scripting.",
                ),
                Example(
                    "{prog} host generate-ssh-config --write PATH -y",
                    "Write the managed ssh-config block.",
                ),
                Example(
                    "{prog} host corroborate scitex-nas-01",
                    "Three-signal check before trusting an address.",
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

    from ._hosts_connectivity import register_connectivity_commands

    register_connectivity_commands(host)
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
        click.echo(
            f"{'NAME':20s} {'KIND':12s} {'LAN':16s} {'LAST_SEEN':12s} SCITEX_ROOT"
        )
        for r in records:
            conn = r.connectivity
            # `-` for "not recorded". An address column that is blank when
            # unknown and blank when the host is unreachable would make the
            # two indistinguishable at a glance.
            click.echo(
                f"{r.name:20s} {r.kind:12s} {(conn.lan or '-'):16s} "
                f"{(conn.last_seen or '-'):12s} {r.scitex_root}"
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
        from ..hosts import resolve

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
        click.echo(f"ssh_alias:   {record.ssh_alias or '(local — no SSH hop)'}")
        click.echo(f"scitex_root: {record.scitex_root}")
        _echo_connectivity(record)


def _echo_connectivity(record) -> None:
    """Print the connectivity block, saying explicitly when nothing is known."""
    conn = record.connectivity
    if conn.is_empty():
        click.echo("connectivity: (nothing recorded)")
        return
    click.echo(f"lan:         {conn.lan or '-'}")
    if conn.reserved:
        # Printed with its relationship to `lan` spelled out, because the two
        # differing is a REAL and current state (an unrenewed lease) that
        # reads as a typo when the values sit side by side unexplained.
        agreement = "matches lan" if conn.reserved == conn.lan else "DIFFERS from lan"
        click.echo(f"reserved:    {conn.reserved}  ({agreement})")
    for label, value in (
        ("mac", conn.mac),
        ("host_key", conn.host_key_fingerprint),
        ("hostname", conn.reported_hostname),
        ("ssh_user", conn.ssh_user),
        ("identity", conn.identity_file),
        ("last_seen", conn.last_seen),
    ):
        if value:
            click.echo(f"{label + ':':12s} {value}")
    if conn.net:
        click.echo(f"net alias:   {record.net_alias}  (transport {conn.net.transport})")
        click.echo(f"net host:    {conn.net.hostname or '-'}")


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

        source = record.connectivity if field in _CONNECTIVITY_FIELDS else record
        value = getattr(source, field)
        click.echo(value if value is not None else "")


# EOF
