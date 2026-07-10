#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command: scitex-dev icons -- deterministic name -> icon generator.

Thin click wrapper over ``scitex_dev._icons``. See that package's
docstring for the full Python API (``generate_svg`` / ``generate_png`` /
``save_icon`` / ``resolve_color`` / ``derive_label``).
"""

from __future__ import annotations

import click


def register_icons_command(main_group):
    """Register the `icons` command group on the main CLI group."""

    @main_group.group("icons")
    def icons_group() -> None:
        """Deterministic name -> icon/avatar generator (SVG + PNG)."""

    @icons_group.command("generate")
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
    def generate_cmd(
        name: str,
        out_dir: str,
        size: int,
        label: str | None,
        color: str | None,
        no_wordmark: bool,
        formats: tuple[str, ...],
    ) -> None:
        """Generate a deterministic icon for NAME (SVG + PNG by default).

        \b
        Example:
            $ scitex-dev icons generate scitex-todo --out ./icons
            $ scitex-dev icons generate my-agent --format svg --no-wordmark
        """
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
        )
        for _fmt, path in written.items():
            click.echo(f"wrote {path}")
