#!/bin/bash
# Durable (option-B) SLURM wrapper for the persistent self-hosted runner.
#
# Operator directive 2026-06-14: replace the existing sleep-infinity
# placeholder (`~/.scitex/hpc/scripts/spartan-ci-runner-permanent.sh` on
# spartan-bm159) so the runner auto-launches inside the allocation, and
# auto-recovers across the ~weekly walltime resubmit cycle.
#
# Compared to the placeholder, the only behavioural change is the body
# below the SBATCH/trap block — instead of `sleep infinity & wait $!` we
# call `launcher.sh` (shipped by scitex-dev) which does the persistent
# `./run.sh` loop with backoff and clean TERM-trap deregistration.
# The USR1 walltime trap → sbatch self-resubmit pattern is preserved
# verbatim so the lease keeps rolling without operator intervention.
#
# How to deploy (operator-side, when greenlit):
#   1. Stage launcher.sh on the HPC host:
#        scp $(python -c 'import scitex_dev,os;print(os.path.dirname(scitex_dev.ci.runner.__file__))')/launcher.sh \
#            spartan:~/.scitex/dev/ci-runner/launcher.sh
#   2. Stage this wrapper:
#        scp scripts/hpc/spartan-ci-runner-wrapper.v2.sh \
#            spartan:~/.scitex/hpc/scripts/spartan-ci-runner-permanent.sh
#   3. Stage install-runner.sh + run it (caches the tarball on persistent
#      storage so launcher.sh's first-run fetch is offline-friendly):
#        scp scripts/hpc/install-runner.sh spartan:~/.scitex/dev/ci-runner/install-runner.sh
#        ssh spartan 'bash ~/.scitex/dev/ci-runner/install-runner.sh'
#   4. Author ~/.scitex/dev/ci-runner.yaml (see scripts/hpc/ci-runner.yaml).
#   5. The CURRENT SLURM job (26030530, sleep-infinity wrapper) stays alive
#      until its walltime trap fires (~6 days from start). On that resubmit
#      the NEW wrapper here will run. For IMMEDIATE proof-of-life, use
#      scripts/hpc/srun-overlap-launch.sh which attaches the runner to the
#      currently-running job without waiting for the resubmit cycle.

#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=64
#SBATCH --time=7-0
#SBATCH --mem=128G
#SBATCH --account=punim2354
#SBATCH --qos=publiccpu
#SBATCH --job-name=spartan-ci-runner-permanent
#SBATCH --signal=B:USR1@3600

set -u

_scitex_hpc_walltime_resubmit() {
  echo "[scitex-hpc] walltime approaching; resubmitting via sbatch $0" >&2
  sbatch "$0"
}
trap _scitex_hpc_walltime_resubmit USR1

# --- env contract for launcher.sh ----------------------------------------
# These are READ from ~/.scitex/dev/ci-runner.yaml by the operator-host
# tooling (`scitex-dev ci runner up`), then PASSED to the runner via
# `srun --overlap … --export=ALL`. When we run as the SLURM job's main
# process we have to plumb them ourselves. Source them from a private
# env file the operator owns (path overridable; default below). Each var
# is REQUIRED — no silent defaults to avoid wrong-repo registration.
SCITEX_CI_ENV_FILE="${SCITEX_CI_ENV_FILE:-$HOME/.scitex/dev/ci-runner.env}"
if [ ! -f "$SCITEX_CI_ENV_FILE" ]; then
  echo "[scitex-hpc] FATAL: ${SCITEX_CI_ENV_FILE} missing — wrapper cannot start runner." >&2
  echo "[scitex-hpc] Falling back to sleep-infinity so the SLURM lease is preserved." >&2
  echo "[scitex-hpc] Author ${SCITEX_CI_ENV_FILE} with GH_TOKEN/GH_REPO/RUNNER_* (see scripts/hpc/ci-runner.env.example)." >&2
  sleep infinity &
  wait $!
fi

# shellcheck disable=SC1090
source "$SCITEX_CI_ENV_FILE"
: "${GH_TOKEN:?GH_TOKEN must be set by $SCITEX_CI_ENV_FILE}"
: "${GH_REPO:?GH_REPO must be set by $SCITEX_CI_ENV_FILE}"
: "${RUNNER_NAME:?RUNNER_NAME must be set by $SCITEX_CI_ENV_FILE}"
: "${RUNNER_LABELS:?RUNNER_LABELS must be set by $SCITEX_CI_ENV_FILE}"
: "${RUNNER_HOME:?RUNNER_HOME must be set by $SCITEX_CI_ENV_FILE}"

LAUNCHER="${LAUNCHER:-$HOME/.scitex/dev/ci-runner/launcher.sh}"
if [ ! -x "$LAUNCHER" ]; then
  echo "[scitex-hpc] FATAL: $LAUNCHER not executable — wrapper cannot start runner." >&2
  echo "[scitex-hpc] Falling back to sleep-infinity so the SLURM lease is preserved." >&2
  sleep infinity &
  wait $!
fi

echo "[scitex-hpc] starting persistent runner via $LAUNCHER (env from $SCITEX_CI_ENV_FILE)" >&2
exec "$LAUNCHER"
