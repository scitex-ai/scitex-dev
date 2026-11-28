"""``scitex-dev linter completion`` group + ``show-completion-*`` leaves.

Extracted from ``cli.py`` (512-line budget). Registered onto the root
group via :func:`register`. The lower-level script generator lives in
``_cmd_completion``; this module is the CLI surface only.
"""

from __future__ import annotations

import json

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
                    "Install the scitex-dev completion drop-in.",
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
            summary="Install the completion drop-in (never edits shell rc files).",
            examples=(
                Example(
                    "{prog} linter completion install", "Auto-detect the shell."
                ),
                Example(
                    "{prog} linter completion install --shell zsh",
                    "Install the zsh drop-in.",
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
        # The linter is a subgroup of `scitex-dev`, so its words complete
        # through scitex-dev's own completion. Install that drop-in via the
        # shared helper; no rc file is touched (scitex-dev#1127).
        import os

        from .._cli import main as root_cli
        from .._cli._completion import install_completion

        del yes  # install never prompts
        if not shell:
            shell = "zsh" if "zsh" in os.environ.get("SHELL", "") else "bash"
        outcomes = install_completion(root_cli, shell, ("scitex-dev",), dry_run=dry_run)
        if as_json:
            rows = [
                {"prog": o.prog_name, "path": str(o.path), "status": o.status}
                for o in outcomes
            ]
            click.echo(json.dumps(rows, indent=2))
            return
        for o in outcomes:
            click.echo(f"{o.status}: {o.path}")

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

        from .._cli._completion import completion_dropin_path

        shell = "zsh" if "zsh" in os.environ.get("SHELL", "") else "bash"
        dropin = completion_dropin_path(shell, "scitex-dev")
        installed = dropin.is_file()

        if as_json:
            click.echo(
                json.dumps(
                    {"shell": shell, "path": str(dropin), "installed": installed},
                    indent=2,
                )
            )
            return

        click.echo(f"Shell:  {shell}")
        click.echo(f"File:   {dropin}")
        click.echo(f"Status: {'installed' if installed else 'not installed'}")
        if not installed:
            click.echo("\nInstall with: scitex-dev install-shell-completion")

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
