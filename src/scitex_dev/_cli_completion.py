#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command for shell tab-completion — registered on main CLI group."""

import click


_SOURCE_MAP = {"bash": "bash_source", "zsh": "zsh_source", "fish": "fish_source"}
_RC_MAP = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
    "fish": "~/.config/fish/completions/scitex-dev.fish",
}


def _generate_script(shell: str) -> str:
    import os
    import subprocess

    env = os.environ.copy()
    env["_SCITEX_DEV_COMPLETE"] = _SOURCE_MAP[shell]
    result = subprocess.run(["scitex-dev"], capture_output=True, text=True, env=env)
    script = result.stdout.strip()
    if not script:
        raise click.ClickException(f"Failed to generate {shell} completion script.")
    return script


def register_completion_command(main_group):
    """Register tab-completion commands on the main CLI."""

    @main_group.command(
        "completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def completion_deprecated(ctx):
        """(deprecated) Split into `print-tab-completion` and `install-tab-completion`."""
        click.echo(
            "error: `scitex-dev completion` was split into "
            "`scitex-dev print-tab-completion` and "
            "`scitex-dev install-tab-completion`.\n"
            "Re-run with one of:\n"
            "  scitex-dev print-tab-completion [--shell bash|zsh|fish]\n"
            "  scitex-dev install-tab-completion [--shell bash|zsh|fish]",
            err=True,
        )
        ctx.exit(2)

    @main_group.command("print-tab-completion")
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        help="Target shell. Default: bash.",
    )
    def print_tab_completion(shell):
        """Print the tab-completion script to stdout.

        \b
        Examples:
          scitex-dev print-tab-completion              # bash, stdout
          scitex-dev print-tab-completion --shell zsh  # zsh, stdout
          eval "$(scitex-dev print-tab-completion)"    # activate in current session
        """
        click.echo(_generate_script(shell))

    @main_group.command("install-tab-completion")
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        help="Target shell. Default: bash.",
    )
    def install_tab_completion(shell):
        """Append the eval line to the shell's rc file (idempotent).

        \b
        Examples:
          scitex-dev install-tab-completion               # → ~/.bashrc
          scitex-dev install-tab-completion --shell zsh   # → ~/.zshrc
        """
        import os

        rc_path = os.path.expanduser(_RC_MAP[shell])
        marker = "# scitex-dev tab completion"
        line = (
            f'eval "$(_SCITEX_DEV_COMPLETE={_SOURCE_MAP[shell]} scitex-dev)"  {marker}'
        )
        if os.path.isfile(rc_path):
            with open(rc_path) as f:
                if marker in f.read():
                    click.echo(f"Tab completion already installed in {rc_path}")
                    return
        with open(rc_path, "a") as f:
            f.write(f"\n{line}\n")
        click.echo(f"Tab completion installed in {rc_path}")
        click.echo(f"Run: source {rc_path}")
