#!/bin/bash
# Option (A) IMMEDIATE proof-of-life: attach the GitHub-Actions runner to
# the currently-running SLURM lease job via `srun --overlap --jobid=…`
# (operator's standing rule for attaching work to held reservations).
#
# Use this when:
#   * The persistent SLURM job is already running (won't be touched).
#   * You want the runner online RIGHT NOW, not at the next ~weekly
#     resubmit cycle of the durable wrapper (option B).
#
# Operator-host-side wrapper around `scitex-dev ci runner up` — adds
# auto-detection of the lease job by name so the operator doesn't have
# to look up the jobid.
#
# Prereqs (the runner CLI will tell you if any are missing):
#   1. ~/.scitex/dev/ci-runner.yaml present + valid (see scripts/hpc/ci-runner.yaml).
#   2. $SCITEX_DEV_GH_PAT set (classic PAT with repo + workflow + actions:variables:write).
#   3. A RUNNING SLURM job whose name matches ci_lease.jobname in the config.
#
# Idempotent: re-running on an already-online runner is a no-op unless
# `--replace-runner` is passed (which forces a clean re-registration).

set -euo pipefail

REPLACE_RUNNER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --replace-runner) REPLACE_RUNNER="--replace-runner"; shift ;;
    -h|--help)
      sed -n '1,/^set -euo pipefail$/p' "$0" | sed -e 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "ERR: unknown arg '$1' (try --help)" >&2
      exit 2 ;;
  esac
done

if ! command -v scitex-dev >/dev/null; then
  echo "ERR: scitex-dev CLI not on PATH. pip install scitex-dev (or activate the venv)." >&2
  exit 3
fi

# scitex-dev ci runner up does the heavy lifting:
#   * reads ~/.scitex/dev/ci-runner.yaml
#   * locates the RUNNING SLURM job by ci_lease.jobname
#   * ssh + scp + srun --overlap --jobid=<jobid> --export=ALL bash launcher.sh
#   * launcher.sh registers + runs the persistent listener inside the allocation
echo "[srun-overlap-launch] dispatching to: scitex-dev ci runner up $REPLACE_RUNNER"
exec scitex-dev ci runner up $REPLACE_RUNNER
