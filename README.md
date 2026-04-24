# SciTeX Dev (`scitex-dev`)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Shared developer utilities for the SciTeX ecosystem</b></p>

<p align="center">
  <a href="https://badge.fury.io/py/scitex-dev"><img src="https://badge.fury.io/py/scitex-dev.svg" alt="PyPI version"></a>
  <a href="https://scitex-dev.readthedocs.io/"><img src="https://readthedocs.org/projects/scitex-dev/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/ywatanabe1989/scitex-dev/actions/workflows/test.yml"><img src="https://github.com/ywatanabe1989/scitex-dev/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>

<p align="center">
  <a href="https://scitex-dev.readthedocs.io/">Full Documentation</a> · <code>pip install scitex-dev</code>
</p>

---

## Problem and Solution


| # | Problem | Solution |
|---|---------|----------|
| 1 | **33 packages get out of sync** -- one package bumps a dep; consumers forget to update minima; users hit runtime errors | **`scitex-dev ecosystem` suite** -- `list`, `diff`, `sync`, `fix-mismatches`, `commit`, `pull`, `push` — fanout tooling for coordinated releases |
| 2 | **Skills scattered across 33 source repos** -- users can't discover them easily | **`scitex-dev skills export --link`** -- symlink the full skill pack into `~/.claude/skills/scitex/` for live-edit dev loops |
| 3 | **Testing against a SLURM cluster requires ssh + sbatch dance** -- interrupts local flow | **`scitex-dev test hpc` + `--poll` + `--result`** -- non-blocking submit, query later |

## Problem

The SciTeX ecosystem spans multiple packages (scitex-clew, scitex-writer, scitex-stats, figrecipe, etc.), each with their own documentation, versions, APIs, and CLI commands. Keeping them in sync, discovering what's available, and maintaining consistency across the ecosystem becomes increasingly difficult as it grows.

## Solution

`scitex-dev` (v0.5.1) provides a unified toolkit for developing and maintaining the SciTeX ecosystem:

- **Version management** — detect and fix version mismatches across pyproject.toml, `__init__.py`, git tags, and PyPI
- **CI/CD** — check GitHub Actions status, wait for workflows, verify PyPI publish
- **Deployment** — deploy and verify production on remote hosts
- **Skills** — aggregate, export, and verify AI agent skill pages across the ecosystem
- **Docs aggregation** — discover, build, and search documentation across all packages
- **LLM-friendly types** — `Result`, `ErrorCode`, `@supports_return_as` for consistent structured responses

Zero runtime dependencies. Pure stdlib.

## Installation

```bash
pip install scitex-dev

# With CLI support:
pip install scitex-dev[cli]

# With MCP server:
pip install scitex-dev[mcp]

# Everything:
pip install scitex-dev[all]
```

## Modules

| Module | Functions | Purpose |
|--------|-----------|---------|
| `skills` | `list_skills`, `get_skill`, `export_skills`, `verify_docs_and_skills` | AI agent skill discovery and export |
| `fix` | `detect_mismatches`, `fix_local`, `fix_remote`, `fix_init_version`, `bump_version`, `determine_bump_type`, `verify_versions` | Version mismatch detection and repair |
| `ci` | `check_ci`, `get_failing_packages`, `verify_pypi_config`, `create_github_release`, `wait_for_workflow`, `check_pypi_publish` | GitHub Actions and PyPI integration |
| `deploy` | `deploy_scitex_cloud`, `verify_production` | Remote host deployment |
| `versions` | `get_commits_since_tag` | Commit tracking since last release |
| `_dist_info` | `clean_stale_dist_info` | Internal: stale dist-info cleanup |

## Quick Start

```python
from scitex_dev.fix import detect_mismatches, fix_local, verify_versions
from scitex_dev.ci import check_ci, get_failing_packages
from scitex_dev.skills import list_skills, export_skills

# Detect version mismatches across the ecosystem
mismatches = detect_mismatches()

# Fix mismatches locally (dry run by default)
fix_local(packages=["scitex-stats"], confirm=True)

# Check CI status
status = check_ci(packages=["scitex", "figrecipe"])
failing = get_failing_packages()

# List and export AI agent skills
skills = list_skills()
export_skills()
```

## Four Interfaces

