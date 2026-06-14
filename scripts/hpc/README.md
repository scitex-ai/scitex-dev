# Spartan CI runner — operator pre-staging

Artifacts that land on the HPC host (spartan-bm159 today) so the existing
`scitex-dev ci runner` machinery has everything it needs.

Operator directive 2026-06-14: prefer the self-hosted Spartan CPU runner,
fall back to GitHub-hosted ONLY when unavailable, and make that fallback
LOUD (operator's phrase: 「スパルタンが可能な時は必ずスパルタンCPUノードを使う、フォール
バックでGitHubでもよいがうるさくフォールバックする」).

## What's here

| File | Role | Operator action |
|------|------|-----------------|
| `install-runner.sh` | Idempotent download + sha256 verify of `actions-runner-linux-x64-2.328.0.tar.gz` into a cache dir launcher.sh reads. | `bash install-runner.sh` on spartan-bm159, once. |
| `srun-overlap-launch.sh` | Option (A) — IMMEDIATE proof-of-life via `srun --overlap --jobid=<lease>`. Thin wrapper around `scitex-dev ci runner up`. | `bash srun-overlap-launch.sh` after config.yaml + PAT are in place. |
| `spartan-ci-runner-wrapper.v2.sh` | Option (B) — DURABLE wrapper replacing the sleep-infinity placeholder so the runner auto-launches inside the allocation on every walltime resubmit. | `cp` over `~/.scitex/hpc/scripts/spartan-ci-runner-permanent.sh` once green-tested. |
| `ci-runner.yaml` | Concrete `~/.scitex/dev/ci-runner.yaml` template pre-filled where derivable (user, ssh_host, ci_lease.jobname matching job 26030530, default_repo). | `cp ci-runner.yaml ~/.scitex/dev/ && chmod 0600`, replace `<TODO_…>`. |
| `ci-runner.env.example` | Source-file consumed by `spartan-ci-runner-wrapper.v2.sh` when it runs as the SLURM job's main process (no srun-overlap intermediate). | `cp ci-runner.env.example ~/.scitex/dev/ci-runner.env && chmod 0600`, replace `<TODO_…>`. |

## How the two options compose

- **A (immediate)**: SLURM job 26030530 keeps its sleep-infinity body — operator
  runs `bash srun-overlap-launch.sh` on the workstation; it `srun --overlap`s
  the runner into the existing allocation. Runner stays online for the
  remaining ~6 days of the current SLURM job's walltime, then dies when the
  current job resubmits itself (the new resubmit will still be sleep-infinity
  because the wrapper file on disk hasn't changed).
- **B (durable)**: Operator `cp`s `spartan-ci-runner-wrapper.v2.sh` over
  `~/.scitex/hpc/scripts/spartan-ci-runner-permanent.sh`. The current SLURM
  job continues running its old sleep-infinity body unaffected. When the
  next walltime resubmit fires (USR1 trap → `sbatch $0`), the NEW wrapper
  picks up and the runner auto-launches inside the freshly-allocated job.

A + B together: operator runs A NOW for immediate proof-of-life, deploys B
ahead of the next walltime so the proof persists across resubmits.

## What's NOT here

- The classic GitHub PAT (`SCITEX_DEV_GH_PAT`) — operator-owned, never
  committed.
- The Apptainer/SIF paths inside ci-runner.yaml — operator-host-dependent.
- The actual runner home directory on punim2354 — operator picks the path.

These five host items (PAT, APPTAINER, SIF, RUNNER_HOME, RUNNER_HOME wrap_log)
are flagged with `<TODO_…>` markers in `ci-runner.yaml` and the env file.

## LOUD-fallback wiring

The ecosystem-side change lives in
`src/scitex_dev/ci/runner/templates/ci.yml.template`: when CI lands on a
GitHub-hosted runner (because `vars.CI_RUNS_ON` was watchdog-flipped to
`"ubuntu-latest"`, or unset), the first step emits

```
::warning title=Spartan UNAVAILABLE — CI fell back to GitHub-hosted::<reason>
```

plus a `$GITHUB_STEP_SUMMARY` block with the exact `scitex-dev ci runner
…` invocation needed to recover. Visible in the PR Checks UI + run
summary; impossible to silently fall back.
