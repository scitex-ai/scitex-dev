---
name: skills-numbered-prefix-convention
description: Two-level `NN_<category>_NN_<topic>.md` numbering rule for `_skills/` leaves — `01-09` interfaces (quick start, Python API, CLI, MCP), `10-19` features, `20-29` meta. Gives a fresh agent an implicit reading order so SKILL.md links are sortable. Use whenever a package's skill count exceeds 3-4 leaves.
tags: [scitex-python, scitex-general, scitex-package, meta]
---

# Numbered-Prefix File Convention

Once a package has more than 3-4 skill files, use **numbered prefixes** so scitex-scholar / scitex-io / scitex-template all share the same browsing layout.

## Buckets

| Range | Purpose | Examples |
|---|---|---|
| `01-09` | Interfaces — quick start, Python API, CLI, MCP | `01_quick-start.md`, `02_python-api.md`, `03_cli-reference.md`, `04_mcp-tools.md` |
| `10-19` | Features — one focused capability per file | `10_save-and-load.md`, `11_centralized-config.md`, `12_supported-formats.md` |
| `20-29` | Meta — env vars, lint rules, release notes | `20_env-vars.md`, `21_linting-rules.md` |

## Reasoning

A fresh agent landing on the package can read 01-04 to understand the surface in under 5 minutes, then drill into a 10-series file only when relevant. Without numbering the index has no implicit reading order; with numbering the SKILL.md links are sortable.

## Standard-5 leaf set (>70% adoption)

Every package should ship these five leaves. The 12-package audit (Tier A + B) shows them as near-universal — when missing, it is because the package genuinely lacks that interface.

| Leaf | Adoption | Required when |
|---|---|---|
| `01_quick-start.md` | 11/12 | always — 30-second tour, install + import + smallest useful example |
| `02_python-api.md` | 10/12 | the package exposes a Python API (almost every package) |
| `03_cli-reference.md` | 9/12 | the package ships a CLI |
| `04_mcp-tools.md` | 9/12 | the package registers MCP tools |
| `20_env-vars.md` | 11/12 | the package reads any `SCITEX_<MODULE>_*` env var |

Beyond these five, leaves are package-specific (workflows in 10–19, deeper meta in 20–29, architecture in 30+). The scaffold in [13_standard-template.md](13_standard-template.md) creates all five as the starting point.

## Rules

- 2-digit zero-padded: `01_`, `02_`, …, `99_`. No gaps within a group.
- Prefixes express **logical** order, not alphabetical.
- `SKILL.md` itself has **no** numeric prefix.
- Filenames are **kebab-case** after the prefix: `01_ecosystem_01_upstream-and-downstream.md`.
- **NEVER** rename a prefixed file by hand; use `git mv` so history is preserved.

## Optional second-level grouping (`general/` mirror)

For very large skill trees that need an extra level of grouping, use the two-level form `NN_<category>_NN_<topic>.md` — e.g. `01_ecosystem_04_environment-variables.md`. The first `NN` is the section, the trailing `NN_<topic>` orders leaves within the section. `general/` itself uses this form.

## Cross-references

- [03_skill-md-as-index.md](03_skill-md-as-index.md) — index links should be in prefix order
- [12_quality-checklist.md](12_quality-checklist.md) — naming/ordering checks at release-gate
