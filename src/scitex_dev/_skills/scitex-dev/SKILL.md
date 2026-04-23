---
description: Shared developer utilities for the SciTeX ecosystem — ecosystem management, version checking, bulk rename, docs aggregation, Result types, and HPC test runner.
allowed-tools: mcp__scitex__dev_*
---

# scitex-dev Skills Index

> These skills are distributed with the **scitex-dev** package.
> Local edits may be overwritten on update. See [MANIFEST.md](MANIFEST.md) for version and update instructions.

## Sub-skills

### Core (01–09)
- [01_result-types.md](01_result-types.md) — Result envelope, ErrorCode, @supports_return_as, SideEffect
- [02_cli-mcp-utils.md](02_cli-mcp-utils.md) — Adapters: CLI exit codes, MCP JSON, option factories
- [03_config.md](03_config.md) — DevConfig, HostConfig, load_config, create_default_config

### Workflows (10–19)
- [10_versions.md](10_versions.md) — list_versions, check_versions, get_mismatches, fix_mismatches
- [11_ecosystem.md](11_ecosystem.md) — Package registry, sync_local, sync_all, sync_host, pull_local
- [12_rename.md](12_rename.md) — bulk_rename, preview_rename, execute_rename
- [13_docs-search.md](13_docs-search.md) — get_docs, build_docs, search_docs, search
- [14_test-runner.md](14_test-runner.md) — run_local, run_hpc_sbatch, poll_hpc_job, fetch_hpc_result
- [15_full-update.md](15_full-update.md) — Full ecosystem release pipeline — audit, bump, release, sync

### Agentic Testing (16–19)
- [16_agentic-test-overview.md](16_agentic-test-overview.md) — Four-layer testing model + shared newbie-docker substrate (entry point)
- [17_agentic-test-skills.md](17_agentic-test-skills.md) — Skill trigger-rate testing (Layer 2 for skills)
- [18_agentic-test-mcp.md](18_agentic-test-mcp.md) — MCP tool-call evaluation (Layer 2+3 for MCP) — draft spec

### Metadata
- [MANIFEST.md](MANIFEST.md) — Package version and skill-export instructions

## Quick Reference

```bash
scitex-dev ecosystem list
scitex-dev ecosystem fix-mismatches --dry-run
scitex-dev rename old_name new_name --root . --dry-run
scitex-dev search "save figure"
scitex-dev mcp start
```

```python
import scitex_dev as dev
dev.check_versions()
dev.fix_mismatches(confirm=False)
dev.preview_rename(pattern="old", replacement="new", directory=".")
```
