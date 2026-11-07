---
description: |
  YAML frontmatter convention for every SciTeX skill file — single
  `description:` field carrying inline `[WHAT]/[WHEN]/[HOW]` markers
  (SKILL.md) or `[TOPIC]/[DETAILS]` markers (leaf), canonical single-tag
  scheme, and SKILL.md-only fields (`allowed-tools`, `primary_interface`,
  `interfaces`). Use when authoring any new skill or auditing existing
  frontmatter.
tags: [scitex-general-interface-skills-frontmatter-metadata]
---

# Skill Frontmatter Metadata

Every SciTeX skill file (the per-skill `SKILL.md` and every leaf `.md` under it) carries YAML frontmatter. Convention below locks a single `description:` field as the source of truth, with inline labels so authors and the auditor can both see the conceptual structure.

## 0. Start with frontmatter; omit generated banners and footers

Dev's skill catalog reads an opening YAML block only when `---` starts the file.
Preceding timestamp blocks, license banners or blank lines prevent that parser
from discovering metadata. This describes Dev's implemented parser, not a
guarantee about every external agent's loader.

Keep metadata at the start. The skill auditor reports a missing initial block
with SK-701 and recognizes the legacy `<!-- ---` header banner with SK-210.

Omit the trailing `<!-- EOF -->` marker. SK-211 rejects that marker at the end
of the file, with optional trailing whitespace. It is a separate style check:
a footer does not prevent Dev's catalog parser from reading valid opening
metadata. Other comments are not automatically SK-211 violations.

Implementation: `_ecosystem/_skills/_frontmatter.py` and
`_cli/audit/_skills/_checks.py`. See the
[quality checklist](12_quality-checklist.md) for the source-owned audit rules.

## 1. Required fields

### SKILL.md

| Field | Purpose |
|---|---|
| `name` | MUST equal the package's pip-name (e.g., `scitex-io`). |
| `description` | Block literal `\|`. MUST contain inline markers `[WHAT]`, `[WHEN]`, `[HOW]` — each typically on its own line. |
| `tags` | Exactly `[scitex-<pkg>]` — one canonical tag per SKILL.md. |

Example:

```yaml
---
name: scitex-io
description: |
  [WHAT] Universal scientific file I/O with 30+ format handlers
  (HDF5, NPY, CSV, JSON, MAT, PKL, ...).
  [WHEN] Reading or writing scientific data files in Python.
  [HOW] `import scitex_io as sio; sio.save(obj, path)`.
tags: [scitex-io]
allowed-tools: mcp__scitex_io__*
primary_interface: python
interfaces:
  python: 3
  cli: 2
  mcp: 2
  skills: 3
  http: 0
---
```

### Leaf

| Field | Purpose |
|---|---|
| `description` | Block literal `\|`. MUST contain inline markers `[TOPIC]` and `[DETAILS]`. |
| `tags` | First tag canonical: `scitex-<pkg>-<slug>` where `<slug>` = filename minus `NN_` prefix and `.md`. Optional topical tags after. |

Leaves do **NOT** carry `name:` (filename is identity). They do **NOT** carry `allowed-tools` / `primary_interface` / `interfaces` (SKILL.md-only — see §2).

Example leaf for `01_installation.md` in `scitex-io`:

```yaml
---
description: |
  [TOPIC] Installation
  [DETAILS] pip install scitex-io; verify with `python -c "import scitex_io"`.
tags: [scitex-io-installation]
---
```

YAML block literal `|` lets the description span multiple lines while remaining a single string field. Newlines inside the block become `\n` characters that the agent reads.

The Dev skill catalog decodes descriptions with safe YAML parsing rather than
advertising the literal `|` marker. It preserves literal-block newlines and
decodes folded or quoted strings. Malformed YAML, custom object tags and
non-string descriptions do not become catalog descriptions; the skill auditor
remains responsible for reporting metadata convention violations. The catalog
keeps the skill's relative identity and owner version separate from its text.
Implementation: `_ecosystem/_skills/_frontmatter.py`; behavioral controls:
`tests/scitex_dev/_ecosystem/_skills/test__frontmatter.py`.

Skill export stamps `version` and `exported_via` only in the opening frontmatter
block. An identically named field in a body example is not export metadata and
must remain unchanged. Stamping preserves the body, existing header spacing and
line endings; legacy pages without frontmatter receive a new metadata block.
Regression controls: `test__frontmatter_stamping.py` in the same test directory.

## 2. Recommended for SKILL.md only

| Field | Purpose |
|---|---|
| `allowed-tools` | Tool prefix the skill may use without per-call approval — e.g., `mcp__scitex_io__*`. Omit if no MCP server. |
| `primary_interface` | Highest-rated interface: `python`, `cli`, `mcp`, `skills`, `http`, or `mixed`. |
| `interfaces` | Star-rating dict (0–3) per interface; renders as the header line. |

## 3. Single source of truth

`description:` is the only place the WHAT/WHEN/HOW (or TOPIC/DETAILS) content lives. There are no separate `what:`/`when:`/`how:`/`topic:`/`details:` fields. The auditor checks marker presence via SK-706 (SKILL.md) and SK-711 (leaf); regeneration / derivation is no longer part of the design.

## 4. Claude Code standard fields (optional)

Use only when the skill is interactive (slash command). Most SciTeX skills are rule files and need none of these.

| Field | Purpose |
|---|---|
| `argument-hint` | Autocomplete hint, e.g. `[issue-number]` |
| `disable-model-invocation` | `true` = only the user can `/name`-invoke |
| `user-invocable` | `false` = hide from the `/` menu |
| `model` | Model override while the skill is active |
| `effort` | `low` / `medium` / `high` / `max` |

## 5. Canonical `tags` values

| Tag | Meaning |
|---|---|
| `scitex-<pkg>` | SKILL.md canonical tag (one only) |
| `scitex-<pkg>-<slug>` | Leaf canonical tag (first position) |
| `scitex-general` | Ecosystem-wide `general/` skill category |
| `meta` | Rules about writing rules — skill authoring, quality checklists |
| `infra` | Cross-cutting infrastructure |

## 6. Dropped from convention

Do not add to new files. When auditing an old file with these, prefer to delete.

| Field | Why dropped |
|---|---|
| `invocation` | Only `general/` itself uses it; downstream packages rely on `description` keyword-matching. |
| `context_tokens` / `context_tokens_total` | 0/12 packages set it; agents don't read it. |
| `canonical-location` | 1/12; drift detection never built. |
| `see-also` | 0/12; cross-references live in body markdown links instead. |
| `what` / `when` / `how` / `topic` / `details` | Folded into a single `description:` with inline markers (§1). |
| Multi-tag SKILL.md (`[scitex-io, scitex-package]`) | One canonical tag per SKILL.md (§1). |
| Leaf `name:` field | Filename is identity (§1). |

## Cross-references

- [03_skill-md-as-index.md](03_skill-md-as-index.md) — SKILL.md template
- [13_standard-template.md](13_standard-template.md) — copy-paste scaffold matching this convention
- [12_quality-checklist.md](12_quality-checklist.md) — release-gate verification (SK-706–SK-711)
