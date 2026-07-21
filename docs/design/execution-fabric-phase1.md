# SciTeX Execution Fabric — Phase-1 Design

Status: Phase-1 proposal (design-first, not yet implemented)
Owners: scitex-dev (policy/auditor) + scitex-hpc (backend adapters)
Date: 2026-07-21
Source vision memo: `central-compute-dispatcher-design-20260720.md` (operator TG1503-1525)

## 1. Purpose & strategic framing

The execution fabric safely routes **reproducible compute jobs** (starting with
test suites) to available resources — local, HPC, and later cloud — behind a
single command: `scitex test` (namespaced `scitex-dev dev test`). It is a CORE
SciTeX compute subsystem, priority VERY HIGH because it is multiplicative on dev
speed (all agents × all packages × all iterations).

### Strategic decision (operator TG1524) — DO NOT reinvent the executor

"local/HPC/cloud via a common API" is solved prior art: Snakemake (executor
plugins), Nextflow/Seqera, Parsl (Slurm provider), Dask/dask-jobqueue, AWS/GCP/
Azure Batch, AWS ParallelCluster. The `submit / status / logs / cancel / collect`
interface is NOT new. **SciTeX must NOT build** Slurm/Batch wrappers from scratch
as a differentiator, a DAG scheduler, retry engine, cloud provisioner, distributed
executor, or storage-staging layer — those are REUSED from existing executors.

What SciTeX uniquely adds is a **POLICY + DX + agent-integration** layer:

1. Repo-level ENFORCEMENT policy — the same rule for humans and agents.
2. Make WRONG usage IMPOSSIBLE — no laptop-heavy-test, no login-node pytest, no
   1-core waits, no GPU-test-on-CPU, no confidential-data-to-cloud. Existing
   executors "work if used right"; SciTeX is the "can't-misuse" layer.
3. One consistent LLM-agent entry point — the agent only knows `scitex test`
   (no partition / sbatch / SSH / module / SIF / worker-count knowledge).
4. Auto-distribution + AUDIT across all packages.

Layering:

```
Agent/Human → SciTeX policy/guard → SciTeX ExecutionBackend interface
            → EXISTING executor (subprocess / srun / Snakemake / Parsl)
            → Slurm / cloud
```

Positioning: Snakemake/Parsl = HOW to execute; **scitex-dev = WHAT to allow**
devs/agents; **scitex-hpc = HOW to connect** to resources; Slurm/Batch = actually
schedule.

### Phase-1 thesis

Build the thin enforcement layer + minimal backends, and **LOCK 4 interfaces NOW**
so everything deferred becomes "+1 adapter later, not a rewrite."

---

## 2. The 4 foundations to lock as interfaces NOW

Get these right and cloud is just one more `ExecutionBackend` implementation.
Sketches below are **illustrative**, not a full implementation.

### 2a. Container contract — the execution unit

Cloud/remote reproducibility = `git commit + container image + recipe`, NEVER a
dirty-tree copy. A job is defined by *what commit* runs *in what image* under
*what recipe* — nothing implicit about the caller's working directory.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ContainerContract:
    """The reproducible unit of execution. No dirty-tree state."""
    repo: str                       # e.g. "scitex-io"
    commit: str                     # exact git SHA (never "HEAD"/branch)
    image: str                      # OCI ref or SIF path, e.g. "ghcr.io/.../scitex:2.1"
    dirty: bool = False             # True only if uncommitted tree; policy may forbid
    workdir: str = "/work"          # in-container mount point of the checkout
    env: dict[str, str] = field(default_factory=dict)
```

Rule: `remote_required` packages MUST run with `dirty=False`. The auditor and the
receipt both record `commit`, so "tested remotely" can never mask a different SHA.

### 2b. Resource spec — backend-neutral

The user/recipe declares only `cpu / memory / gpu / walltime`. They NEVER write
`partition: bm`, `instance_type: c7i.4xlarge`, or `machine_type: ...` — each
backend TRANSLATES the neutral spec into its own vocabulary.

```python
@dataclass(frozen=True)
class ResourceSpec:
    """Backend-neutral resource request. Backends translate it."""
    cpu: int = 1                    # logical cores; drives allocated -n worker count
    memory_gb: float | None = None
    gpu: int = 0
    walltime_min: int | None = None # soft cap; backend maps to --time / timeout
```

Translation lives in the backend PROFILE (scitex-hpc), never in the recipe:
`slurm` maps `cpu -> --cpus-per-task` + partition selection; a future `aws-batch`
maps `cpu/memory_gb -> instance_type`.

### 2c. ExecutionBackend interface — submit / status / logs / cancel / collect

The one contract scitex-dev calls. It knows nothing of Slurm/AWS; it only calls
`backend.submit(job)`. Lives in **scitex-hpc**.

```python
from typing import Protocol
from enum import Enum

class JobState(str, Enum):
    PENDING = "pending"; RUNNING = "running"
    SUCCEEDED = "succeeded"; FAILED = "failed"; CANCELLED = "cancelled"

