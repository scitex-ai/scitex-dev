#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills expand-tags` (+ hidden deprecated `tags-expand`)."""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(skills):
    @skills.command(
        "expand-tags",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=(
                "Print absolute paths of skill files whose frontmatter "
                "`tags:` includes <tag>."
            ),
            description=(
                "Designed for CLAUDE.md `@<tag>` shorthand resolution. "
                "See general/06_skills_06_frontmatter-metadata.md "
                '§"CLAUDE.md tag shortcuts".',
            ),
            examples=(
                Example(
                    "{prog} skills expand-tags scitex-package", "Package-tagged skills."
                ),
                Example("{prog} skills expand-tags research", "Research-tagged skills."),
                Example(
                    "{prog} skills expand-tags scitex-general",
                    "General-tagged skills.",
                ),
            ),
        ),
    )
    @click.argument("tag")
    @click.option(
        "--no-source-tree",
        is_flag=True,
        help="Skip ~/proj/scitex-*/src/*/_skills scan; only use installed packages.",
    )
    def skills_expand_tags(tag, no_source_tree):
        from .._tags import tags_expand

        raise SystemExit(tags_expand(tag, include_source_tree=not no_source_tree))

    # Deprecated bare-noun-leading alias (§1: leaves must start with verb).
    # Removed in 0.11.0.
    @skills.command("tags-expand", hidden=True)
    @click.argument("tag")
    @click.option("--no-source-tree", is_flag=True)
    def _skills_tags_expand_deprecated(tag, no_source_tree):
        """(deprecated) Use `skills expand-tags`. Removed in 0.11.0."""
        click.echo(
            "warning: `skills tags-expand` was renamed to `skills expand-tags` "
            "(verb-noun per §1).",
            err=True,
        )
        from .._tags import tags_expand

        raise SystemExit(tags_expand(tag, include_source_tree=not no_source_tree))


__all__ = ["register"]
