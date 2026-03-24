---
name: scitex-dev
description: Development tools for the SciTeX ecosystem - package discovery, docs/skills aggregation, testing, linting, and ecosystem management. Use when managing SciTeX packages or coordinating ecosystem-wide operations.
allowed-tools: mcp__scitex__dev_*
---

# SciTeX Ecosystem Management with scitex-dev

## Quick Start

```bash
scitex-dev ecosystem list           # See all SciTeX packages
scitex-dev ecosystem sync           # Sync all to remote hosts
scitex-dev docs list                # Browse aggregated docs
scitex-dev skills list              # Browse aggregated skills
scitex-dev skills export --level project  # Export to .claude/skills/
```

## Common Workflows

### "See all SciTeX packages"

```bash
scitex-dev ecosystem list
scitex-dev ecosystem diff           # Show uncommitted changes
```

### "Sync ecosystem"

```bash
scitex-dev ecosystem sync           # Preview (dry run)
scitex-dev ecosystem sync --confirm # Execute
scitex-dev ecosystem sync-local     # Reinstall locally
scitex-dev ecosystem pull           # Git pull all
scitex-dev ecosystem commit         # Commit across all packages
```

### "Browse documentation"

```bash
scitex-dev docs list
scitex-dev docs get scitex-io api
scitex-dev docs get figrecipe cheatsheet
scitex-dev docs search "session"
```

### "Browse and export skills"

```bash
scitex-dev skills list
scitex-dev skills get scitex-stats SKILL
scitex-dev skills export --level project --dry-run  # Dest: $SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR
```

### "Run tests"

```bash
scitex-dev test local scitex-stats
scitex-dev test hpc scitex-stats         # Submit to SLURM
scitex-dev test hpc-poll <job-id>        # Check status
scitex-dev test hpc-result <job-id>      # Get results
```

## CLI Commands

```bash
# Ecosystem management
scitex-dev ecosystem list|sync|sync-local|pull|commit|diff|fix-mismatches

# Documentation aggregation
scitex-dev docs list|get|search|build

# Skills aggregation
scitex-dev skills list|get|export|update|upgrade

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
| `dev_ecosystem_sync` | Sync all packages to remote hosts |
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
