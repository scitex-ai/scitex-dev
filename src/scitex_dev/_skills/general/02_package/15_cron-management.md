---
description: |
  [TOPIC] Scheduled-job ownership and management
  [DETAILS] Dev supplies the shared JobSpec/discovery contract and scheduler management; leaves own their job logic and declarations. Distinguish the legacy Dev built-in cron registry from federated providers, explicit installation and observed execution.
tags: [scitex-general-package-cron-management]
---

# Scheduled-job ownership and management

Dev owns shared discovery, schedule-management and logging primitives. A leaf
owns its expert job body and declares it through `scitex_dev.jobs`. Cross-package
coordination can be Dev-owned; that does not require moving every leaf's
scheduled implementation into Dev.

## Leaf provider declaration

An illustrative provider imports the public JobSpec contract and returns its
own declarations:

```python
from scitex_dev.jobs import JobSpec

def provide_jobs() -> list[JobSpec]:
    return [JobSpec(
        name="scitex-example-report",
        kind="cron",
        schedule="0 13 * * *",
        command="python -m example_package.jobs.report",
        description="Produce a local report.",
    )]
```

Implement the command in the owning leaf and replace the example identity
before registering it. Constructing this declaration does not run the command.
The matching package metadata is:

```toml
[project.entry-points."scitex_dev.jobs"]
scitex-example = "example_package._jobs:provide_jobs"
```

`JobSpec` supports `cron`, `timer` and `service` kinds with different applicable
fields. Inspect the installed contract for cadence, service lifetime, environment
and working-directory options. Discovery is not evidence that a scheduler is
installed, enabled or healthy on a host.

Source: `scitex_dev/jobs/__init__.py` and its exported JobSpec implementation.
Use the installed ecosystem manager's help to select the relevant kind:

```bash
scitex dev ecosystem --help
```

## Dev's built-in cron registry

The existing `dev cron` group separately manages Dev's historical built-in
registry in `_cli/cron/_jobs.py`. It has five operations:

```bash
scitex dev cron list --help
scitex dev cron status --help
scitex dev cron install --help
scitex dev cron remove --help
scitex dev cron exec --help
```

These umbrella routes require the installed Dev adapter. Standalone bootstrap:
`scitex-dev dev cron ...`; the legacy top-level `scitex-dev cron` alias may emit
a deprecation notice. Inspect actual help before applying changes.

Install/remove support previews and explicit application flags. Managed crontab
lines carry the `# scitex-dev cron: <name>` marker, allowing the manager to select
its own entries while preserving unrelated lines. A job body may itself send
messages, rotate credentials, install packages or modify repositories; inspect
that body before execution. A command named `exec` is not a read-only check.

## Logging and verification

The built-in execution path uses `_cli/cron/_job_commands.py` and
`jobs/_logsink.py` to resolve and rotate its managed runtime logs. Do not duplicate
shell redirection in a registry command when that execution layer already owns
logging. Host/runtime paths must follow the actual shared path resolver rather
than a copied home directory.

Verify declarations, installed units/crontab entries, recent execution records,
exit status and expected outcomes separately. Do not infer success from the
registry entry or a scheduler's next-run timestamp. The daily documentation
review follows [22_documentation-drift.md](../05_development/22_documentation-drift.md).

Related: [worktree cleanup](15b_cron-worktree-gc.md) and the actual leaf's own job
skill. This guide does not request scheduler installation or a fleet-wide run.
