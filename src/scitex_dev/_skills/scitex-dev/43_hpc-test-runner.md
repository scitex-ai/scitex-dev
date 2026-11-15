---
description: |
  [TOPIC] Legacy HPC Test Runner
  [DETAILS] Use the Slurm-specific sync, submission, polling and result helpers. Check failure returns and saved job IDs; source signatures do not qualify a cluster.
tags: [scitex-dev-hpc-test-runner]
---

# Legacy HPC Test Runner

HPC defaults resolve via `PriorityConfig`:
1. Direct parameter on `TestConfig` (where the function accepts one)
2. `SCITEX_DEV_TEST_*` environment variables
3. Built-in defaults in the table below

## sync_to_hpc

Rsync project to HPC host (excludes .git, __pycache__, dist, build, etc.).

```python
from scitex_dev import sync_to_hpc, TestConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
sync_to_hpc(config: 'TestConfig') -> 'bool'
```

Auto-detects Git root and project name. Target: `{hpc_host}:{remote_base}/{project}/`.
The implementation uses `rsync --delete`: unmatched destination files outside
its exclusion list can be removed. Inspect the destination before using it.

## run_hpc_srun

Blocking srun on HPC — waits for completion.

```python
from scitex_dev import run_hpc_srun, TestConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
run_hpc_srun(config: 'TestConfig') -> 'int'
```

Current implementation (not a dependency-resolution or cluster-readiness check):
1. SSH to `hpc_host`
2. `srun --partition=... --cpus-per-task=... --time=... --mem=...`
3. Install the editable project with `--no-deps`; dependencies must already exist.
4. `python -m pytest {test_path} -n {cpus} --dist loadfile -x --tb=short`

## run_hpc_sbatch

Async sbatch — submits job and returns job ID immediately.

```python
from scitex_dev import run_hpc_sbatch, TestConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
run_hpc_sbatch(config: 'TestConfig') -> 'str | None'
```

Returns a job ID string, or `None` when submission fails or no numeric ID is
found. A successful submission saves the ID in local `.last-hpc-job`.
Stdout and stderr are separate files under
`{remote_base}/{project}/.pytest-hpc-output/{job_id}.out` and `{job_id}.err`.

## poll_hpc_job

Check sacct status of an HPC job. With no `job_id`, this reads local
`.last-hpc-job`; with no saved ID it returns
`{"state": "error", "output": None, "job_id": ""}` before contacting HPC.
An unrecognized status is `UNKNOWN`, not successful completion.

```python
from scitex_dev import poll_hpc_job
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
poll_hpc_job(job_id: 'str | None' = None, hpc_host: 'str | None' = None) -> 'dict[str, Any]'
```

```python
status = poll_hpc_job()
if status["state"] == "COMPLETED":
    print(status["output"])
```

## watch_hpc_job, fetch_hpc_result

Convenience wrappers around `poll_hpc_job`:

- `watch_hpc_job(job_id=None, hpc_host=None, interval=15) -> dict` — returns
  on `COMPLETED`, `FAILED`, `TIMEOUT`, `CANCELLED`, `error` or `UNKNOWN`.
  It keeps polling running/pending jobs with no overall deadline; `interval`
  controls the delay between polls, not a timeout.
- `fetch_hpc_result(job_id=None, hpc_host=None) -> str | None` — scp's the
  full stdout from `.pytest-hpc-output/{job_id}.out`. None if missing.

## Typical HPC Workflow

```python
from scitex_dev import TestConfig, sync_to_hpc, run_hpc_sbatch, watch_hpc_job

config = TestConfig(module="", fast=True, hpc_cpus=8)  # intentional whole suite

# 1. Inspect the destination first: sync uses rsync --delete.
if not sync_to_hpc(config):
    raise RuntimeError("Project sync failed; no job submitted")

# 2. Submit job
job_id = run_hpc_sbatch(config)
if job_id is None:
    raise RuntimeError("Job submission failed; no job to watch")
print(f"Submitted: {job_id}")

# 3. Wait and get output
result = watch_hpc_job(job_id=job_id, hpc_host=config.hpc_host, interval=30)
print(result["state"], result["output"])
```

The failure checks are significant: passing `None` to the watcher can select
an older `.last-hpc-job` instead of the failed submission. Keep
`SCITEX_DEV_TEST_REMOTE_BASE` consistent across submission, polling and fetch:
the latter helpers have no `TestConfig`/`remote_base` parameter and resolve
the remote base from that environment variable or the default.

For local pytest selection and the full `TestConfig` signature, see
[Local Test Runner](17_test-runner.md).

These examples describe legacy source behavior; remote execution requires
separate cluster qualification. Owning symbols: `run_hpc_sbatch`,
`poll_hpc_job`, `watch_hpc_job` and `fetch_hpc_result` in `test_runner.py`.

## Interface availability

The current CLI does not register `scitex-dev test local`, `test hpc`,
`test hpc-poll` or `test hpc-result`. Use the public Python functions above;
do not infer a CLI command from an exported Python name. The MCP server has
separate `dev_test_*` tools. Inspect the installed tool catalog before use.

These are legacy Slurm-specific helpers, not the scheduler abstraction of
`scitex-hpc`. The signatures and local source do not establish remote access,
cluster policy, installed dependencies or successful job execution.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SCITEX_DEV_TEST_HOST` | `spartan` | HPC SSH hostname |
| `SCITEX_DEV_TEST_CPUS` | `16` | CPUs per Slurm task |
| `SCITEX_DEV_TEST_PARTITION` | `sapphire` | Slurm partition |
| `SCITEX_DEV_TEST_TIME` | `00:20:00` | Slurm time limit |
| `SCITEX_DEV_TEST_MEM` | `128G` | Slurm memory |
| `SCITEX_DEV_TEST_REMOTE_BASE` | `~/proj` | Remote project directory |
