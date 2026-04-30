---
name: scitex-dev-env-vars
description: Environment variables read by scitex-dev at import / runtime. Follow SCITEX_<MODULE>_* convention — see general/10_arch-environment-variables.md.
tags: [scitex-dev, scitex-package]
---

# scitex-dev — Environment Variables

## Paths / config

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_DEV_CONFIG` | Path to the scitex-dev YAML config. | bundled | path |
| `SCITEX_DEV_ENV_SRC` | Path to an env-file sourced at CLI startup. | unset | path |
| `SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR` | Default target when `scitex dev skills export --link`. | `~/.claude/skills/scitex` | path |
| `SCITEX_DIR` | Base SciTeX data dir (ecosystem-wide). | `~/.scitex` | path |
| `SCITEX_DEV_COMPLETE` | Internal sentinel: standalone available. | unset | bool (presence) |

## Ecosystem audit

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_DEV_GITHUB_REMOTES` | Extra GitHub org/user names to sync via `ecosystem pull/sync`. | `ywatanabe1989` | string (CSV) |
| `SCITEX_DEV_HOSTS` | SSH hosts for ecosystem-wide operations. | unset | string (CSV) |
| `SCITEX_DEV_CLAUDE_ACCOUNTS` | Claude-account slugs used by agentic test harness. | unset | string (CSV) |
| `SCITEX_CATEGORIES` | Override for package-category taxonomy. | bundled | string (CSV) |
| `SCITEX_UPSTREAM_AND_DOWNSTREAM_RULES` | Path to upstream/downstream rules YAML. | bundled | path |

## Agentic / HPC test harness

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_DEV_AGENTIC_BACKEND` | Backend for agentic tests (`docker` / `apptainer` / `local`). | `docker` | string |
| `SCITEX_DEV_AGENTIC_DOCKER_IMAGE` | Docker image for the agentic harness. | bundled tag | string |
| `SCITEX_DEV_TEST_HOST` | HPC host for `scitex dev test hpc`. | `—` | string |
| `SCITEX_DEV_TEST_PARTITION` | SLURM partition. | `—` | string |
| `SCITEX_DEV_TEST_CPUS` | CPUs per task. | `4` | int |
| `SCITEX_DEV_TEST_MEM` | Memory per task. | `8G` | string |
| `SCITEX_DEV_TEST_TIME` | Wall-clock limit. | `01:00:00` | string |
| `SCITEX_DEV_TEST_REMOTE_BASE` | Remote base dir for staged sources. | `~/scratch/scitex-test` | path |

## Cross-package

| Variable | Owner | Purpose |
|---|---|---|
| `SCITEX_AGENT_CONTAINER_CI_ANTHROPIC_API_KEY` | scitex-agent-container | CI-only API key, consumed when launching a container from scitex-dev. |
| `SCITEX_API_TOKEN` | scitex-cloud | Ecosystem API token. |
| `SCITEX_OROCHI_HOST` / `_PORT` / `_TOKEN` | scitex-orochi | Orochi hub connection when fleet features are used. |
| `SCITEX_MCP_USE_*` | general | MCP tool-group opt-out flags (see `general/10`). |

## Feature flags

None module-private. Uses the ecosystem-wide `SCITEX_MCP_USE_<MODULE>=0`
opt-out pattern.

## Audit

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/scitex-dev/src/ | sort -u
```
