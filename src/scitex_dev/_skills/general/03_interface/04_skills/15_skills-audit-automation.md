---
description: |
  [TOPIC] Skills Quality Checklist Automation
  [DETAILS] The programmatic skills linter — `scitex-dev ecosystem audit-skills <distribution>`. Full `SK<§><idx>` rule-code table (directory / naming / index / leaf-size / frontmatter checks), §1 conditionality of the mandatory-leaf rules, the `--fix` frontmatter auto-fix behavior, run examples, and exit codes.
tags: [scitex-general-interface-skills-quality-checklist-automation]
---

# SciTeX Package Skills — Audit Automation

Section 9 of the [12_quality-checklist.md](12_quality-checklist.md) release gate.

## 9. Automation

Programmatic linter ships as `scitex-dev ecosystem audit-skills <distribution>` —
mirrors `audit-cli`, `audit-mcp-tools`, `audit-python-apis`. Rule codes
`SK<§><idx>`:

| Rule | §  | What it checks |
|------|----|----------------|
| SK-101 | §1 | `_skills/` directory exists in package source |
| SK-102 | §1 | `_skills/<pip-name>/SKILL.md` index file present |
| SK-103 | §1 | no forbidden subdirectories (`legacy/`, `.old/`) |
| SK-104 | §1 | no duplicate index (`SKILL_INDEX.md`, `INDEX.md`, `README.md` shadowing) |
| SK-201 | §2 | every leaf `.md` carries a 2-digit numeric prefix |
| SK-202 | §2 | `SKILL.md` itself has no numeric prefix |
| SK-203 | §2 | filenames are kebab-case after the prefix |
| SK-210 | §2a | no HTML-comment header banner above frontmatter |
| SK-211 | §2a | no `<!-- EOF -->` trailing marker |
| SK-301 | §3 | `SKILL.md` ≤ 4 KB / 80 lines |
| SK-302 | §3 | every sibling leaf is referenced from `SKILL.md` (no orphans) |
| SK-401 | §4 | no leaf exceeds 10 KB / 200 lines |
| SK-601 | §6 | skill text uses bare `import scitex` (not `as stx`) |
| SK-105 | §1 | `01_installation.md` present (mandatory) |
| SK-106 | §1 | `02_quick-start.md` present (mandatory) |
| SK-107 | §1 | `03_python-api.md` present iff package exposes any public Python API |
| SK-108 | §1 | `04_cli-reference.md` present iff `[project.scripts]` ships any entry |
| SK-109 | §1 | `05_mcp-tools.md` present iff MCP server entry-point registered |
| SK-110 | §1 | `06_http-api.md` present iff package ships HTTP routes |
| SK-111 | §1 | `20_env-vars.md` present iff source references any `SCITEX_<MOD>_*` env var |
| SK-701 | FM | every file has a `---` frontmatter block at line 1 |
| SK-702 | FM | frontmatter contains required `name:` |
| SK-703 | FM | frontmatter contains required `description:` |
| SK-704 | FM | frontmatter contains required `tags:` |
| SK-705 | FM | leaf MUST NOT carry `name:` field (filename = identity) |
| SK-706 | FM | SKILL.md `description:` contains inline markers `[WHAT]`, `[WHEN]`, `[HOW]` (each on its own line is fine) |
| SK-708 | FM | SKILL.md `name:` exactly matches the package's pip-name |
| SK-709 | FM | SKILL.md `tags:` equals `[scitex-<pkg>]` exactly (one canonical tag) |
| SK-710 | FM | leaf `tags[0]` equals `scitex-<pkg>-<slug>` (canonical-first ordering) |
| SK-711 | FM | leaf `description:` contains inline markers `[TOPIC]` and `[DETAILS]` |

### §1 Conditionality

SK-105–SK-106 are unconditional. SK-107–SK-111 are gated by pyproject.toml inspection / source scanning — auditor checks whether the package actually ships the interface (public Python API / `[project.scripts]` / MCP entry-point / HTTP framework import / `SCITEX_<MOD>_*` env reference) before nagging for the missing leaf.

### §FM Auto-fix

`scitex-dev ecosystem audit-skills <pkg> --fix` mechanically fixes SK-705 (strip leaf `name:`), SK-709 (rewrite SKILL.md `tags:` to `[scitex-<pkg>]`), and SK-710 (prepend canonical `scitex-<pkg>-<slug>` to leaf `tags`). Frontmatter-only, idempotent, prints a diff. SK-706 / SK-711 (description marker presence) require manual edits — description is the source of truth.

Run examples:

```bash
scitex-dev ecosystem audit-skills scitex-io
scitex-dev ecosystem audit-skills scitex-io --json
scitex-dev ecosystem audit-skills scitex-io --rule SK-210 --rule SK-211
```

Exit codes: `0` = clean, `1` = violations, `2` = package not installed.

Tracking: see `02_package/03_quality.md` (sibling) for the broader release
checklist.
