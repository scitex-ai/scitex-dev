"""``scitex-dev ci runner down`` — deregister the runner + stop it."""

from __future__ import annotations

import subprocess

import click

from . import config


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--runner-name",
        default=None,
        help="Runner name to remove. Default: from config.",
    )
    def down_cmd(runner_name: str | None) -> None:
        """Deregister the self-hosted runner and stop it.

        \b
        Steps:
          1. Get remove-token from GitHub API.
          2. Run config.sh remove --token on the runner.
          3. Delete the runner from GitHub.
          4. Kill the wrapper process on the HPC host.

        \b
        NOTE: This NEVER cancels the SLURM lease job — only removes the
        runner from GitHub and kills the runner process.

        \b
        Example:
          $ scitex-dev ci runner down
        """
        cfg = config.load_runner_config()
        target = config._ssh_target(cfg)
        gh_token = config.get_gh_token(cfg)
        repo = cfg["github"]["default_repo"]
        rname = runner_name or cfg["runner"]["name"]

        # Step 1: Find the runner and get remove-token
        find_cmd = [
            "gh",
            "api",
            f"repos/{repo}/actions/runners",
            "--jq",
            f'[.[] | select(.name == "{rname}") | {{"id": .id}}]',
        ]
        find_result = subprocess.run(find_cmd, capture_output=True, text=True, timeout=30)
        if find_result.returncode != 0:
            raise click.ClickException(f"Failed to find runner: {find_result.stderr.strip()}")

        import json

        runners = json.loads(find_result.stdout.strip())
        if not runners:
            raise click.ClickException(f"Runner {rname!r} not found on {repo}")

        runner_id = runners[0]["id"]

        # Step 2: Get remove-token
        remove_token_cmd = [
            "gh",
            "api",
            f"repos/{repo}/actions/runners/{runner_id}/remove-token",
            "-X",
            "POST",
            "--jq",
            '.token',
        ]
        remove_result = subprocess.run(
            remove_token_cmd, capture_output=True, text=True, timeout=30
        )
        if remove_result.returncode != 0:
            raise click.ClickException(
                f"Failed to get remove-token: {remove_result.stderr.strip()}"
            )

        remove_token = remove_result.stdout.strip().strip('"')
        if not remove_token:
            raise click.ClickException("Empty remove-token from GitHub API")

        # Step 3: Run config.sh remove --token on HPC
        ssh_remove = (
            f"ssh -o ControlPath=none -o ControlMaster=no "
            f'{target} '
            f"\"cd {cfg['runner']['home']} && ./config.sh remove --token {remove_token}\""
        )
        rm_result = subprocess.run(
            ssh_remove, capture_output=True, text=True, timeout=30, shell=True
        )
        if rm_result.returncode != 0:
            # Non-fatal — the runner might already be deregistered
            click.echo(f"  (runner remove returned {rm_result.returncode}, continuing)", fg="yellow")

        # Step 4: Delete the runner from GitHub
        delete_cmd = [
            "gh",
            "api",
            f"repos/{repo}/actions/runners/{runner_id}",
            "-X",
            "DELETE",
        ]
        delete_result = subprocess.run(delete_cmd, capture_output=True, text=True, timeout=30)
        if delete_result.returncode != 0:
            raise click.ClickException(
                f"Failed to delete runner: {delete_result.stderr.strip()}"
            )

        # Step 5: Kill the wrapper process on HPC
        kill_cmd = (
            f"ssh -o ControlPath=none -o ControlMaster=no "
            f'{target} '
            f'"pkill -f scitex_ci_launcher || true"'
        )
        subprocess.run(kill_cmd, capture_output=True, text=True, timeout=15, shell=True)

        click.echo(f"Runner {rname} (id={runner_id}) deregistered and stopped.")


# EOF
