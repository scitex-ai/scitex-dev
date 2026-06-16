"""``scitex-dev ci runner up`` — start the persistent runner on HPC."""

from __future__ import annotations

import os
import subprocess
import tempfile

import click

from . import config

# Absolute SLURM paths: the `up` wrapper runs in a NON-interactive login shell
# where SLURM is not on PATH (so bare `srun`/`squeue` fail). Match these.
_SRUN = "/apps/slurm/latest/bin/srun"
_SQUEUE = "/apps/slurm/latest/bin/squeue"


def _staging_paths(runner_home: str) -> tuple[str, str, str]:
    """Return (stage_dir, wrapper_remote, launcher_remote) on the SHARED FS.

    Staging MUST be on a shared filesystem, never /tmp: Spartan has multiple
    round-robin login nodes and each ssh WITHOUT connection-sharing can land
    on a different node, whose /tmp is node-local; worse, the wrapper runs on
    a login node but `srun` executes the launcher on the COMPUTE node, which
    shares the project FS but not /tmp. runner_home is a punim0264 project dir
    (mounted on every node), so stage under its parent.
    """
    stage_dir = os.path.join(os.path.dirname(runner_home), "run")
    return (
        stage_dir,
        os.path.join(stage_dir, "scitex_ci_wrapper.sh"),
        os.path.join(stage_dir, "scitex_ci_launcher.sh"),
    )


