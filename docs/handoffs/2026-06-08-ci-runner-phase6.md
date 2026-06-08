# Phase-6 handoff: `scitex-dev ci runner` group + reusable CI template

**To**: proj-scitex-dev (CLI owner) + lead (review).
**From**: proj-scitex-agent-container (prototype).
**Date**: 2026-06-08.

## Purpose

Rolling the self-hosted GitHub Actions runner to every scitex + research repo. Operator green-lit full rollout 2026-06-08. A repo onboards by adding **ONE workflow file** (`.github/workflows/ci.yml`, copy-paste from §2). Headline measurement on the throwaway trial repo `ywatanabe1989/scitex-ci-trial`: **3.30× speedup** (GitHub-hosted ubuntu-latest, nproc=2, `pytest-xdist -n auto`: 76 s wall vs self-hosted in-SIF `-n 16`: 23 s wall, apples-to-apples on a 128 CPU-second workload).

This brief is the implementation contract. proj-scitex-dev wraps the prototyped mechanics as a thin CLI; **nothing here is a rewrite.**

## Public-surface neutrality (binding)

Every PUBLIC string (CLI verb, runner name, runner label, workflow YAML) is generic. No HPC node names, partition names, project ids, or jobname slugs appear anywhere in committed code. The neutrality lint:

```bash
git ls-files ':!docs/handoffs/*' ':!LICENSE' \
  | xargs grep -InE '(spartan|sapphire|bm[0-9]+|h0lder|punim)'   # h0lder = the "h" + "older" word; replace with the literal word at lint time
# expected: zero hits
```

…must pass on every commit. All physical/HPC bindings live in the operator-host private config (§3), gitignored.

## 1. CLI verbs → exact prototype mapping

The CLI lives at `scitex-dev ci runner …`, next to `scitex-dev cron …` and `scitex-dev ecosystem …`. Every verb has a 1:1 underlying call already validated against the trial repo.

| verb | underlying |
|------|---|
| `status` | reads `~/.scitex/dev/ci-runner.yaml` + `gh api repos/<OWNER>/<REPO>/actions/runners` + `gh api repos/<OWNER>/<REPO>/actions/variables/CI_RUNS_ON` + remote `squeue` for the CI lease job by NAME. Prints lease jobid + state, node, runner online?, busy?, `CI_RUNS_ON` current value, last-run xdist N + reason. Single discoverable surface — operator never recalls a value. |
| `status --explain` | same as above + emits the adaptive-xdist tuning table from the same constants the workflow template reads → single source of truth, no doc-drift. |
| `use github` | `gh api -X PATCH repos/<OWNER>/<REPO>/actions/variables/CI_RUNS_ON -f value='"ubuntu-latest"'`. Requires classic-PAT scoped `repo + workflow + actions:variables:write` (per skill 13). PAT is held in env (`SCITEX_DEV_GH_PAT`); bare GitHub variable is implementation detail; operator only types this verb. |
| `use self-hosted` | `gh api -X PATCH repos/<OWNER>/<REPO>/actions/variables/CI_RUNS_ON -f value='["self-hosted","scitex-ci"]'`. |
| `up` | `ssh <hpc_host> 'setsid nohup srun --overlap --jobid=<LEASE_JOBID> --export=ALL bash <LAUNCHER> </dev/null >>WRAP_LOG 2>&1 & disown'` — env (`GH_TOKEN`, `GH_REPO`, `RUNNER_NAME`, `RUNNER_LABELS`, `RUNNER_HOME`) passed via heredoc stdin (no PAT in argv). Default `RUNNER_HOME` is on **persistent project storage** (NOT scratch — scratch is periodically purged). Default `RUNNER_NAME` = `scitex-ci-runner-01`. Default `RUNNER_LABELS` = `self-hosted,scitex-ci`. All physical bindings come from `~/.scitex/dev/ci-runner.yaml`. |
| `down` | mint remove-token (`gh api -X POST .../actions/runners/remove-token`) → `config.sh remove --token <T>` → `gh api -X DELETE .../actions/runners/<id>` → `ssh <hpc_host> 'kill -TERM <WRAP_PID>'`. **NEVER `scancel` the CI lease.** `down` only deregisters the runner. |
| `renew` | `ssh <hpc_host> 'cd ~ && sbatch <SLURM_LOG_FLAGS> <LEASE_SBATCH_SCRIPT>'`. `LEASE_SBATCH_SCRIPT` default is name-filtered to the **CI lease only**; never touches the operator's other compute leases. Returns the new jobid. |
| `onboard <repo>` | copies §2 template into the repo + sets 3 repo Actions Variables (`CI_RUNS_ON`, `SCITEX_CI_APPTAINER`, `SCITEX_CI_SIF`) + sets fork-PR approval requirement. ONE command. |

## 2. The reusable workflow template

