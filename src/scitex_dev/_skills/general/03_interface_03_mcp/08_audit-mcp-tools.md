---
description: |
  [TOPIC] Interface Mcp Audit
  [DETAILS] SciTeX MCP automated audit — `scitex-dev ecosystem audit-mcp-tools`. Coverage matrix, what it flags, custom dict format. Parallels `audit-cli`.
tags: [scitex-general-interface-mcp-audit-mcp-tools]
---

# §7. Automated check — `scitex-dev ecosystem audit-mcp-tools`

> **Status — shipped (2026-04-30).** Static + behavioral checks for §1–§6 implemented in `scitex_dev._cli_audit._mcp_audit`. Tests in `tests/test_cli_audit_mcp.py`. The §9 [10_audit-checklist.md](10_audit-checklist.md) remains the manual fallback for anything not yet automated.

- Opt-in linter that walks every `scitex-*` package's `_mcp_server.mcp` instance.
- Warns (never errors) on §1–§6 violations.
- Behind the `cli-audit` extra (shared with `audit-cli`).

```bash
pip install 'scitex-dev[cli-audit]'
scitex-dev ecosystem audit-mcp-tools <package-name>
scitex-dev ecosystem audit-mcp-tools --all --json > mcp-drift.json
scitex-dev ecosystem audit-mcp-tools <pkg> --behavioral   # also probe `<cli> mcp ...`
```

## Coverage matrix

| Rule                                                                  | Section | Status      | Notes                                                                |
|-----------------------------------------------------------------------|---------|-------------|----------------------------------------------------------------------|
| Single `FastMCP` instance at `scitex_<pkg>._mcp_server.mcp`           | §1      | ✅ static   | `_resolve_mcp_server` tries `_mcp_server`, `mcp_server`, `_mcp.server`, `mcp.server`. |
| Umbrella bridge uses `safe_mount` (not hand-wrap, not direct `.mount`) | §1     | ✅ static   | Two distinct §1 violations: hand-wrap (per-tool `@mcp.tool()`) and direct `mcp.mount(...)` without `safe_mount`. |
| No double prefix (`<pkg>_<pkg>_*`)                                    | §1      | ✅ static   | Per-tool name check.                                                  |
| Tool naming `<pkg>_<verb>_<noun>` snake_case                          | §2      | ✅ static   | snake_case + verb/noun split + bare-verb-allowlist for `_save`/`_speak`/etc. |
| Required subcommands (`mcp start | doctor | list-tools | show-installation`) on the CLI | §3 | ✅ behavioral | Probes via `<cli> mcp <sub> --help` under `--behavioral`.           |
| `mcp list-tools` accepts `-v|-vv|-vvv` and `--json`                   | §4      | ✅ behavioral | Monotonic ladder check + JSON parseability.                          |
| `<pkg>_skills_list` and `<pkg>_skills_get` present                    | §5      | ✅ static   | Accepts both prefixed and bare (Convention A vs B).                  |
| Every public Python API has matching MCP tool                         | §6      | ✅ static   | Functions only (classes filtered); >50% missing → flag.              |
| Every MCP tool traces back to a public Python API (no orphans)        | §6      | ✅ static   | Skill-tool envelope (`skills_*`) excluded; >3 orphans → flag.        |
| No banned synonyms in tool names (`io_ls`, `io_rm`, …)                | §2      | ✅ static   | Maps `ls`→`list`, `rm`→`delete`, `display`→`show`, etc.              |
| JSON-schema arg parity at `-vvv`                                      | §6      | ❌ TODO     | Currently only verifies `--json` parses, not arg-name/type match.    |

The matrix layout mirrors `audit-cli` ([CLI §1d](../03_interface_02_cli/07_audit-cli.md)).

## What it should flag

- **Mount drift.** Bridge file in `scitex/_mcp_tools/<pkg>.py` hand-wraps tools (any `@mcp.tool()` decorator) instead of `safe_mount`.
- **Double prefix.** Tool names `<pkg>_<pkg>_*` after mount.
- **Banned bare leaves.** Tool name = `<pkg>` only (no verb), or `<pkg>_<verb>` only with no noun where transitive.
- **Synonyms.** `<pkg>_ls` instead of `<pkg>_list`; `<pkg>_rm` instead of `<pkg>_delete`. Same "Avoid" column as the CLI catalog.
- **Parity gap.** Public Python API exists but no MCP tool wraps it (or vice versa: orphan MCP tool with no matching API).
- **Missing skills tools.** `<pkg>_skills_list` / `<pkg>_skills_get` absent.
- **Missing `mcp` subcommands** on the CLI (`start`, `doctor`, `list-tools`, `show-installation`).
- **`mcp list-tools` ladder broken.** `-vv` output ⊄ `-v` output (level not additive).

## Output and exit code

- **Output:** human-readable findings on stderr; machine-readable summary on stdout when `--json` passed.
- **Exit code:** always `0` — warns, doesn't fail. `--strict` (future) flips warnings to errors for CI gating.

## Operational notes

- Run in CI for every `scitex-*` repo.
- Parity check requires both the package AND the umbrella to be installed (so `list-python-apis` and `mcp list-tools` can both run).
- Skip pass-through entries (same exemption mechanism as the CLI auditor — see [CLI §1c](../03_interface_02_cli/05_pass-through.md)).
