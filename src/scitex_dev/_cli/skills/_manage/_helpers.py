#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the `scitex-dev skills` command family."""

import click


def _print_export_result(exported, dest_path, as_json=False):
    """Print export results."""
    import json as json_mod

    if not exported:
        click.echo("No skills found to export.")
        return
    if as_json:
        click.echo(
            json_mod.dumps(
                {k: [str(f) for f in v] for k, v in exported.items()}, indent=2
            )
        )
    else:
        total = sum(len(v) for v in exported.values())
        click.echo(
            f"Exported {total} files across {len(exported)} packages to {dest_path}"
        )
        for k, v in sorted(exported.items()):
            click.echo(f"  {k}: {len(v)} files")