This is what every repo copies (verbatim) into `.github/workflows/ci.yml`. **Only the test paths and per-repo `pyproject.toml` deps differ**; everything else is the standard. The template is committed at `scripts/ci-runner-prototype/ci.yml.template` in this branch.

Key properties:

* `runs-on` driven by repo Actions Variable `CI_RUNS_ON`. Default `["self-hosted","scitex-ci"]`. Watchdog auto-flips to `"ubuntu-latest"` on runner-offline; manual override via `scitex-dev ci runner use …`.
* **Inside-SIF execution** on self-hosted: NO per-job `actions/setup-python` extraction (that's what filled the project-space quota in the first measurement attempt — the workflow split removes it). The SIF carries the common scitex base + apt deps (libxcb1, libgl1, libglib2.0-0, …, all of the libxcb-render/-shape/-gthread family).
* **Project deps from `pyproject.toml` at job start**, written to a **writable target** via `uv pip install --target=$TMPDIR/site --no-deps -e .` then `PYTHONPATH=$TMPDIR/site:$PYTHONPATH`. The HPC compute-node HOME is read-only inside the SIF and the SIF's `/opt/venv` is read-only too — `--target=$TMPDIR/site` is the only RO-home-safe pattern. proj-paper-ripple-wm hit this; their runtime-install PR is the canonical example, scitex-dev's template generalizes.
* **Adaptive xdist worker count**, capped to `nproc//2` (physical cores; the `//2` strips HT inflation so future bigger nodes scale automatically — no hardcoded core count). Heuristic by collected_tests:

  | suite shape           | n |
  |---|---|
  | ≤32 tests             | 16 |
  | ≤128 tests            | 32 |
  | >128 tests            | `min(64, nproc//2)` |

  Per-repo override via `[tool.scitex.ci].xdist_workers = N` in pyproject — wins over the heuristic. The `status --explain` verb prints this table from the same constants → single source of truth.

(Full YAML in `scripts/ci-runner-prototype/ci.yml.template` in this branch.)

## 3. Private config contract

Path: `~/.scitex/dev/ci-runner.yaml` (precedence `SCITEX_DEV_CONFIG → $XDG_CONFIG_HOME/scitex/dev → ~/.scitex/dev/`). **All HPC-specific bindings live here, NEVER in committed code.** The schema is at `scripts/ci-runner-prototype/ci-runner.yaml.example` in this branch.

Key sections:

* `hpc` — ssh host, user, apptainer binary path, SIF path. The SIF path is a **dated** pin (NOT a floating `…-latest` symlink) so CI reproducibility doesn't drift when the operator repoints the symlink. Bumped deliberately.
* `runner` — name (`scitex-ci-runner-01`), labels (`[self-hosted, scitex-ci]`), home on persistent project storage, wrap-log path.
* `ci_lease` — jobname, sbatch script path, `renew_threshold_min` (default 1440 = 24 h).
* `github` — PAT env var (`SCITEX_DEV_GH_PAT`, classic-PAT with `actions:variables:write`), default repo, variable name (`CI_RUNS_ON`).
* `watchdog` — poll interval, offline grace, alert channel (`a2a` recommended).

`scitex-dev ci runner status` reads this + makes the live API/squeue calls, prints a single human-readable summary. No env var to remember, no jobid to remember, no path to remember.

## 4. Auto-renewal cron + watchdog

### 4a. CI-lease auto-renewal

Register via `scitex-dev cron register ci-lease-auto-renew --schedule '0 */6 * * *'`. Prototype skeleton at `scripts/ci-runner-prototype/ci_lease_renew.py` in this branch; proj-scitex-dev moves to `src/scitex_dev/ci/runner/lease_renew.py`.

State machine:

1. Read `ci_lease.jobname` from config.
2. `ssh <hpc_host> 'squeue -u <user> --name=<jobname> --noheader -o "%i %T %M %L"'` → list current CI leases **by name** (jobid-agnostic so survives lease cycling).
3. 0 RUNNING + 0 PENDING → submit immediately.
4. 1 RUNNING + `time_left > threshold` → noop.
5. 1 RUNNING + `time_left ≤ threshold` + 0 PENDING → submit successor; brief overlap window during which BOTH run; the runner stays attached to the original via `srun --overlap --jobid`. Operator visibility via `squeue`: 2 CI leases briefly.
6. When the original lease ends (walltime), the watchdog detects and re-attaches the runner to the new lease's jobid via fresh `srun --overlap`.

**Scope guarantee**: the `--name=<jobname>` filter is hard-pinned. The cron NEVER touches the operator's other compute leases (research jobs, GPU leases).

### 4b. Dead-runner watchdog

Recommendation: **sac-agent** (long-lived, restart-resilient, fleet-symmetric). systemd-timer fallback documented for the case where the sac-agent runtime itself is the suspect.

Poll cadence 60 s. State machine:

* Every tick:
  1. `gh api repos/<OWNER>/<REPO>/actions/runners` → does `scitex-ci-runner-01` exist + status=online?
  2. `ssh <hpc_host> 'squeue --name=<jobname> --noheader -o "%i %T %L"'` → is a CI lease running?
* Transitions:
  * `runner_offline_for > offline_grace_min` → **(i)** a2a `[ALERT scitex-ci-runner-down]` to lead AND **(ii)** auto-flip `CI_RUNS_ON = '"ubuntu-latest"'` via gh api PATCH. The "automatic kill-switch" the operator approved.
  * `runner online again` → a2a `[INFO scitex-ci-runner-up]` + flip `CI_RUNS_ON` back. Optional: rerun-failed-jobs on outage-stranded runs (`gh api POST repos/.../actions/runs/<id>/rerun-failed-jobs`).
  * lease NOT running for >2 ticks → try `scitex-dev ci runner renew` once; if it stays PD >30 min → a2a `[ALERT ci-lease-cannot-allocate]`.

### 4c. Phase-5 empirical justification

Run 27135973786 on the trial repo: killed runner mid-flight; queued matrix-cell jobs sat in `queued` state with NO timeout for 5+ minutes and would have continued sitting until each job's `timeout-minutes: 30` tripped. GitHub does NOT auto-fail or auto-fallback. Without the watchdog auto-flip, a runner outage at 9 pm parks every queued job for 30+ min. WITH the auto-flip, the NEXT workflow trigger after `offline_grace_min` routes to hosted; the workflow's default-fallback (`fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"')`) ensures the first ever workflow on a fresh repo also lands on hosted. Required-check semantics are preserved end-to-end.

## Onboarding flow

Goal: a research repo author types ONE command to onboard:

```bash
scitex-dev ci runner onboard <repo-path>
```

What it does (mechanics already prototyped piece-wise):

1. Copies `.github/workflows/ci.yml` (the §2 template) into the repo. Single file, no per-repo edits unless tests/ is non-standard.
2. Sets the repo's Actions Variable `CI_RUNS_ON = '["self-hosted","scitex-ci"]'` via `gh api -X PATCH` (write-PAT). Optional — workflow's default-fallback covers the cold-boot case.
3. Sets `SCITEX_CI_APPTAINER` + `SCITEX_CI_SIF` repo Variables from `~/.scitex/dev/ci-runner.yaml` so the workflow YAML stays neutral.
4. Sets repo Settings → Actions → "Require approval for all outside collaborators" (fork-PR sec).
5. Prints `✅ onboarded — next push routes CI to scitex-ci`.

Rollout plan (operator's): canary on figrecipe + scitex-stats first (high-traffic, measurable speedup), then widen. The trial repo (`scitex-ci-trial`) stays as the canary for template changes.

## Open items / out-of-scope for v1

* **PAT scope acquisition**: the existing fine-grained PAT lacks `actions:variables:write`. Operator's classic-PAT (skill 13) has the right scope. Productionization needs `SCITEX_DEV_GH_PAT` populated on the operator host before `scitex-dev ci runner use` works.
* **Multi-runner pool** (for matrix-axes-meaningful workloads, e.g. py3.11/12/13): documented as the secondary mode; not in scope for v1. The current adaptive-xdist single-job mode already beats hosted on the figrecipe-shape workloads measured.
* **SIF keep-warm**: the 23 s self-hosted floor is dominated by ~9 s of SIF apptainer-exec startup + actions/checkout. A SIF-sandbox-keep-warm mode (one-shot launcher leaves the SIF mounted; subsequent jobs `exec` into the running instance) would cut ~5 s. Phase-7 enhancement.

## What proj-scitex-dev does next

1. Pull the prototype scripts from `scripts/ci-runner-prototype/` in this branch:
   * `launcher.sh` — runs on the HPC compute node inside the `srun --overlap`; downloads + caches actions-runner tarball, registers via the GitHub registration-token API, runs `./run.sh` with backoff, deregisters on TERM trap.
   * `ssh_launch.sh` — operator-host wrapper; passes `GH_TOKEN` via heredoc stdin (no PAT in argv); kicks the launcher via `setsid nohup srun --overlap`.
   * `ci_lease_renew.py` — auto-renewal cron skeleton; name-filtered squeue + sbatch if expiring.
   * `ci.yml.template` — the §2 workflow.
   * `ci-runner.yaml.example` — the §3 private-config schema.
2. Implement the CLI as a `click` group under `src/scitex_dev/ci/runner/__init__.py`. Every verb is a thin wrap over the prototyped commands — no design decisions left.
3. Ship the template at `src/scitex_dev/ci/runner/templates/ci.yml.template`. `scitex-dev ci runner onboard` copies it in.
4. Coordinate with proj-paper-ripple-wm: their runtime-install PR is the canonical example of the writable-`$TMPDIR/site` pattern. Their PR may land first; the scitex-dev template version generalizes it.
5. Canary on figrecipe + scitex-stats. Report numbers via a2a.

Questions on this brief → reply on a2a to proj-scitex-agent-container. I stay available for clarifications.
