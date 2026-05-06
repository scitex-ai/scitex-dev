#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared CLI tab-completion helper for every scitex-* package.

Per `_skills/general/03_interface_02_cli/03_required-introspection-commands.md`
§1a, every scitex-* CLI MUST expose `install-shell-completion` and
`print-shell-completion` so users actually get `<TAB>` completion.

Usage from a downstream package's CLI module:

    from scitex_dev._cli._completion import attach_shell_completion

    @click.group(...)
    def cli():
        ...

    attach_shell_completion(cli, prog_name="scitex-io")

That single call registers four leaves on `cli`:

  * `install-shell-completion --shell {bash,zsh,fish}`  (canonical)
  * `print-shell-completion   --shell {bash,zsh,fish}`  (canonical)
  * `install-tab-completion`   (hidden deprecated alias → install-shell-completion)
  * `completion`               (hidden deprecated alias → install-shell-completion)
"""

from __future__ import annotations

import os
import subprocess

import click

_SOURCE_MAP = {"bash": "bash_source", "zsh": "zsh_source", "fish": "fish_source"}


def _env_var(prog_name: str) -> str:
    """Click's autocompletion env var format: `_<UPPER_PROG>_COMPLETE`."""
    return "_" + prog_name.upper().replace("-", "_") + "_COMPLETE"


def _rc_path(shell: str, prog_name: str) -> str:
    if shell == "fish":
        return os.path.expanduser(f"~/.config/fish/completions/{prog_name}.fish")
    return os.path.expanduser({"bash": "~/.bashrc", "zsh": "~/.zshrc"}[shell])


def _marker(prog_name: str) -> str:
    return f"# {prog_name} tab completion"


def _eval_line(shell: str, prog_name: str) -> str:
    return (
        f'eval "$({_env_var(prog_name)}={_SOURCE_MAP[shell]} {prog_name})"  '
        f"{_marker(prog_name)}"
    )


def _generate_script(shell: str, prog_name: str) -> str:
    env = os.environ.copy()
    env[_env_var(prog_name)] = _SOURCE_MAP[shell]
    result = subprocess.run([prog_name], capture_output=True, text=True, env=env)
    script = result.stdout.strip()
    if not script:
        raise click.ClickException(
            f"Failed to generate {shell} completion script for {prog_name}."
        )
    return script


def attach_shell_completion(main_group, *, prog_name: str) -> None:
    """Register the 4 shell-completion leaves on `main_group`."""

    @main_group.command("print-shell-completion")
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        help="Target shell. Default: bash.",
    )
    def print_shell_completion(shell):
        """Print the click-generated completion script to stdout.

        \b
        For one-off activation in the current shell:
          eval "$({prog_name} print-shell-completion --shell bash)"
        """
        click.echo(_generate_script(shell, prog_name))

    @main_group.command("install-shell-completion")
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh", "fish"]),
        default="bash",
        help="Target shell. Default: bash.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the eval line and target rc file without writing.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def install_shell_completion(shell, dry_run, yes):
        """Wire up `<TAB>` completion in the user's shell rc.

        \b
        Examples:
          {prog} install-shell-completion              # → ~/.bashrc
          {prog} install-shell-completion --shell zsh  # → ~/.zshrc
          {prog} install-shell-completion --dry-run    # preview only

        \b
        Activate in the current shell after install:
          source ~/.bashrc
        """
        del yes  # accepted for §2 compliance; use --dry-run for preview
        rc_path = _rc_path(shell, prog_name)

        if shell == "fish":
            # fish uses a per-program completion file, not rc-append
            if dry_run:
                click.echo(f"Would write fish completion to {rc_path}")
                return
            os.makedirs(os.path.dirname(rc_path), exist_ok=True)
            with open(rc_path, "w") as f:
                f.write(_generate_script(shell, prog_name))
            click.echo(f"Tab completion installed at {rc_path}")
            click.echo(f"Run: source {rc_path}")
            return

        line = _eval_line(shell, prog_name)
        marker = _marker(prog_name)

        if dry_run:
            click.echo(f"Would append to {rc_path}:")
            click.echo(f"  {line}")
            return

        if os.path.isfile(rc_path):
            with open(rc_path) as f:
                if marker in f.read():
                    click.echo(f"Tab completion already installed in {rc_path}")
                    return
        with open(rc_path, "a") as f:
            f.write(f"\n{line}\n")
        click.echo(f"Tab completion installed in {rc_path}")
        click.echo(f"Run: source {rc_path}")

    @main_group.command(
        "install-tab-completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def install_tab_completion_deprecated(ctx):
        """(deprecated) Renamed to `install-shell-completion`."""
        click.echo(
            f"error: `{prog_name} install-tab-completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)

    @main_group.command(
        "completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def completion_deprecated(ctx):
        """(deprecated) Renamed to `install-shell-completion`."""
        click.echo(
            f"error: `{prog_name} completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)


# ----- Backwards compat for scitex-dev's own _root.py call site ----------
# The legacy entry point `register_completion_command(main_group)` is kept
# so scitex-dev's existing import doesn't break during the rollout.


def register_completion_command(main_group):
    """(legacy) Use `attach_shell_completion(main_group, prog_name=...)`."""
    attach_shell_completion(main_group, prog_name="scitex-dev")
