# `scitex-dev ci runner ensure` — the CI-runner-lifecycle solver

## Problem

Spartan SLURM jobs max out at a **7-day walltime**. The self-hosted GitHub
Actions runner used to be held alive by an ad-hoc SLURM hold-job submitted
inside `scitex-dev ci runner up` / `renew`. When that hold-job's walltime
expired, the runners died and CI broke fleet-wide — and scitex-dev was
re-implementing lease renewal that **scitex-hpc already solves**.

## Solution: ride on scitex-hpc persistent reservations

`scitex-hpc reservations book --persistent` installs a SLURM SIGUSR1
auto-resubmit trap (`#SBATCH --signal=B:USR1@3600` → `sbatch "$0"`), so the
allocation re-submits itself ~1h before walltime and is effectively permanent.
`scitex-hpc reservations refresh <name>` re-discovers the new `job_id`/`node`
via `squeue` after each walltime re-key (the lease's friendly **name** is
stable even though the SLURM job id cycles).

`scitex-dev ci runner ensure` is a thin, **idempotent, cron-safe** solver on
top of that. It never re-implements lease renewal — it delegates to the
`scitex-hpc reservations` CLI.

### What one `ensure` pass does

1. **Lease** — make a scitex-hpc reservation back CI:
   - `reservations get <name>` exits 2 (no lease file) → `reservations book
     --persistent …`.
   - lease present → `reservations refresh <name>`. If it re-keys to a live
     RUNNING node → **healthy, no booking** (the 7-day boundary is handled by
     scitex-hpc itself). If `refresh` finds no live job (allocation died, or a
     gap the auto-resubmit hasn't bridged) → `reservations cancel` the stale
     lease, then `reservations book` a fresh one.
2. **Runners** — `gh api repos/<owner>/<repo>/actions/runners`; for each
   desired runner GitHub reports **offline/missing**, restart it on the
   reservation's node via `scitex-hpc reservations exec`'s sibling path — the
   same SSH-vector-safe launcher (`ssh -J <login> <node> 'setsid nohup bash
   launcher.sh'`) that `ci runner up` uses. Keeps the configured count online
   (parallelism).
3. **No-op** when the reservation is healthy and N runners are online.

Fresh-book races: if a just-booked reservation has not been allocated a node
yet (still PENDING), runner restart is deferred to the next pass — not an error.

`up` and `down` now share this lease backend: with a `reservation` block in
config, `up` resolves its compute node from the persistent reservation
(book/refresh) instead of the standalone hold-job, and `down` resolves the node
via the **read-only** `refresh` (it never books or cancels — teardown only
deregisters the runner and kills its process).

## Config

Add a `reservation` block to `~/.scitex/dev/ci-runner.yaml` (see
`scripts/ci-runner-prototype/ci-runner.yaml.example`). When present, the legacy
`ci_lease` block is optional/ignored; only `reservation.name` is required.

```yaml
reservation:
  name:        spartan-cpu-64-cores-256-ram   # the scitex-hpc reservation name
  cli:         scitex-hpc                      # or an absolute path for cron PATH
  host:        spartan                         # passed as --host (defaults to hpc.ssh_host)
  partition:   cascade
  cpus:        64
  mem:         256G
  time:        7-0
  account:     <YOUR_SLURM_ACCOUNT>
  qos:         publiccpu
  # Optional explicit pool for parallelism (omit → single runner from runner.*):
  # runners:
  #   - {name: spartan-cpu-runner-01, home: /persist/.../runner-01}
  #   - {name: spartan-cpu-runner-02, home: /persist/.../runner-02}
```

`cli` defaults to `scitex-hpc`; set it to the absolute path (e.g.
`/home/<user>/.venv/bin/scitex-hpc`) when running from cron, where `PATH` is
minimal.

## Usage

```bash
scitex-dev ci runner ensure              # one idempotent pass
scitex-dev ci runner ensure --dry-run    # report decisions, change nothing
scitex-dev ci runner ensure --json       # machine-readable result
```

## Suggested cron

Run `ensure` every ~30 min — well inside the 7-day window, so a single missed
tick never lets the lease lapse, and the cost is two cheap CLI calls when
everything is healthy:

```cron
*/30 * * * * /home/<user>/.venv/bin/scitex-dev ci runner ensure >> ~/.scitex/dev/logs/ci-runner-ensure.log 2>&1
```

Or via the scitex-dev cron surface, if registered there:

```bash
scitex-dev cron register ci-runner-ensure --schedule '*/30 * * * *'
```

The reservation's own SIGUSR1 auto-resubmit bridges the 7-day walltime; this
cron is the watchdog that re-books on a true death and keeps N runners online.