@dataclass(frozen=True)
class JobSpec:
    container: ContainerContract
    resources: ResourceSpec
    command: list[str]              # e.g. ["pytest", "-n", "<allocated>", "tests/"]
    shard: tuple[int, int] | None = None   # (index, total); deferred use

@dataclass(frozen=True)
class JobHandle:
    backend: str                    # "local" | "slurm" | ...
    job_id: str                     # subprocess pid / SLURM job id
    submitted_at: str

class ExecutionBackend(Protocol):
    name: str
    def submit(self, job: JobSpec) -> JobHandle: ...
    def status(self, handle: JobHandle) -> JobState: ...
    def logs(self, handle: JobHandle) -> str: ...
    def cancel(self, handle: JobHandle) -> None: ...
    def collect(self, handle: JobHandle) -> "JobReceipt": ...
```

`collect()` blocks (or polls) to terminal state and returns the receipt — the
only sanctioned way to obtain a result.

### 2d. Execution RECEIPT schema — anti-false-claim

The receipt is how an agent PROVES it tested the right thing at the right commit
on the right backend with the right CPU count. It prevents "tested remotely" while
actually testing another commit, or merely submitting.

```python
@dataclass(frozen=True)
class ReceiptSource:
    repo: str; commit: str; dirty: bool

@dataclass(frozen=True)
class ReceiptRuntime:
    image: str; backend: str; instance: str | None; cpu: int   # cpu = ALLOCATED

@dataclass(frozen=True)
class ReceiptResult:
    passed: int; failed: int; duration_s: float
    cost_usd: float | None = None   # None until a cost-bearing backend exists

@dataclass(frozen=True)
class JobReceipt:
    source: ReceiptSource
    runtime: ReceiptRuntime
    result: ReceiptResult
    junit_xml_path: str | None = None
