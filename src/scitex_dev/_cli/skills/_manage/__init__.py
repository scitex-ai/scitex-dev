#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills` command family -- registered on the main CLI group.

Split from the former flat `_manage.py` module (2026-07-11,
CLI-standardization audit pass §4b) — one command per file, mirroring
the `_audit_per_target/` and `_branch_protection/` package splits.
`_cli/skills/__init__.py`'s `from ._manage import register_skills_commands`
call site is unchanged since a package's `__init__.py` satisfies the
same import shape as the former module.
"""

from ...._ecosystem.help_spec import CliHelp, SpecGroup
from ._expand_tags_cmd import register as _register_expand_tags
from ._explain_self_cmd import register as _register_explain_self
from ._get_cmd import register as _register_get
from ._init_cmd import register as _register_init
from ._install_cmd import register as _register_install
from ._list_cmd import register as _register_list


def register_skills_commands(main_group):
    """Register the `skills` command group on the main CLI."""
    import click

    @main_group.group(
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Manage skills across the SciTeX ecosystem.",
        ),
    )
    @click.pass_context
    def skills(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _register_list(skills)
    _register_get(skills)
    _register_init(skills)
    _register_install(skills)
    _register_explain_self(skills)
    _register_expand_tags(skills)

    return skills


__all__ = ["register_skills_commands"]