def _build_wrapper_script(
    *,
    runner_home: str,
    launcher_content: str,
    gh_token: str,
    gh_repo: str,
    runner_name: str,
    runner_labels: str,
    apptainer: str,
    sif: str,
    wrap_log: str,
    jobid: str,
) -> str:
    """Build the login-node wrapper script (pure — no I/O).

    Writes the launcher to the SHARED staging dir and starts it via the
    ABSOLUTE srun path under srun --overlap on the existing lease. Both
    invariants are regression-guarded by tests (the two bugs this fixed:
    /tmp staging on multi-login-node Spartan, and bare `srun` not on the
    non-interactive PATH).
    """
    stage_dir, _wrapper_remote, launcher_remote = _staging_paths(runner_home)
    return f"""#!/bin/bash
set -euo pipefail

# Write launcher to the SHARED staging dir (visible to the compute node srun
# runs on — /tmp would not be).
mkdir -p '{stage_dir}'
cat > '{launcher_remote}' << 'LAUNCHER_EOF'
{launcher_content}
LAUNCHER_EOF
chmod +x '{launcher_remote}'

# Set environment for the srun --overlap call
export GH_TOKEN='{gh_token}'
export GH_REPO='{gh_repo}'
export RUNNER_NAME='{runner_name}'
export RUNNER_LABELS='{runner_labels}'
export RUNNER_HOME='{runner_home}'
export APPTAINER='{apptainer}'
export SIF='{sif}'
export RUNNER_VERSION='2.328.0'

# Start the runner via srun --overlap on the existing lease job.
# Absolute srun path: the wrapper runs in a NON-interactive login shell where
# SLURM is not on PATH (matches the absolute squeue path the lease check uses)
# — bare `srun` fails with "No such file or directory".
setsid nohup {_SRUN} \\
  --overlap --jobid={jobid} --export=ALL \\
  bash '{launcher_remote}' </dev/null >'{wrap_log}' 2>&1 &
disown
echo "RUNNER_STARTED:$!"
"""


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
    @click.option(
        "--name",
        "name_override",
        default=None,
        help="Override runner.name from config — provision a SECOND/THIRD "
        "executor (e.g. spartan-cpu-runner-02) for a parallel matrix. "
        "Pair with --home so each runner has its own work/install dir.",
    )
    @click.option(
        "--home",
        "home_override",
        default=None,
        help="Override runner.home — REQUIRED to differ per runner when "
        "running multiple executors (each needs its own _work/install dir).",
    )
    @click.option(
        "--repo",
        "repo_override",
        default=None,
        help="Override github.default_repo — provision a runner for ANOTHER "
        "ecosystem repo (e.g. ywatanabe1989/scitex-todo) on the SAME shared "
        "Spartan lease. This is the ecosystem-rollout path: ywatanabe1989 is a "
        "User (no org runner pool), so each repo needs its own registration, "
        "but they all overlap one lease/node. Pair with --name + --home.",
    )
    @click.option(
        "--labels",
        "labels_override",
        default=None,
        help="Override runner.labels (comma list) for this runner, e.g. "
        "'self-hosted,spartan-cpu,scitex-ci' to also match a repo whose "
        "workflow still targets the legacy label. Default: runner.labels from config.",
    )
    def up_cmd(
        launcher: str | None,
        replace_runner: bool,
        name_override: str | None,
        home_override: str | None,
        repo_override: str | None,
        labels_override: str | None,
    ) -> None:
        """Start the persistent GitHub Actions runner on the HPC compute node.

        \b
        How it works:
          1. Copies launcher.sh to the HPC host (shared FS staging).
          2. SSHs to the HPC host and runs:
             srun --overlap --jobid=<CI_LEASE_JOBID> --export=ALL \\
               bash launcher.sh
          3. The launcher downloads + caches the GitHub runner tarball,
             registers the runner, and runs a persistent run.sh loop.

        \b
        The GH_TOKEN is passed via env (never in argv) to avoid leaking it.

        \b
        Examples:
          $ scitex-dev ci runner up
          $ scitex-dev ci runner up --replace-runner
          # add a second executor (home-clean parallel matrix):
          $ scitex-dev ci runner up --name spartan-cpu-runner-02 \\
              --home /data/.../punim0264/.../ci/actions-runner-02
          # ecosystem rollout: a runner for ANOTHER repo on the SAME lease
          $ scitex-dev ci runner up --repo ywatanabe1989/scitex-todo \\
              --name spartan-cpu-todo-01 \\
              --home /data/.../punim0264/.../ci/actions-runner-todo \\
              --labels self-hosted,spartan-cpu,scitex-ci
        """
        cfg = config.load_runner_config()
        target = config._ssh_target(cfg)
        gh_token = config.get_gh_token(cfg)
        jobname = cfg["ci_lease"]["jobname"]
        runner_home = home_override or cfg["runner"]["home"]
        wrap_log = cfg["runner"]["wrap_log"]
        runner_name = name_override or cfg["runner"]["name"]
        runner_labels = labels_override or ",".join(cfg["runner"]["labels"])
        gh_repo = repo_override or cfg["github"]["default_repo"]
        apptainer = cfg["hpc"]["apptainer"]
        sif = cfg["hpc"]["sif"]

        # Determine launcher path — shipped copy in the package
        pkg_launcher = os.path.join(os.path.dirname(__file__), "launcher.sh")
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
                *config.SSH_MUX_OPTS,
                target,
                f"{_SQUEUE} -u {cfg['hpc']['user']} --name={jobname} --noheader -o '%i %T'",
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

        # Build the login-node wrapper (pure; staging on the SHARED FS, absolute
        # srun — see _build_wrapper_script). Write it locally, then scp+ssh it.
        stage_dir, wrapper_remote, _launcher_remote = _staging_paths(runner_home)
        wrapper_script = _build_wrapper_script(
            runner_home=runner_home,
            launcher_content=launcher_content,
            gh_token=gh_token,
            gh_repo=gh_repo,
            runner_name=runner_name,
            runner_labels=runner_labels,
            apptainer=apptainer,
            sif=sif,
            wrap_log=wrap_log,
            jobid=jobid,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as tmp:
            tmp.write(wrapper_script)
            tmp_path = tmp.name

        ssh_opts = config.SSH_MUX_OPTS

        # Ensure the shared staging dir exists (on the shared FS, so any login
        # node the next connection lands on sees it).
        mkdir_result = subprocess.run(
            ["ssh", *ssh_opts, target, f"mkdir -p '{stage_dir}'"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if mkdir_result.returncode != 0:
            os.unlink(tmp_path)
            raise click.ClickException(
                f"Failed to create staging dir {stage_dir}: {mkdir_result.stderr.strip()}"
            )

        # SCP the wrapper to the shared staging dir.
        scp_cmd = ["scp", *ssh_opts, tmp_path, f"{target}:{wrapper_remote}"]
        scp_result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if scp_result.returncode != 0:
            os.unlink(tmp_path)
            raise click.ClickException(f"SCP failed: {scp_result.stderr.strip()}")
        os.unlink(tmp_path)

        # Run the wrapper on HPC (shared path → any login node sees it).
        run_result = subprocess.run(
            ["ssh", *ssh_opts, target, f"bash '{wrapper_remote}'"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if run_result.returncode != 0:
            raise click.ClickException(
                f"Failed to start runner: {run_result.stderr.strip()}"
            )

        click.echo(run_result.stdout.strip())
        click.echo(f"Runner {runner_name} started on HPC job {jobid}")


# EOF