<details>
<summary><b>Python API</b></summary>

```python
# Version management
from scitex_dev.fix import detect_mismatches, fix_local, fix_remote, verify_versions
mismatches = detect_mismatches()
fix_local(packages=["scitex-stats"], confirm=True)
verify_versions()

# CI/CD
from scitex_dev.ci import check_ci, get_failing_packages, check_pypi_publish
status = check_ci()
failing = get_failing_packages()

# Skills
from scitex_dev.skills import list_skills, get_skill, export_skills
skills = list_skills()
page = get_skill(package="scitex-stats")
export_skills()

# Deployment
from scitex_dev.deploy import deploy_scitex_cloud, verify_production
deploy_scitex_cloud(host="nas", confirm=True)

# Commit tracking
from scitex_dev.versions import get_commits_since_tag
commits = get_commits_since_tag("scitex-stats")

# LLM-friendly types
from scitex_dev import Result, supports_return_as
```

</details>

<details>
<summary><b>CLI Commands</b></summary>

```bash
# Ecosystem management
scitex-dev ecosystem list
scitex-dev ecosystem list --versions
scitex-dev ecosystem fix-mismatches --dry-run
scitex-dev ecosystem sync

# Documentation
scitex-dev docs --package scitex-writer
scitex-dev search "save figure"

# Bulk rename
scitex-dev rename old_name new_name --dry-run

# See all commands
scitex-dev --help
scitex-dev --help-recursive
```

</details>

<details>
<summary><b>MCP Server</b></summary>

```bash
# Start server
scitex-dev mcp start

# Check setup
scitex-dev mcp doctor
scitex-dev mcp list-tools

# Installation info
scitex-dev mcp installation
```

**Claude Code Setup** — add `.mcp.json` to your project root. Use `SCITEX_DEV_ENV_SRC` to load configuration from a `.src` file:

```json
{
  "mcpServers": {
    "scitex-dev": {
      "command": "scitex-dev",
      "args": ["mcp", "start"],
      "env": {
        "SCITEX_DEV_ENV_SRC": "${SCITEX_DEV_ENV_SRC}"
      }
    }
  }
}
```

Switch environments via your shell profile:

```bash
# Local machine
export SCITEX_DEV_ENV_SRC=~/.scitex/dev/local.src

# Remote server
export SCITEX_DEV_ENV_SRC=~/.scitex/dev/remote.src
```

</details>

<details>
<summary><strong>Skills — for AI Agent Discovery</strong></summary>

<br>

Skills provide workflow-oriented guides that AI agents query to discover capabilities and usage patterns.

```bash
scitex-dev skills list              # List available skill pages
scitex-dev skills get SKILL         # Show main skill page
scitex-dev skills export --package scitex-dev  # Export to Claude Code
# Private skills (~/.scitex/*/skills/*-private/) are symlinked automatically
```

| Skill | Content |
|-------|---------|
| `result-types` | `Result`, `ErrorCode`, `@supports_return_as` for LLM-friendly responses |
| `cli-mcp-utils` | CLI and MCP utility helpers |
| `versions` | Version management, mismatch detection and fixing |
| `ecosystem` | Ecosystem list, sync, and commit workflows |
| `rename` | Safe bulk rename with cross-reference updates |
| `docs-search` | Documentation aggregation and unified search |
| `test-runner` | Local and HPC test execution |
| `config` | Package configuration and priority config patterns |

</details>

## Part of SciTeX

`scitex-dev` is part of [SciTeX](https://scitex.ai). It provides the shared infrastructure that keeps the ecosystem consistent and discoverable. When used with the orchestrator package `scitex`, it enables unified version management, CI monitoring, and deployment across all modules:

```python
from scitex_dev.fix import detect_mismatches, verify_versions
from scitex_dev.ci import check_ci, get_failing_packages

# See the entire ecosystem at a glance
mismatches = detect_mismatches()
verify_versions()

# Monitor CI across all packages
failing = get_failing_packages()
```

The SciTeX system follows the Four Freedoms for Research below, inspired by [the Free Software Definition](https://www.gnu.org/philosophy/free-sw.en.html):

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>AGPL-3.0 — because we believe research infrastructure deserves the same freedoms as the software it runs on.

---

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40">
  </a>
</p>
