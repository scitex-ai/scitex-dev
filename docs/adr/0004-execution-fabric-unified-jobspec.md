# ADR-0004: Execution fabric — one declarative JobSpec, intent/mechanism orthogonality, best-effort allocation onto the shared pool, phased adoption

## Status

Accepted (2026-07-22). Operator-approved direction (2026-07-22): "declare jobs
uniformly; separate INTENT (daemon/periodic/one-shot) from MECHANISM
(local/Slurm/runner); allocate best-effort onto idle resources; phased
adoption: tests first, then CI, then agent jobs." This ADR records the
unifying architecture; it does not re-litigate the direction.

## Context

The SciTeX ecosystem runs (at least) four families of compute jobs today, each
with its own declaration surface, its own executor wiring, and no shared
resource model:

1. **Test suites** — the test-execution recipe shipped in #385
   (`src/scitex_dev/_core/test_execution.py`): a per-package
   `TestExecutionConfig` (`local` | `remote-required`) with a free-form
   `submit_template`, a `test_execution` knob, and an auto-loaded `pytest11`
   guard (`_test_execution_plugin.py`) that blocks local pytest when a package
   mandates remote.
2. **CI** — GitHub Actions across ~70 repos, mid-consolidation onto the ONE
   canonical thin org-reusable caller
   (`src/scitex_dev/_ecosystem/ci_template/templates/ci.yml.tmpl`, #400): job
   bodies live once in `scitex-ai/.github@main`; runner selection is the
   Actions Variable `vars.CI_RUNS_ON`. The 2026-07-21 CI-drift inventory
   found **five** self-hosted runner-label vocabularies plus 651
   `ubuntu-latest` violations spread over six workflow generations — the cost
   of never having had one declaration model.
3. **Experiments / research pipelines** — ad hoc `srun`/`sbatch`/ssh onto
   Spartan, no uniform receipt, no uniform resource declaration.
4. **Agent/fleet jobs** — periodic and daemon work (sac restart passes,
   drift timers, sweeps), partially federated through the
   `scitex_dev.jobs.JobSpec` entry-point contract
   (`scitex_dev/jobs/__init__.py`, group `scitex_dev.jobs`), partially still
   hand-rolled crons on hosts.

Two prior design artifacts cover slices of this space and must be reconciled,
not duplicated:

- **The phase-1 execution-fabric design** (`docs/design/execution-fabric-phase1.md`,
  merged as PR #388) locks four interfaces — `ContainerContract`,
  `ResourceSpec`, `JobSpec`/`JobHandle` with the
  `submit/status/logs/cancel/collect` `ExecutionBackend` Protocol, and the
  anti-false-claim `JobReceipt` — and scopes phase-1 to exactly two backends
  (`local`, `slurm`). Its strategic rule stands: **do not reinvent the
  executor** (Snakemake/Parsl/Slurm/Batch are prior art); SciTeX adds the
  policy + can't-misuse + agent-DX layer.
- **The JobSpec federation contract** (fleet card + GITIGNORED contract doc,
  2026-07-20) establishes that a leaf never runs its own cron/systemd: it
  *declares* `JobSpec`s via the `scitex_dev.jobs` entry-point group and
  scitex-dev discovers, merges, lowers, and installs them
  (`ecosystem {systemd,cron,up,run}`). Its open thread — a `kind` taxonomy
  note separating INTENT (daemon/periodic) from MECHANISM
  (service/timer/cron) — is exactly the axis split this ADR decides.

The problem: these two `JobSpec`s (the fabric's batch-job spec and the
federation's scheduled-job spec) grew independently, CI declares nothing in
either, and "where may this run, with what resources" is answered by four
different mechanisms. Meanwhile the operator directed the runner fleet toward
**one shared pool** (org runners + Spartan, best-effort onto idle capacity),
which no per-family mechanism can express.

## Decision

Adopt **one ecosystem-wide execution-fabric model** with four load-bearing
decisions.

### 1. One declarative JobSpec; INTENT and MECHANISM are orthogonal axes

Every job — test run, CI job, experiment, agent/fleet job — is declared by a
single conceptual JobSpec with two independent axes:

- **INTENT** (what lifecycle the work wants):
  `one-shot` | `periodic` | `daemon` | `reactive`.
  - `one-shot` — run once to completion (a test suite, an experiment trial).
  - `periodic` — run on a schedule (drift timers, sweeps, nightly CI).
  - `daemon` — long-running, supervised, restart-on-death (sac agents,
    listeners).
  - `reactive` — run when an external event fires (PR push → CI, card event
    → handler).
- **MECHANISM** (what engine executes it):
  `local-exec` | `slurm` | `gh-runner` | `systemd/cron`.

**No declaration may name a mechanism where an intent belongs, and vice
versa.** A leaf says "this is periodic, every 2 min, needs 1 cpu"; the fabric
(scitex-dev) chooses systemd-timer vs cron vs a Slurm scrontab. A test recipe
says "remote-required, 8 cpu"; the fabric chooses the slurm backend and the
partition. This generalizes what the federation contract already enforces
("`kind` is INTENT … Do NOT pick the mechanism") and resolves its open
taxonomy thread: the current `service`/`timer`/`cron` kinds are re-read as
`daemon` / `periodic` / `periodic` intents, with `timer`-vs-`cron` demoted to
a mechanism choice the lowering step makes (and the #369 rule stands: lowering
that would silently drop a guarantee like `timeout_sec`/`venv` must refuse
loudly instead).

**Resources are declared, never implied.** The backend-neutral `ResourceSpec`
(`cpu` / `memory_gb` / `gpu` / `walltime_min`) from the phase-1 design is the
one resource vocabulary. Declarations never contain `partition:`,
`instance_type:`, or runner hostnames; each mechanism adapter translates
(`cpu → --cpus-per-task`, `cpu → pytest -n <allocated>`, labels → runner
selection). The allocated-cpus rule from phase-1 §3c is part of this: a job
sees its *allocated* budget, never the literal node core count.

The phase-1 batch `JobSpec` (container + resources + command) and the
federation `JobSpec` (name + schedule + command + guarantees) are hereby two
**profiles of the same model** — a one-shot profile and a periodic/daemon
profile — and converge field-by-field as phase 3 lands (shared `ResourceSpec`,
shared receipt/log conventions, one discovery surface). Neither is rewritten
today; new fields land in the unified vocabulary only.

Reproducibility-bearing jobs (tests, experiments) additionally carry the
phase-1 `ContainerContract` (commit + image + recipe, no dirty-tree state) and
must yield a `JobReceipt` from `collect()` — the anti-false-claim artifact
(real commit, backend, allocated cpu, pass/fail). Ephemeral fleet plumbing
(a restart pass) is exempt from the container contract but not from logging
(`~/.scitex/<pkg>/runtime/logs/<name>.log`, scitex-dev-owned).

### 2. Allocation: best-effort onto the shared pool

There is **one shared compute pool**: the org self-hosted runners plus
Spartan idle/backfill capacity. Allocation is **best-effort** — jobs state
resources and constraints; the fabric places them onto whatever pool capacity
is free, with no per-repo or per-team runner ownership.

- The **CI-facing slice** of this pool is the runner-label unification
  already in flight: `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '["self-hosted","Linux","X64","scitex-ci"]') }}`
  in the org-side reusable bodies, with `vars.CI_RUNS_ON` (repo → org
  precedence) as the single selection knob. The five current label
  vocabularies collapse to ONE (the CI-drift inventory's target); GitHub-
  hosted runners remain forbidden (PS-169, ERROR).
- The **batch-facing slice** is the phase-1 `slurm` backend: `srun --overlap`
  into an existing lease where one is held (no queue wait), `sbatch`
  otherwise, compute nodes only — never the login node. Spartan is ONE
  resource; internal placement is delegated to Spartan's native Slurm via
  the `submit_template`. The fabric never nests a second scheduler
  controller inside Slurm.
- Best-effort means **no reservations and no fairness engine in SciTeX**:
  contention is resolved by the underlying engines (Slurm priorities, the
  Actions queue). The fabric's job is to route to *idle* capacity and to
  refuse *forbidden* placements (laptop-heavy-test, login-node pytest,
  GPU-test-on-CPU), not to arbitrate between permitted ones.
- The routing selector (`--target fastest|cheapest|local-only|secure`) stays
  deferred exactly as phase-1 left it; until it lands, backend choice is
  explicit per declaration.

### 3. Ownership: ports-and-adapters boundaries (per ADR-0003)

The seams are extension points, not hard imports — the ecosystem's default
seam rule (ADR-0003) applied to compute:

| Owner | Owns | Does NOT own |
| --- | --- | --- |
| **scitex-dev** | The fabric **primitives** (JobSpec model, `ResourceSpec`, receipt schema, intent taxonomy), the **policy/guard layer** (recipes, knobs, pytest11 guard, auditor rules), and **aggregation**: the single job aggregator for all repetitive jobs — plugin federation via the `scitex_dev.jobs` entry-point group; leaves declare, scitex-dev discovers/merges/lowers/installs; **no hardcoded or leaf-local crons**. | Slurm mechanics, container lifecycle. |
| **scitex-hpc** | Spartan **capacity mechanics**: the `ExecutionBackend` implementations (`local`, `slurm`), `ResourceSpec` → backend-vocabulary translation (partition/account/`--cpus-per-task`), the resource registry + liveness probes, runner provisioning on Spartan. | Policy (what is allowed to run where), job declaration schemas. |
| **sac** | **Container/daemon lifecycle**: agent containers, supervised daemon processes, restart/heal passes. sac keeps its detection + restart logic; it registers only the *scheduling* of its passes as federation JobSpecs (intent `periodic`), per the federation contract. | Scheduling installation (cron/systemd rendering — scitex-dev's), Spartan submission. |

Leaf packages interact with the fabric only through declaration surfaces
(recipe YAML, knob, entry-point provider) — kind-c edges in the ADR-0003
taxonomy — never by importing backend internals. The interface-home question
from phase-1 §6 (shared spec module vs a thin `scitex-execspec` package)
remains open with the same recommendation: a thin shared spec so neither side
co-locks the other's release (standalone-independence).

### 4. Failure doctrine: fail-safe on the invocation path, fail-loud in gates

The house pattern, already shipped twice, is now fabric-wide law:

- **Invocation paths fail safe.** Anything auto-loaded into every
  environment must never brick the host process. Precedents: the #385 recipe
  loader (malformed YAML / unreadable file / discovery error → warn +
  inert `mode=local`, pytest never crashes) and the currency gate's
  FRESHNESS half (#396: never a blocking network call; offline → PASS).
  Fabric corollaries: a missing/unparseable JobSpec declaration disables
  that job with a loud warning, it does not take down the aggregator run;
  an unreachable backend fails *that submission* with an actionable error,
  not the fabric.
- **Gates fail loud.** Anything whose job is to *verify* must never report
  green for what it could not check. Precedents: the currency gate's
  INTEGRITY half raising `StalenessError` with the exact remedy, the
  deterministic audit target-tree resolution (#397 — an audit that might
  grade the wrong checkout now names which tree it resolved and how), and
  the PS-221 `[all]`-closure ERROR rule. Fabric corollaries: the pytest11
  remote-required guard aborts with `UsageError`; a `collect()` that cannot
  fill the mandatory receipt fields (commit, backend, allocated cpu,
  pass/fail) is non-conformant and errors; the timer→cron lowering refuses
  to drop guarantees (#369); the CI auditor ERRORs on `ubuntu-latest` and
  non-canonical workflow files.

The dividing line: **is this code path *running* work or *vouching* for
work?** Running → degrade gracefully, warn loudly. Vouching → refuse loudly;
skipped must never count as clean.

### Phased adoption — with exit criteria

| Phase | Scope | Status | Exit criteria |
| --- | --- | --- | --- |
| **P1** | **Tests** | Shipped (#385, v0.33.0; design locked by #388) | (a) recipe + `test_execution` knob + auto-loaded `pytest11` guard live (done); (b) literal `-n auto` resolved from allocated-cpus per backend via `scitex_dev._core.test_execution.allocated_cpus` (done for `ecosystem test-remote`); (c) at least one `remote-required` package runs end-to-end through the scitex-hpc `slurm` backend and every run emits a conformant `JobReceipt`. |

> **P1(b) correction (measured 2026-07-23).** An earlier draft of this row
> named `$SLURM_CPUS_PER_TASK` as *the* source. It is not sufficient: on the
> Spartan CI runner that variable is **empty**. The runner is reached by ssh
> and adopted into the lease cgroup (`job_27144058/step_extern`), so it
> inherits the **cpuset** but not the step's Slurm environment. Measured on
> spartan-bm155 inside the 48-CPU lease: `sched_getaffinity`=48,
> `os.cpu_count()`=128, `psutil.cpu_count()`=128, both `SLURM_*` vars unset.
> `sched_getaffinity` is therefore the authoritative fallback, and the reason
> `-n auto` misbehaves at all is that pytest-xdist consults **psutil before**
> `sched_getaffinity` (`xdist/plugin.py` 3.8.0 L26-34) — not, as first
> assumed, that `auto` is inherently allocation-blind.
| **P2** | **CI** | Wave 1 in flight (#400 canonical caller; drift inventory 2026-07-21) | (a) every scitex repo carries the thin org-reusable `ci.yml` caller and nothing else (six generations → one); (b) runner labels unified to ONE vocabulary selected via `vars.CI_RUNS_ON`; (c) zero `ubuntu-latest` / GitHub-hosted jobs in scitex repos (PS-169 at ERROR); (d) auditor rule ERRORs on non-canonical workflow files, so drift cannot silently return. |
| **P3** | **Agent/fleet jobs** | Design open (federation contract 2026-07-20; this ADR fixes the taxonomy) | (a) `scitex_dev.jobs.JobSpec` carries the intent/mechanism split (intents accepted; mechanism chosen at lowering; back-compat mapping for `service`/`timer`/`cron`); (b) zero leaf-local or hand-rolled host crons — every repetitive job discoverable via `scitex-dev ecosystem` from an entry-point provider; (c) sac's daemon/restart passes declared through the federation (sac keeps the logic, scitex-dev installs the schedule); (d) periodic fleet jobs eligible for pool placement (Spartan backfill) where they don't need host-locality. |

A phase is *entered* when its predecessor's exit criteria are met or
explicitly waived by the operator; phases may overlap in build but not in
"declare victory" order. Experiments/research pipelines ride P1's interfaces
(same backends, same receipts) and need no separate phase.

### Non-goals

- **Not a new scheduler kernel.** Slurm, systemd, cron, and the GitHub
  Actions queue remain the engines; the fabric declares, routes, guards, and
  audits. No DAG scheduler, retry engine, distributed executor, or
  storage-staging layer is built here (delegate to Snakemake/Nextflow if
  ever needed — phase-1 §5/§7 stand).
- **No paid cloud.** No AWS/GCP/Azure backends, no cost-bearing capacity.
  The interfaces keep the door open (`cost_usd` stays `None`; a cloud
  backend would be "+1 adapter"), but no cloud code, budget, or data-
  governance machinery ships under this ADR.
- **No fairness/quota arbitration** between permitted jobs (see Decision 2).

## Consequences

**Positive**

- One vocabulary for "what runs where with what": four job families stop
  answering the question four ways. New job types (a benchmark sweep, a docs
  build) get declaration + placement + receipts for free instead of a new
  bespoke runner script.
- The intent/mechanism split makes mechanism migration invisible to leaves:
  moving a periodic job from host cron to a systemd timer to Slurm scrontab
  is a lowering change in scitex-dev, zero leaf PRs — the same property the
  thin CI caller already gives workflows (job bodies change org-side, repos
  don't churn).
- The shared pool ends runner-label balkanization: capacity added to the
  pool (a new Spartan lease, a new runner box) becomes available to CI,
  tests, and fleet jobs simultaneously via one label vocabulary and one
  `ResourceSpec` translation point.
- The receipt + fail-loud-gate doctrine extends the anti-false-claim
  property from tests to every job family: "it ran" is always backed by an
  artifact naming commit/backend/resources, which is what lets agents be
  trusted to self-report.
- Ownership boundaries are enforceable with the existing ADR-0003 lint
  machinery (entry-point federation is kind-c; a leaf importing backend
  internals is the a2 smell).

**Negative / cost**

- Convergence debt is real: two JobSpec shapes exist today and must be
  field-reconciled during P3 without breaking registered providers
  (back-compat mapping for `service`/`timer`/`cron` is mandatory).
- Best-effort allocation means no latency guarantees: a saturated pool
  queues CI and fleet jobs alike. Accepted — the alternative (reserved
  capacity per family) recreates the balkanization this ADR removes.
- scitex-dev becomes a scheduling single-point-of-policy: an aggregator bug
  can mis-install fleet-wide schedules. Mitigated by the fail-safe
  invocation doctrine (one bad declaration never kills the run) and by the
  engines staying authoritative (a wrong lowering is visible in
  systemd/cron state, not hidden in a bespoke daemon).
- P2 completion requires a ~70-repo sweep (the drift inventory's wave plan);
  until (d) lands, drift can re-enter behind the sweep.

**Avoided cost (vs. status quo)**

- Without this ADR, the two JobSpecs keep diverging, CI label vocabularies
  keep multiplying (five and counting), and every new job family invents a
  fifth declaration mechanism — each later unification strictly more
  expensive than this one.

## Notes

- Operator approvals: direction approved 2026-07-22 (intent/mechanism split,
  best-effort pool, tests→CI→agent-jobs phasing); shared-pool + label-
  unification directive TG 1580/1583/1592 (2026-07-21); executor-reuse rule
  TG1524 (via phase-1 doc).
- Source documents synthesized (not duplicated) here:
  - `docs/design/execution-fabric-phase1.md` (#388) — the four locked
    interfaces, the two phase-1 backends, the scitex-dev/scitex-hpc split,
    the deferred list. Remains the authoritative interface spec; this ADR
    is the ecosystem-wide architecture above it.
  - `src/scitex_dev/_core/test_execution.py`,
    `src/scitex_dev/_core/_test_execution_plugin.py`,
    `src/scitex_dev/_core/_knobs.py` (#385) — the shipped P1 policy layer.
  - `src/scitex_dev/_ecosystem/ci_template/templates/ci.yml.tmpl` (#400) —
    the canonical thin caller; CI-drift inventory 2026-07-21 (GITIGNORED)
    — the P2 ground truth and wave plan.
  - `scitex_dev/jobs/__init__.py` + the JobSpec federation contract
    (2026-07-20) — the P3 substrate; its open `kind`-taxonomy thread is
    closed by Decision 1.
- Open threads this ADR leaves open (tracked on the fleet board, not here):
  the interface-home question (shared module vs `scitex-execspec`), the
  routing selector, sharding, cost/budget fields, data governance — all
  deferred exactly as phase-1 §5 lists them.
- Related ADRs: ADR-0003 (ports-and-producers — supplies the seam rule
  Decision 3 applies); ADR-0001/0002 (package-absorption precedent for the
  "reverse via a new ADR" convention this file follows).