```

Mandatory fields in Phase-1: `commit`, `backend`, `cpu` (allocated), and
`passed/failed`. The receipt is emitted by every `collect()` and is the artifact
CI + agents cite as proof.

---

## 3. The 2 Phase-1 backends

Exactly two `ExecutionBackend` implementations ship in Phase-1 — nothing else.

### 3a. `local` backend

- Executor: plain `subprocess`.
- `submit`: fork `pytest -n <allocated> ...` against the checkout at `commit`.
- `status`: poll the child process.
- `logs`: tail captured stdout/stderr.
- `cancel`: signal the process group.
- `collect`: wait, parse JUnit XML, emit `JobReceipt` with `backend="local"`.
- Allocated CPUs = the caller's permitted core budget (see §3c), NOT literal
  all-cores. On an unconstrained laptop this may default to `os.cpu_count()`, but
  `remote_required` packages are BLOCKED from the `local` backend by policy.

### 3b. `slurm` backend

- Executor: native Slurm via `srun --overlap` into an existing lease (no queue
  wait), or `sbatch` for a fresh allocation.
- `submit`: render the recipe `submit_template`, e.g.
  `srun --overlap -p <cpu-partition> pytest -n <allocated> {pytest_args}`.
- `status` / `logs` / `cancel`: `sacct` / job stdout file / `scancel`.
- `collect`: parse JUnit XML from the job output, emit `JobReceipt` with
  `backend="slurm"`, `instance=<node/partition>`, `cpu=$SLURM_CPUS_PER_TASK`.
- Hard constraint: submit to a COMPUTE node via the scheduler, NEVER the login
  node (admins flag login-node compute).
- Spartan is treated as ONE resource; the fabric DELEGATES internal placement to
  Spartan's native Slurm via the `submit_template` — it inherits/extends the
  native scheduler, it does not nest a second controller.

### 3c. `-n auto` → allocated-cpus (fix to fold in)

`pytest -n auto` sees the WHOLE node's cores. On Slurm that over-subscribes an
allocation and gets flagged. Phase-1 replaces the literal `-n auto` merged in
#384/#385 with a per-backend **allocated-cpus** abstraction:

- `slurm`: `-n $SLURM_CPUS_PER_TASK` (the permitted count).
- `local`: `-n <ResourceSpec.cpu>` (bounded, not all-cores).

Login/allocation detection uses `running_inside_slurm()` = presence of
`SLURM_JOB_ID` / `SLURM_STEP_ID`, NOT hostname (naming varies per environment).

---

## 4. Ownership split — scitex-dev (policy/auditor) vs scitex-hpc (adapters)

POLICY declares WHAT (local/remote/parallel/backend); the scitex-hpc PROFILE holds
HOW (Spartan/cloud translation). Backends stay independent and portable to other
universities — no hard dependency on Slurm cloud-bursting.

### scitex-dev owns

- The `scitex-dev dev test` policy-layer CLI (extends the #385 recipe).
- The recipe schema (`local_allowed` / `remote_required`, resource-spec fields).
- The 4 interface DEFINITIONS as the shared contract (dataclasses/Protocols above
  live in a shared `scitex_dev` interface module that scitex-hpc imports, OR a
  jointly-owned `scitex-execspec` — see §6).
- The AUDITOR rules (ERROR severity):
  - `pytest-not-serial` (missing xdist where required),
  - `remote-required-run-local`,
  - `public-extra-beyond-[all]`,
  - `CI-template-off-convention`,
  - internal `_`-extras exposed in README/docs.
- The 3-layer guard: L1 agent hook (auto-convert `pytest tests/` → `scitex test
  tests/` for agents; error+correct-cmd for humans), L2 CLI, L3 `conftest.py`
  last-line (`pytest_sessionstart` raises if `remote_required` and not in an
  approved env).

Extras convention (confirmed): public = bare | `[all]` only; internal =
`_test` / `_docs` / `_hpc` (underscore = intent; auditor also checks README/docs
don't expose internal extras).

### scitex-hpc owns

- The `ExecutionBackend` interface implementations: `local` and `slurm` in Phase-1
  (later `ssh`, `aws-batch`, `google-batch`, `azure-batch`).
- All Spartan/cloud specifics: partition selection, `sbatch` rendering,
  `--cpus-per-task ↔ -n` match, `--overlap` into leases, account.
- The resource REGISTRY (resource id → submit_template + capacity/labels +
  liveness probe) and live-utilisation knowledge.
- The backend-neutral `ResourceSpec` → backend-vocabulary TRANSLATION.

---

## 5. Explicitly DEFERRED behind the interfaces

Deferrable because each is "+1 adapter" against a locked interface, not a rewrite:

- **Cloud backends** — AWS Batch / Google Batch / Azure Batch as additional
  `ExecutionBackend` implementations (scitex-hpc). No cloud code in Phase-1.
- **Best-effort load-balancing / routing** across free registered nodes, and the
  `scitex test --target fastest|cheapest|local-only|secure` selector with
  `routing{objective, constraints}` — deferred; Phase-1 selects backend explicitly.
- **Job sharding** — split the test list across multiple cloud jobs and aggregate
  JUnit XML (the `JobSpec.shard` field is reserved but unused in Phase-1). Note
  multi-node ≠ xdist; shard, don't over-subscribe.
- **Cost control** — `budget{max_cost_per_job, prefer_spot, fallback_to_on_demand}`
  and the receipt `cost_usd` field (present but `None` until a cost-bearing
  backend exists).
- **Data governance** — can-data-go-to-cloud / ethics approval / storage region /
  PII gating in recipe policy BEFORE resource pick. Only matters once a cloud
  backend exists; the recipe schema reserves space for it.
- **DAG / complex workflows** — DELEGATE to Snakemake/Nextflow if ever needed;
  never hand-rolled.

---

## 6. Coordination ask for scitex-hpc

Phase-1 is scitex-hpc-led on backends and scitex-dev-led on policy/audit/CLI. This
is a JOINT design — do NOT solo-build either side. Concretely, scitex-hpc must
agree to and implement:

1. **Own the `ExecutionBackend` Protocol implementations.** Consume the four
   locked interfaces (`ContainerContract`, `ResourceSpec`, `JobSpec`/`JobHandle`,
   `JobReceipt`) exactly as defined in §2 — same field names, same
   `submit/status/logs/cancel/collect` signatures. scitex-dev calls only
   `backend.submit(job)` and `backend.collect(handle)`.
2. **Ship exactly two backends in Phase-1:** `local` (subprocess) and `slurm`
   (`srun --overlap` into a lease; `sbatch` fallback). No cloud, no ssh yet.
3. **Emit a compliant `JobReceipt` from every `collect()`** — with real
   `commit`, `backend`, ALLOCATED `cpu`, and `passed/failed`. This is the anti-
   false-claim contract; a backend that cannot fill these is non-conformant.
4. **Honour allocated-cpus, never all-cores:** map `-n` to
   `SLURM_CPUS_PER_TASK` (slurm) / `ResourceSpec.cpu` (local); never emit literal
   `-n auto` on a shared allocation. Provide `running_inside_slurm()` semantics
   (env-var based, not hostname).
5. **Own `ResourceSpec` → backend translation** (partition/account/instance) and
   the resource registry + liveness probe. Guarantee Slurm submits to COMPUTE
   nodes only, never the login node.
6. **Agree the interface-home question:** whether the four dataclasses/Protocols
   live in a scitex-dev interface module that scitex-hpc imports, or a small
   jointly-owned `scitex-execspec` package. Recommendation: a thin shared spec
   module so neither side co-locks the other's release (standalone-independence).

Interface contract scitex-hpc CONSUMES: §2a–§2d verbatim. Interface contract
scitex-hpc PROVIDES: conformant `local` + `slurm` `ExecutionBackend` objects
discoverable by name.

### Immediate independent follow-up (lands first)

The **extras-enforcement auditor** (public = bare|`[all]`; internal `_`-extras not
exposed in README/docs) is small, already agreed, and independent of scitex-hpc —
queue it to land ahead of the joint backend work.

---

## 7. Non-goals for Phase-1

No cloud provisioning, no DAG scheduler, no retry/backoff engine, no distributed
executor, no storage staging, no routing/cost optimiser. Those are REUSED or
deferred behind the four interfaces above.
