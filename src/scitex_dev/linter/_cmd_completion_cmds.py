"""``scitex-dev linter completion`` group + ``show-completion-*`` leaves.

Extracted from ``cli.py`` (512-line budget). Registered onto the root
group via :func:`register`. The lower-level script generator lives in
``_cmd_completion``; this module is the CLI surface only.
"""

from __future__ import annotations

import json
import sys

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def _completion_script(shell):
    from ._cmd_completion import _generate_completion_script

    return _generate_completion_script(shell)


def register(main_group):
    """Attach the completion commands to ``main_group``."""

    @main_group.group(
        "completion",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Shell tab-completion management.",
            examples=(
                Example(
                    "{prog} linter completion install --shell bash",
                    "Install completion into ~/.bashrc.",
                ),
                Example(
                    "{prog} linter show-completion-status",
                    "Report whether completion is installed.",
                ),
            ),
        ),
    )
    def completion_group():
        pass

    @completion_group.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Install completion to shell RC file.",
            examples=(
                Example(
                    "{prog} linter completion install", "Auto-detect the shell."
                ),
                Example(
                    "{prog} linter completion install --shell zsh",
                    "Target ~/.zshrc explicitly.",
                ),
                Example(
                    "{prog} linter completion install --dry-run",
                    "Show what would be written.",
                ),
            ),
        ),
    )
    @click.option(
        "--shell",
        type=click.Choice(["bash", "zsh"]),
        default=None,
        help="Shell type (auto-detected if not provided).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Show what would be installed without writing.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        default=False,
        help="Skip confirmation.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def completion_install(shell, dry_run, yes, as_json):
        import os

        if not shell:
            shell_env = os.environ.get("SHELL", "")
            shell = "zsh" if "zsh" in shell_env else "bash"

        script = _completion_script(shell)
        if not script:
            click.echo(f"Unsupported shell: {shell}", err=True)
            sys.exit(1)

        rc_file = os.path.expanduser("~/.bashrc" if shell == "bash" else "~/.zshrc")

        if os.path.exists(rc_file):
            with open(rc_file) as f:
                if "scitex-dev linter tab completion" in f.read():
                    click.echo(f"Completion already installed in {rc_file}")
                    return

        if dry_run:
            click.echo(f"Would append completion script to {rc_file}")
            return

        if not yes:
            click.echo(
                f"Refusing to modify {rc_file} without --yes/-y.",
                err=True,
            )
            raise SystemExit(2)

        with open(rc_file, "a") as f:
            f.write(f"\n{script}\n")
        click.echo(f"Completion installed in {rc_file}")
        click.echo(f"Reload with: source {rc_file}")

    @main_group.command(
        "show-completion-status",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show shell completion installation status.",
            examples=(
                Example(
                    "{prog} linter show-completion-status", "Human-readable status."
                ),
                Example(
                    "{prog} linter show-completion-status --json",
                    "Machine-readable status.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def show_completion_status(as_json):
        import os

        shell_env = os.environ.get("SHELL", "")
        shell = "zsh" if "zsh" in shell_env else "bash"
        rc_file = os.path.expanduser("~/.bashrc" if shell == "bash" else "~/.zshrc")
        installed = False
        if os.path.exists(rc_file):
            with open(rc_file) as f:
                if "scitex-dev linter tab completion" in f.read():
                    installed = True

        if as_json:
            click.echo(
                json.dumps(
                    {"shell": shell, "rc_file": rc_file, "installed": installed},
                    indent=2,
                )
            )
            return

        click.echo(f"Shell:  {shell}")
        click.echo(f"RC:     {rc_file}")
        click.echo(f"Status: {'installed' if installed else 'not installed'}")
        if not installed:
            click.echo("\nInstall with: scitex-dev linter completion install")

    @main_group.command(
        "show-completion-bash",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print the bash completion script to stdout.",
            examples=(
                Example(
                    "{prog} linter show-completion-bash "
                    "> /etc/bash_completion.d/scitex-dev-linter",
                    "Install system-wide.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def show_completion_bash(as_json):
        script = _completion_script("bash")
        if as_json:
            click.echo(json.dumps({"shell": "bash", "script": script}, indent=2))
        else:
            click.echo(script)

    @main_group.command(
        "show-completion-zsh",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print the zsh completion script to stdout.",
            examples=(
                Example(
                    "{prog} linter show-completion-zsh "
                    "> ~/.zsh/completions/_scitex-dev-linter",
                    "Install for the current user.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def show_completion_zsh(as_json):
        script = _completion_script("zsh")
        if as_json:
            click.echo(json.dumps({"shell": "zsh", "script": script}, indent=2))
        else:
            click.echo(script)

    return completion_group


# EOF
