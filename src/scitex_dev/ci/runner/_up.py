"""``scitex-dev ci runner up`` — start the persistent runner on HPC."""

from __future__ import annotations

import os
import subprocess
import tempfile

import click

from . import config


def register(group: click.Group) -> None:
    @group.command()
    @click.option(
        "--launcher",
        default=None,
        help="Path to launcher.sh on the HPC host. Default: shipped copy.",
    )
    @click.option(
        "--replace-runner",
        is_flag=True,
        default=False,
        help="Replace any existing runner with the same name.",
    )
    def up_cmd(launcher: str | None, replace_runner: bool) -> None:
        """Start the persistent GitHub Actions runner on the HPC compute node.

        \b
        How it works:
          1. Copies launcher.sh to the HPC host.
          2. SSHs to the HPC host and runs:
             srun --overlap --jobid=<CI_LEASE_JOBID> --export=ALL \\
               bash launcher.sh
          3. The launcher downloads + caches the GitHub runner tarball,
             registers the runner, and runs a persistent run.sh loop.

        \b
        The GH_TOKEN is passed via ssh stdin (never in argv) to avoid
        leaking it into process listings.

        \b
        Example:
          $ scitex-dev ci runner up
          $ scitex-dev ci runner up --replace-runner
        """
        cfg = config.load_runner_config()
        target = config._ssh_target(cfg)
        gh_token = config.get_gh_token(cfg)
        jobname = cfg["ci_lease"]["jobname"]
        runner_home = cfg["runner"]["home"]
        wrap_log = cfg["runner"]["wrap_log"]
        runner_name = cfg["runner"]["name"]
        runner_labels = ",".join(cfg["runner"]["labels"])
        apptainer = cfg["hpc"]["apptainer"]
        sif = cfg["hpc"]["sif"]

        # Determine launcher path — shipped copy in the package
        pkg_launcher = os.path.join(
            os.path.dirname(__file__), "launcher.sh"
        )
        if launcher:
            launcher_path = launcher
        elif os.path.exists(pkg_launcher):
            launcher_path = pkg_launcher
        else:
            raise click.ClickException(
                f"launcher.sh not found. "
                f"Check the scitex-dev package or pass --launcher PATH."
            )

        # Copy launcher to a temp file on the HPC and run it via heredoc
        # Pass env vars through the launcher via environment injection.

        # Read launcher.sh content
        with open(launcher_path, "r") as f:
            launcher_content = f.read()

        # First, get the current lease jobid to check it exists
        lease_info = subprocess.run(
            [
                "ssh",
                "-o",
                "ControlPath=none",
                "-o",
                "ControlMaster=no",
                target,
                f"/apps/slurm/latest/bin/squeue -u {cfg['hpc']['user']} --name={jobname} --noheader -o '%i %T'",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if lease_info.returncode != 0 or not lease_info.stdout.strip():
            raise click.ClickException(
                f"No RUNNING CI lease job found for name={jobname}. "
                f"Run 'scitex-dev ci runner renew' first to submit a lease job."
            )

        # Extract jobid from squeue output
        jobid = None
        for line in lease_info.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "RUNNING":
                jobid = parts[0]
                break

        if not jobid:
            raise click.ClickException(
                f"No RUNNING CI lease job found for name={jobname}. "
                f"See squeue output for available jobs."
            )

        # Now set up the runner on the HPC host:
        # 1. Copy launcher.sh to /tmp on HPC
        # 2. Run via srun --overlap

        # We need to pass the token and env through heredoc to ssh
        # Use a temp file approach: write a wrapper script locally, then scp+ssh
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as tmp:
            # The launcher already handles GH_TOKEN from env; we just need
            # to pass env vars into the srun --overlap context
            tmp.write(f'''#!/bin/bash
set -euo pipefail

# Write launcher to HPC /tmp
cat > /tmp/scitex_ci_launcher.sh << 'LAUNCHER_EOF'
{launcher_content}
LAUNCHER_EOF
chmod +x /tmp/scitex_ci_launcher.sh

# Set environment for the srun --overlap call
export GH_TOKEN='{gh_token}'
export GH_REPO='{cfg['github']['default_repo']}'
export RUNNER_NAME='{runner_name}'
export RUNNER_LABELS='{runner_labels}'
export RUNNER_HOME='{runner_home}'
export APPTAINER='{apptainer}'
export SIF='{sif}'
export RUNNER_VERSION='2.328.0'

# Start the runner via srun --overlap on the existing lease job
setsid nohup srun \\
  --overlap --jobid={jobid} --export=ALL \\
  bash /tmp/scitex_ci_launcher.sh </dev/null >'{wrap_log}' 2>&1 &
disown
echo "RUNNER_STARTED:$!"
''')
            tmp_path = tmp.name

        # SCP the wrapper to HPC and run it
        scp_cmd = [
            "scp",
            "-o",
            "ControlPath=none",
            "-o",
            "ControlMaster=no",
            tmp_path,
            f"{target}:/tmp/scitex_ci_wrapper.sh",
        ]
        scp_result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if scp_result.returncode != 0:
            os.unlink(tmp_path)
            raise click.ClickException(f"SCP failed: {scp_result.stderr.strip()}")
        os.unlink(tmp_path)

        # Run the wrapper on HPC
        run_cmd = [
            "ssh",
            "-o",
            "ControlPath=none",
            "-o",
            "ControlMaster=no",
            target,
            "bash /tmp/scitex_ci_wrapper.sh",
        ]
        run_result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)

        if run_result.returncode != 0:
            raise click.ClickException(
                f"Failed to start runner: {run_result.stderr.strip()}"
            )

        click.echo(run_result.stdout.strip())
        click.echo(f"Runner {runner_name} started on HPC job {jobid}")


# EOF
