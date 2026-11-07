---
description: |
  [TOPIC] Test Runner
  [DETAILS] Run pytest locally or on HPC via Slurm. TestConfig configures test execution. run_local launches pytest as a subprocess. sync_to_hpc rsyncs the project. run_hpc_srun/sbatch submit jobs. poll_hpc_job and fetch_hpc_result retrieve status and output.
tags: [scitex-dev-test-runner]
---

# Test Runner

## TestConfig

Dataclass for test execution configuration.

```python
from scitex_dev import TestConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
TestConfig(module: 'str' = '', parallel: 'str' = 'auto', fast: 'bool' = False, coverage: 'bool' = False, exitfirst: 'bool' = False, pattern: 'str' = '', changed: 'bool' = False, last_failed: 'bool' = False, hpc_host: 'str | None' = None, hpc_cpus: 'int | None' = None, hpc_partition: 'str | None' = None, hpc_time: 'str | None' = None, hpc_mem: 'str | None' = None, remote_base: 'str | None' = None) -> None
```

HPC defaults resolve via `PriorityConfig`:
1. Direct parameter on `TestConfig`
2. `SCITEX_DEV_TEST_*` environment variables
3. Built-in defaults in the table below

## run_local

Run pytest locally via subprocess.

```python
from scitex_dev import run_local, TestConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
run_local(config: 'TestConfig') -> 'int'
```

```python
# Run all tests
exit_code = run_local(TestConfig())

# Run specific module, fast, stop on failure
exit_code = run_local(TestConfig(
    module="io",
    fast=True,
    exitfirst=True,
))

# With coverage
exit_code = run_local(TestConfig(coverage=True))
```

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

Output written to `{remote_base}/{project}/.pytest-hpc-output/{job_id}.out`

## poll_hpc_job

Check sacct status of an HPC job.

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

- `watch_hpc_job(job_id=None, hpc_host=None, interval=15) -> dict` — polls
  until terminal state, then returns the same dict as `poll_hpc_job`.
- `fetch_hpc_result(job_id=None, hpc_host=None) -> str | None` — scp's the
  full stdout from `.pytest-hpc-output/{job_id}.out`. None if missing.

## Typical HPC Workflow

```python
from scitex_dev import TestConfig, sync_to_hpc, run_hpc_sbatch, watch_hpc_job

config = TestConfig(module="io", fast=True, hpc_cpus=8)

# 1. Sync project to HPC
sync_to_hpc(config)

# 2. Submit job
job_id = run_hpc_sbatch(config)
print(f"Submitted: {job_id}")

# 3. Wait and get output
result = watch_hpc_job(job_id=job_id, interval=30)
print(result["state"], result["output"])
```

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
