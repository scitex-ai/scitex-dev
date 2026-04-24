---
description: Developer utilities for maintaining the whole SciTeX ecosystem across ~15 packages — version audit and mismatch fixing, editable-install sync, per-host git pull/commit/diff via SSH, bulk rename across files + contents + directories + symlinks (with git-safety guards), aggregated docs search across all packages, a Result/ErrorCode envelope shared by CLI + MCP, DevConfig/HostConfig, a local + HPC-Slurm test runner (`sbatch` / `srun`, job polling, result fetch), skill aggregation (`list_skills`, `get_skill`), and ecosystem-wide release pipelines (audit → bump → release → sync). Drop-in replacement for hand-rolled `for pkg in scitex-*; do ...` loops, manual `git status` walks across sibling repos, and shell scripts that pip-install everything in editable mode. Use whenever the user asks to "list scitex versions", "check for version mismatches", "fix version drift", "rename old_name → new_name across all files", "sync my changes to the HPC / laptop / servers", "run tests on the HPC via Slurm", "poll my sbatch job", "fetch HPC test output", "search the docs for save_fig", "commit remote changes on gpu01", "pull all repos", "audit the ecosystem before a release", "show ecosystem skills", or does any cross-package maintenance.
allowed-tools: mcp__scitex__dev_*
primary_interface: cli
interfaces:
  python: 2
  cli: 3
  mcp: 2
  skills: 2
  hook: 0
  http: 0
---

# scitex-dev Skills Index

> **Interfaces:** Python ⭐⭐ · CLI ⭐⭐⭐ (primary) · MCP ⭐⭐ · Skills ⭐⭐ · Hook — · HTTP —

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
- [15_full-update.md](15_full-update.md) — Full ecosystem release pipeline — pre-flight + release (phases 1–2)
- [19_full-update-deploy.md](19_full-update-deploy.md) — Full ecosystem release pipeline — local sync, NAS deploy, verification (phases 3–5)

### Agentic Testing (16–18)
- [16_agentic-test-overview.md](16_agentic-test-overview.md) — Four-layer testing model + shared newbie-docker substrate (entry point)
- [17_agentic-test-skills.md](17_agentic-test-skills.md) — Skill trigger-rate testing (Layer 2 for skills)
- [18_agentic-test-mcp.md](18_agentic-test-mcp.md) — MCP tool-call evaluation (Layer 2+3 for MCP) — draft spec

### Quality Gates (20+)
- [20_dynamic-audit.md](20_dynamic-audit.md) — Dynamic-audit design skeleton for release-gate (paired with scitex-python 99_checklist static commit-gate)

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
