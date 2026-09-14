#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `<pkg> dev access …` command group, mountable by any leaf package.

Mirrors ``scitex_dev.secret.cli``: all behaviour is in the library, and a leaf
gets the identical surface by calling the registrar on its ``dev`` group::

    from scitex_dev.access.cli import register_access_group

    register_access_group(dev, pkg="scitex-cards")

Exit codes are the decision's, never 1 or 2 (which Click already uses):
0 allowed, 10 denied / not signed in / not entitled, 11 unresolved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from ._check import check, decide_missing
from ._decision import AccessDecision
from ._errors import AccessConfigError
from ._fixture import AccessFixture
from ._kinds import KindRegistry, discover_kinds
from ._types import Principal, split_resource_ref

_EXIT_CODES = (
    (0, "allowed"),
    (10, "denied, not signed in, or not entitled"),
    (11, "unresolved: the question could not be answered"),
)


def _registry_with(fixture: Optional[AccessFixture]) -> KindRegistry:
    discovered = list(discover_kinds().values())
    fixture_kinds = list(fixture.kinds.values()) if fixture is not None else []
    return KindRegistry(discovered + fixture_kinds)


def _load_fixture(fixture_path: Optional[str]) -> Optional[AccessFixture]:
    if fixture_path is None:
        return None
    try:
        return AccessFixture.load(Path(fixture_path).expanduser())
    except AccessConfigError as error:
        raise click.ClickException(str(error)) from error


def decide_from_fixture(
    principal_text: str, action: str, resource_text: str, fixture: Optional[AccessFixture]
) -> AccessDecision:
    """The CLI's decision, reusable by an MCP tool or HTTP view over the same fixture shape."""
    principal = Principal.parse(principal_text)
    split_resource_ref(resource_text)
    kinds = _registry_with(fixture)
    resource = fixture.find(resource_text) if fixture is not None else None
    if resource is None:
        return decide_missing(principal, action, resource_text, kinds=kinds)
    return check(
        principal,
        action,
        resource,
        grants=fixture.grants,
        memberships=fixture.memberships,
        kinds=kinds,
    )


def register_access_group(parent: click.Group, *, pkg: Optional[str] = None) -> click.Group:
    """Mount ``access`` on *parent* (a package's ``dev`` group).

    ``pkg`` narrows ``access list-kinds`` to the kinds that package registers;
    ``None`` (scitex-dev's own mount) lists every registered kind.
    """

    @parent.group(
        "access",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Access decisions: who may do what to which resource.",
            description=(
                "One primitive for every app: check() decides a single request "
                "and accessible() describes the rows a principal may list. Kinds "
                "are registered through the `scitex_dev.access.kinds` entry point. "
                "v1 has no persistence, so grants come from a JSON fixture."
            ),
            examples=(
                Example(
                    "{prog} dev access check --principal user:alice --action edit "
                    "--resource demo.doc:/users/alice/d1 --fixture world.json",
                    "Decide one request.",
                ),
                Example("{prog} dev access list-kinds --json", "List registered resource kinds."),
            ),
            exit_codes=_EXIT_CODES,
        ),
    )
    @click.pass_context
    def access(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    fixture_option = click.option(
        "--fixture",
        "fixture_path",
        default=None,
        type=click.Path(),
        help="JSON file of kinds, resources, grants and memberships (v1 has no persistence).",
    )
    json_option = click.option(
        "--json", "as_json", is_flag=True, help="Emit the scitex-access/1 record as JSON."
    )

    @access.command(
        "check",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Decide whether a principal may perform an action on a resource.",
            description=(
                "Prints the decision kind and reason on stdout and the detail and "
                "hint on stderr; --json prints the full scitex-access/1 record. A "
                "resource absent from the fixture is decided exactly like a private "
                "one, so the answer never confirms that something exists."
            ),
            examples=(
                Example(
                    "{prog} dev access check --principal agent:alice/bot --action edit "
                    "--resource demo.doc:/users/alice/d1 --fixture world.json --json",
                    "Machine-readable decision for an agent.",
                ),
            ),
            exit_codes=_EXIT_CODES,
        ),
    )
    @click.option("--principal", "principal_text", required=True,
                  help="user:<id>, org:<id>, agent:<owner>/<name> or anonymous.")
    @click.option("--action", required=True, help="A verb the resource's kind declares.")
    @click.option("--resource", "resource_text", required=True, help="<kind>:<path>.")
    @fixture_option
    @json_option
    def check_cmd(
        principal_text: str,
        action: str,
        resource_text: str,
        fixture_path: Optional[str],
        as_json: bool,
    ) -> None:
        fixture = _load_fixture(fixture_path)
        try:
            decision = decide_from_fixture(principal_text, action, resource_text, fixture)
        except AccessConfigError as error:
            raise click.ClickException(str(error)) from error
        if as_json:
            click.echo(json.dumps(decision.to_dict(), ensure_ascii=False))
        else:
            click.echo(f"{decision.kind.value} {decision.reason.value}")
            click.echo(decision.detail, err=True)
            if decision.hint:
                click.echo(f"hint: {decision.hint}", err=True)
        if decision.exit_code:
            raise SystemExit(decision.exit_code)

    @access.command(
        "list-kinds",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List registered resource kinds and the role each action needs.",
            examples=(
                Example("{prog} dev access list-kinds", "One kind per line."),
                Example("{prog} dev access list-kinds --all --json", "Every package's kinds as JSON."),
            ),
        ),
    )
    @click.option("--all", "show_all", is_flag=True, help="Include every package's kinds.")
    @fixture_option
    @json_option
    def kinds_cmd(show_all: bool, fixture_path: Optional[str], as_json: bool) -> None:
        try:
            registry = _registry_with(_load_fixture(fixture_path))
        except AccessConfigError as error:
            raise click.ClickException(str(error)) from error
        specs = [
            spec
            for spec in registry.values()
            if show_all or pkg is None or spec.package in (pkg, "fixture")
        ]
        if as_json:
            click.echo(json.dumps({"kinds": [spec.to_dict() for spec in specs]}, ensure_ascii=False))
            return
        if not specs:
            click.echo("no resource kinds registered", err=True)
        for spec in specs:
            actions = ", ".join(f"{action}={role}" for action, role in spec.actions.items())
            click.echo(f"{spec.name}\t{spec.path_prefix}\t{actions}\t{spec.package}")

    return access


__all__ = ["decide_from_fixture", "register_access_group"]

# EOF
