---
name: scitex-dev
description: Development tools for the SciTeX ecosystem - package discovery, docs/skills aggregation, testing, linting, and ecosystem management. Use when managing SciTeX packages or coordinating ecosystem-wide operations.
allowed-tools: mcp__scitex__dev_*
---

# SciTeX Ecosystem Management with scitex-dev

## Quick Start

```bash
scitex-dev ecosystem list
scitex-dev ecosystem sync
scitex-dev docs list
scitex-dev skills list
scitex-dev skills export --level project
```

## Common Workflows

### "See all SciTeX packages"

```bash
scitex-dev ecosystem list
scitex-dev ecosystem diff
```

### "Sync ecosystem"

```bash
scitex-dev ecosystem sync
scitex-dev ecosystem sync-local
scitex-dev ecosystem pull
scitex-dev ecosystem commit
```

### "Browse documentation"

```bash
scitex-dev docs list
scitex-dev docs get scitex-io api
scitex-dev docs get figrecipe cheatsheet
```

### "Browse skills"

```bash
scitex-dev skills list
scitex-dev skills get scitex-stats SKILL
scitex-dev skills export --level project --dry-run
```

### "Run tests"

```bash
scitex-dev test local scitex-stats
scitex-dev test hpc scitex-stats
scitex-dev test hpc-poll <job-id>
scitex-dev test hpc-result <job-id>
```

## CLI Commands

```bash
# Ecosystem
scitex-dev ecosystem list|sync|sync-local|pull|commit|diff|fix-mismatches

# Documentation aggregation
scitex-dev docs list|get|search|build

# Skills aggregation
scitex-dev skills list|get|export

# Testing
scitex-dev test local|hpc|hpc-poll|hpc-result

# Configuration
scitex-dev config show
scitex-dev bulk-rename
```

## MCP Tools (for AI agents)

| Tool | Purpose |
|------|---------|
| `dev_ecosystem_list` | List all ecosystem packages |
| `dev_ecosystem_sync` | Sync all packages |
| `dev_ecosystem_sync_local` | Reinstall local packages |
| `dev_ecosystem_pull` | Git pull all packages |
| `dev_ecosystem_commit` | Commit across all packages |
| `dev_ecosystem_diff` | Show uncommitted changes |
| `dev_ecosystem_fix_mismatches` | Fix version mismatches |
| `dev_config_show` | Show ecosystem configuration |
| `dev_bulk_rename` | Bulk rename across ecosystem |
| `dev_test_local` | Run local tests |
| `dev_test_hpc` | Submit HPC test job |
| `dev_test_hpc_poll` | Poll HPC job status |
| `dev_test_hpc_result` | Get HPC test results |
