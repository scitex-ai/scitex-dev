#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command for shell tab-completion — registered on main CLI group."""

import click


def register_completion_command(main_group):
    """Register completion command on the main CLI."""

    @main_group.command()
    @click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]), default="bash")
    @click.option("--install", is_flag=True, help="Install completion to shell config.")
    def completion(shell, install):
        """Generate or install shell tab-completion script.

        \b
        Examples:
          scitex-dev completion bash          # Print bash completion script
          scitex-dev completion bash --install # Install to ~/.bashrc
          scitex-dev completion zsh            # Print zsh completion script
          eval "$(scitex-dev completion bash)" # Activate in current session
        """
        import os
        import subprocess

        env_var = "_SCITEX_DEV_COMPLETE"
        source_map = {
            "bash": "bash_source",
            "zsh": "zsh_source",
            "fish": "fish_source",
        }
        rc_map = {
            "bash": "~/.bashrc",
            "zsh": "~/.zshrc",
            "fish": "~/.config/fish/completions/scitex-dev.fish",
        }

        env = os.environ.copy()
        env[env_var] = source_map[shell]

        result = subprocess.run(
            ["scitex-dev"],
            capture_output=True,
            text=True,
            env=env,
        )
        script = result.stdout.strip()

        if not script:
            raise click.ClickException(f"Failed to generate {shell} completion script.")

        if install:
            rc_path = os.path.expanduser(rc_map[shell])
            marker = "# scitex-dev tab completion"
            line = (
                f'eval "$(_SCITEX_DEV_COMPLETE={source_map[shell]} scitex-dev)"'
                f"  {marker}"
            )

            # Check if already installed
            if os.path.isfile(rc_path):
                with open(rc_path) as f:
                    if marker in f.read():
                        click.echo(f"Tab completion already installed in {rc_path}")
                        return

            with open(rc_path, "a") as f:
                f.write(f"\n{line}\n")
            click.echo(f"Tab completion installed in {rc_path}")
            click.echo(f"Run: source {rc_path}")
        else:
            click.echo(script)
