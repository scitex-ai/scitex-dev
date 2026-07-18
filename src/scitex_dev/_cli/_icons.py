#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command: scitex-dev icons -- deterministic name -> icon generator.

Thin click wrapper over ``scitex_dev._icons``. See that package's
docstring for the full Python API (``generate_svg`` / ``generate_png`` /
``save_icon`` / ``resolve_color`` / ``derive_label``).
"""

from __future__ import annotations

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register_icons_command(main_group):
    """Register the `icons` command group on the main CLI group."""

    @main_group.group(
        "icons",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Deterministic name -> icon/avatar generator (SVG + PNG).",
        ),
    )
    def icons_group() -> None:
        pass

    @icons_group.command(
        "generate",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Generate a deterministic icon for NAME (SVG + PNG by default).",
            description=(
                "The name is hashed to derive a stable brand color and a "
                "short label caption; --color/--label override the "
                "derived values. See `scitex_dev._icons` for the "
                "underlying Python API (generate_svg / generate_png / "
                "save_icon / resolve_color / derive_label).",
            ),
            examples=(
                Example(
                    "{prog} icons generate scitex-todo --out ./icons",
                    "Write both formats to ./icons.",
                ),
                Example(
                    "{prog} icons generate my-agent --format svg --no-wordmark",
                    "SVG only, no wordmark caption.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option(
        "--out",
        "out_dir",
        default=".",
        show_default=True,
        help="Output directory.",
    )
    @click.option(
        "--size",
        default=512,
        show_default=True,
        help="Icon size in pixels (square canvas).",
    )
    @click.option("--label", default=None, help="Override the derived short label.")
    @click.option(
        "--color", default=None, help="Override the resolved hex brand color."
    )
    @click.option(
        "--no-wordmark", is_flag=True, help='Omit the "SciTeX" wordmark caption.'
    )
    @click.option(
        "--format",
        "formats",
        multiple=True,
        type=click.Choice(["svg", "png"]),
        default=("svg", "png"),
        show_default=True,
        help="Output format(s); repeat to pick both.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print the file(s) that would be written without rendering "
            "or touching the filesystem. audit-cli §2 — every mutating "
            "verb must expose --dry-run."
        ),
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help=(
            "Accept all confirmation prompts (no-op today; icon "
            "generation never prompts). Required by audit-cli §2 for "
            "mutating verbs so callers can scriptedly bypass any future "
            "confirm logic."
        ),
    )
    def generate_cmd(
        name: str,
        out_dir: str,
        size: int,
        label: str | None,
        color: str | None,
        no_wordmark: bool,
        formats: tuple[str, ...],
        dry_run: bool,
        yes: bool,
    ) -> None:
        del yes  # --yes is reserved for audit-cli §2 conformance; no
                 # confirmation prompts are issued today.
        from .._icons import save_icon

        wordmark = None if no_wordmark else "SciTeX"
        written = save_icon(
            name,
            out_dir,
            size=size,
            label=label,
            color=color,
            wordmark=wordmark,
            formats=tuple(formats),
            dry_run=dry_run,
        )
        verb = "would write" if dry_run else "wrote"
        for _fmt, path in written.items():
            click.echo(f"{verb} {path}")
