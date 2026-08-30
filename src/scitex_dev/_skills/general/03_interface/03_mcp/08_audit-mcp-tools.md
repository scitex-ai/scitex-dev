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
| The same bridge defect, seen from a package that does not ship the bridge | §1u | ✅ static | `scitex/_mcp_tools/<pkg>.py` ships in the UMBRELLA. When any other package's audit finds it bad, the finding is attributed to `scitex` and emitted at **warn** tier: the audited package neither contains the file nor depends on the umbrella, so it cannot fix it and must not be gated on it. Still printed, still counted, still carries the remedy — only the blame moves. Warn-tier sibling of an error rule, same construction as `§10w` beside `§10`. |
| No double prefix (`<pkg>_<pkg>_*`)                                    | §1      | ✅ static   | Per-tool name check.                                                  |
| Standalone tools use bare names when umbrella mounts with namespace   | §1/§2   | TODO        | If umbrella bridge calls `safe_mount(..., namespace="<pkg>")`, every tool registered on `scitex_<pkg>._mcp_server.mcp` must NOT start with `<pkg>_`. Auditor today only catches the umbrella half (hand-wrap); add the inverse to flag pre-prefixed standalone tools (the scitex-dataset 2026-05-06 case — 21 `dataset_<x>` tools renamed at once). |
| Tool naming `<pkg>_<verb>_<noun>` snake_case                          | §2      | ✅ static   | snake_case + verb/noun split + bare-verb-allowlist for `_save`/`_speak`/etc. |
| Required subcommands (`mcp start | doctor | list-tools | install`) on the CLI | §3 | ✅ static + behavioral | **Static:** click-tree walk verifies all four leaves under the `mcp` group; missing any one is a §3 violation (the scitex-scholar pre-2026-05-06 case shipped only `list-tools` and went unflagged because the check was behavioral-only). **Behavioral:** under `--behavioral`, also probes `<cli> mcp <sub> --help` to confirm the leaf actually wires up. |
| `mcp list-tools` accepts `-v|-vv|-vvv` and `--json`                   | §4      | ✅ behavioral | Monotonic ladder check + JSON parseability.                          |
| `<pkg>_skills_list` and `<pkg>_skills_get` present                    | §5      | ✅ static   | Accepts both prefixed and bare (Convention A vs B).                  |
| Every public Python API has matching MCP tool                         | §6      | ✅ static   | Functions only (classes filtered); >50% missing → flag.              |
| Every MCP tool traces back to a public Python API (no orphans)        | §6      | ✅ static   | Skill-tool envelope (`skills_*`) excluded; >3 orphans → flag.        |
| No banned synonyms in tool names (`io_ls`, `io_rm`, …)                | §2      | ✅ static   | Maps `ls`→`list`, `rm`→`delete`, `display`→`show`, etc.              |
| JSON-schema arg parity at `-vvv`                                      | §6      | ❌ TODO     | Currently only verifies `--json` parses, not arg-name/type match.    |

The matrix layout mirrors `audit-cli` ([CLI §1d](../02_cli/07_audit-cli.md)).

## What it should flag

- **Mount drift.** Bridge file in `scitex/_mcp_tools/<pkg>.py` hand-wraps tools (any `@mcp.tool()` decorator) instead of `safe_mount`.
- **Standalone-prefix drift.** Standalone `_mcp_server.mcp` registers a tool whose name starts with `<pkg>_` while the umbrella bridge mounts with `namespace="<pkg>"` — strip the prefix in the standalone (the namespace is added at mount time).
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
- Skip pass-through entries (same exemption mechanism as the CLI auditor — see [CLI §1c](../02_cli/05_pass-through.md)).
