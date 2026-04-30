---
name: interfaces-overview
description: The five interfaces every SciTeX package must expose — Python API (primary), CLI (noun-verb), MCP (fastmcp), Skills (_skills/ directory), optional HTTP (FastAPI). Includes the delegation chain (Python API is canonical; CLI/MCP/HTTP are thin wrappers with no original logic) and cross-interface parity expectations. Use as the entry point when onboarding a new package or checking that all interfaces agree on a given feature.
tags: [scitex-python, scitex-general, scitex-package, meta]
---

# Five Interfaces (Required per Package)

Every SciTeX package exposes up to five interfaces. No logic duplication — all delegate to the Python API (the single source of truth).

| # | Interface | Audience | Delegates to | Required |
|---|-----------|----------|--------------|----------|
| 1 | **Python API** | Scripts, notebooks | — (source of truth) | ✅ Required |
| 2 | **CLI** | Terminal, shell | Python API | Recommended when package has a user-facing surface; optional for pure library utilities |
| 3 | **MCP Server** | AI agents (actions) | CLI commands | Recommended when package has a user-facing surface; optional for pure library utilities |
| 4 | **Skills** | AI agents (discovery) | Static markdown | ✅ Required |
| 5 | **HTTP API** | Web clients | Python API | ⚪ Optional |

## Sub-skills

* [03_interface_01_python-api/](03_interface_01_python-api/) — Minimal API design, no logic duplication (split into per-section files; start at [00_index.md](03_interface_01_python-api/00_index.md))
* [03_interface_02_cli/](03_interface_02_cli/) — Required sub-commands, flags, consistency rules (split into per-section files; start at [00_index.md](03_interface_02_cli/00_index.md))
* [03_interface_03_mcp/00_index.md](03_interface_03_mcp/00_index.md) — fastmcp patterns, reproducibility, standard commands
* [03_interface_04_skills/](03_interface_04_skills/) — `_skills/` layout, SKILL.md format, registration, export, frontmatter (split into per-section files; start at [00_index.md](03_interface_04_skills/00_index.md))
* [03_interface_05_http-api/](03_interface_05_http-api/) (split into per-section files; start at [00_index.md](03_interface_05_http-api/00_index.md)) — Optional FastAPI, delegation rules
