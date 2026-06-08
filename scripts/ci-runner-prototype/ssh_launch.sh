#!/bin/bash
# Operator-host wrapper: sshs the runner-start command to the HPC host
# with the GH_TOKEN passed through ssh stdin (no PAT in argv anywhere).
# Returns the detached-process PID for the watchdog to track.
#
# Reads all bindings from ~/.scitex/dev/ci-runner.yaml (or env overrides
# for the prototype). productionization: scitex-dev ci runner up wraps this.
set -eu

GH_TOKEN="$(gh auth token)"
LEASE_JOBID="${LEASE_JOBID:?LEASE_JOBID required}"
GH_REPO="${GH_REPO:?GH_REPO required}"
RUNNER_NAME="${RUNNER_NAME:-scitex-ci-runner-01}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,scitex-ci}"
RUNNER_HOME="${RUNNER_HOME:?RUNNER_HOME required (persistent project-storage path)}"
HPC_HOST="${HPC_HOST:?HPC_HOST required}"
SLURM_SRUN="${SLURM_SRUN:-/apps/slurm/latest/bin/srun}"
LAUNCHER="${LAUNCHER:?LAUNCHER required (absolute path to launcher.sh on the HPC)}"
WRAP_LOG="${WRAP_LOG:?WRAP_LOG required (absolute path on the HPC)}"

ssh -o ControlPath=none -o ControlMaster=no "${HPC_HOST}" bash <<EOF
export GH_TOKEN='${GH_TOKEN}'
export GH_REPO='${GH_REPO}'
export RUNNER_NAME='${RUNNER_NAME}'
export RUNNER_LABELS='${RUNNER_LABELS}'
export RUNNER_HOME='${RUNNER_HOME}'
mkdir -p "\${RUNNER_HOME}"
setsid nohup ${SLURM_SRUN} \
  --overlap --jobid=${LEASE_JOBID} --export=ALL \
  bash '${LAUNCHER}' </dev/null >'${WRAP_LOG}' 2>&1 &
disown
echo "WRAP_PID=\$!"
echo "WRAP_LOG=${WRAP_LOG}"
echo "RUNNER_HOME=${RUNNER_HOME}"
EOF
