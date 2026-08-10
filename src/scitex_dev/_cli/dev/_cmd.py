#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev dev`` — the canonical §13 self-maintenance group.

§13 (operator directive) mandates that every self-maintenance surface a package
ships mounts under ONE group named ``dev``, and that package plumbing is never
mounted at top level. The spec is explicit that it enforces the *nesting*, not a
frozen verb list:

    "Each of the six verbs is itself the sub-surface (a group or a leaf as the
     package needs); §13 enforces the nesting, not any fixed verb set inside
     each one."

This module creates that group for scitex-dev itself.

THE `secret` VERB LIVES IN THE LIBRARY, NOT HERE
------------------------------------------------
scitex-dev is the SSOT for how the ecosystem handles credentials, and a leaf
package (scitex-hub, scitex-writer, scitex-scholar, figrecipe, …) must end up
with the SAME surface rather than a similar one. So the group is built by
``scitex_dev.secret.cli.register_secret_group``, which is public, and scitex-dev
mounts it exactly the way a leaf does:

    register_secret_group(dev, pkg="dev")

That is deliberate and not indirection for its own sake. If scitex-dev kept its
own copy, scitex-dev's copy would be the one that got fixed, and every leaf
would drift from it silently — a convention nobody can tell they have stopped
following. Here there is one implementation, so a leaf either has the whole
surface or visibly has none of it.
"""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecGroup
from ...secret.cli import register_secret_group

#: scitex-dev's own store. A leaf passes its own short name instead.
_DEFAULT_PKG = "dev"


def register_dev_commands(main_group) -> click.Group:
    """Register ``scitex-dev dev`` and its verbs on ``main_group``."""

    @main_group.group(
        "dev",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Package self-maintenance surfaces (§13 canonical group).",
            description=(
                "One group for every self-maintenance surface this package "
                "ships. §13 enforces the nesting rather than a fixed verb set, "
                "so verbs are added here as each surface migrates off the top "
                "level."
            ),
            examples=(
                Example("{prog} dev secret list", "List stored secret names."),
            ),
        ),
    )
    @click.pass_context
    def dev(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    register_secret_group(dev, pkg=_DEFAULT_PKG)
    return dev


__all__ = ["register_dev_commands"]


# EOF
