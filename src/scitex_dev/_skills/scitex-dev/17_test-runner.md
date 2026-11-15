---
description: |
  [TOPIC] Local Test Runner
  [DETAILS] Configure TestConfig and run pytest locally with run_local. Legacy Slurm helpers are documented separately in 43_hpc-test-runner.md.
tags: [scitex-dev-test-runner]
---


# Local Test Runner

## TestConfig

Dataclass for test execution configuration.

```python
from scitex_dev import TestConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
TestConfig(module: 'str' = '', parallel: 'str' = 'auto', fast: 'bool' = False, coverage: 'bool' = False, exitfirst: 'bool' = False, pattern: 'str' = '', changed: 'bool' = False, last_failed: 'bool' = False, hpc_host: 'str | None' = None, hpc_cpus: 'int | None' = None, hpc_partition: 'str | None' = None, hpc_time: 'str | None' = None, hpc_mem: 'str | None' = None, remote_base: 'str | None' = None) -> None
```

HPC fields and their configuration precedence are documented in
[Legacy HPC Test Runner](43_hpc-test-runner.md).

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

### Local module selection

`module=""` intentionally selects the project's whole `tests/` directory.
For a nonempty module, the local runner first checks `tests/scitex/<module>`;
otherwise it passes `tests/<module>` to pytest. For leaf layouts, include the
package directory when needed, for example `module="scitex_dev/testing"` if
that directory exists. This is path selection, not package-name discovery.

A missing explicit module stays a missing pytest path and returns pytest's
usage-error exit status (4); it no longer silently selects the whole suite.
Valid selection precedence, pytest options and test-failure exit codes are
unchanged. This local fix does not change the separate legacy HPC helpers or
add a progress journal, timeout policy or new CLI route.

Owning source: `test_runner.py::_build_pytest_args` / `run_local`.
Real local subprocess selection and exit-status controls:
`tests/integration/test_test_runner_module_scope.py`.

## Legacy HPC helpers

For `sync_to_hpc`, `run_hpc_srun`, `run_hpc_sbatch`, `poll_hpc_job`,
`watch_hpc_job` and `fetch_hpc_result`, use
[Legacy HPC Test Runner](43_hpc-test-runner.md). It covers submission failures,
saved job IDs, configuration and the limits of remote execution evidence.

## Interface availability

The CLI does not register `scitex-dev test local`; use the public Python
function above. MCP exposes separate `dev_test_*` tools; inspect the installed
catalog before use.

These section links preserve entry points to the moved HPC guidance.

## sync_to_hpc

See [Legacy HPC Test Runner](43_hpc-test-runner.md#sync_to_hpc).

## run_hpc_srun

See [Legacy HPC Test Runner](43_hpc-test-runner.md#run_hpc_srun).

## run_hpc_sbatch

See [Legacy HPC Test Runner](43_hpc-test-runner.md#run_hpc_sbatch).

## poll_hpc_job

See [Legacy HPC Test Runner](43_hpc-test-runner.md#poll_hpc_job).

## watch_hpc_job, fetch_hpc_result

See [Legacy HPC Test Runner](43_hpc-test-runner.md#watch_hpc_job-fetch_hpc_result).

## Typical HPC Workflow

See [Legacy HPC Test Runner](43_hpc-test-runner.md#typical-hpc-workflow).

## Environment Variables

See [Legacy HPC Test Runner](43_hpc-test-runner.md#environment-variables).
