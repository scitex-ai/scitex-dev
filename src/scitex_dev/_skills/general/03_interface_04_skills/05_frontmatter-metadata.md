---
name: skills-frontmatter-metadata
description: YAML frontmatter convention for every SciTeX skill file — what is required (`name`, `description`, `tags`), what is recommended based on >70% adoption across the ecosystem (`allowed-tools`, `primary_interface`, `interfaces`), and which earlier extensions are dropped because adoption never converged (`invocation`, `context_tokens`, `canonical-location`, `see-also`). Also documents the Claude Code standard fields. Use when authoring any new skill or auditing existing frontmatter.
tags: [scitex-python, scitex-general, scitex-package, meta]
---

# Skill Frontmatter Metadata

Every SciTeX skill file (the per-skill `SKILL.md` and every leaf `.md` under it) carries YAML frontmatter. Convention below was derived from a 12-package audit (Tier A + Tier B) — fields are listed by **actual ecosystem adoption**, not aspiration.

## 0. Frontmatter must be the very first bytes — no header, no footer

Claude Code parses YAML frontmatter only when the file **starts with `---` on line 1**. Any preceding content — auto-inserted timestamp blocks, license banners, even a blank line — pushes the frontmatter below the first byte and the loader treats the file as plain markdown with no metadata. The same applies to trailing markers like `<!-- EOF -->` for tools that scan the last block.

Required shape:

```markdown
---
name: my-skill
description: ...
tags: [...]
---

# My Skill

...content...
```

Banned at the **top** of any skill / agent / command / hook file: HTML-comment banners, timestamp/author/license blocks, blank lines, or any byte before the opening `---`.

Banned at the **bottom**: trailing `<!-- EOF -->` or similar end-of-file markers.

If your editor auto-inserts these on save, disable that behavior for files under `_skills/`, `skills/`, `agents/`, `commands/`, and `.claude/`. Run the lint script below before commit as a backstop:

```bash
python3 -c "
import re
from pathlib import Path
hdr = re.compile(r'^<!-- ---\n(?:!--.*\n)+!-- --- -->\n+', re.MULTILINE)
ftr = re.compile(r'\n*<!-- EOF -->\s*\$')
for f in Path('src/scitex/_skills').rglob('*.md'):
    t = f.read_text()
    new = ftr.sub('\n', hdr.sub('', t, count=1))
    if new != t: f.write_text(new); print('cleaned', f)
"
```

This is enforced at release-gate time — see [12_quality-checklist.md](12_quality-checklist.md).

## 1. Required (every file)

| Field | Adoption | Purpose |
|---|---|---|
| `name` | 12/12 | Display name. Lowercase + hyphens. Defaults to dir name. |
| `description` | 12/12 | One-line summary. Claude Code uses this to decide auto-load. |
| `tags` | recommended-as-required | Categorisation; agents filter on it. See tag table below. |

```yaml
---
name: scitex-io
description: Universal scientific file I/O with 30+ format handlers.
tags: [scitex-io, scitex-package]
---
```

### Canonical `tags` values

| Tag | Meaning |
|---|---|
| `scitex-package` | Rules that apply to every `scitex-*` repo |
| `scitex-general` | The ecosystem-wide `general/` skill category |
| `scitex-python` | Specific to the scitex-python umbrella package |
| `scitex-<name>` | Owned by a specific package (`scitex-io`, `figrecipe`, …) |
| `research` | Rules for a research project *using* SciTeX |
| `paper` | Manuscript prep — figures, LaTeX, citations |
| `infra` | Cross-cutting infrastructure — SSH, containers, cloud, tunnels |
| `meta` | Rules about writing rules — skill authoring, quality checklists |
| `claude-code` | Claude Code runtime reference material |

A leaf usually carries 2–4 tags: its package, its category, and 1–2 cross-cutting scopes.

## 2. Recommended for SKILL.md (>70% adoption)

| Field | Adoption | Purpose |
|---|---|---|
| `allowed-tools` | 12/12 SKILL.md | Tool prefix the skill may use without per-call approval — e.g., `mcp__scitex__io_*` |
| `primary_interface` | 10/12 SKILL.md | Highest-rated interface: `python`, `cli`, `mcp`, `skills`, `hook`, or `mixed` |
| `interfaces` | 10/12 SKILL.md | Star-rating dict (0–3) per interface; renders as the header line |

```yaml
---
name: scitex-io
description: Universal scientific file I/O with 30+ format handlers.
tags: [scitex-io, scitex-package]
allowed-tools: mcp__scitex__io_*
primary_interface: python
interfaces:
  python: 3
  cli: 2
  mcp: 2
  skills: 3
  hook: 0
  http: 0
---
```

The header line in the SKILL.md body restates the rating for human readers:

```markdown
> **Interfaces:** Python ⭐⭐⭐ · CLI ⭐⭐ · MCP ⭐⭐ · Skills ⭐⭐⭐ · Hook — · HTTP —
```

## 3. Claude Code standard fields (optional)

Use only when the skill is interactive (slash command) rather than a static rule file. Most SciTeX skills are rule files and need none of these.

| Field | Purpose |
|---|---|
| `argument-hint` | Autocomplete hint, e.g. `[issue-number]` |
| `disable-model-invocation` | `true` = only the user can `/name`-invoke; Claude cannot auto-load |
| `user-invocable` | `false` = hide from the `/` menu (default `true`) |
| `model` | Model override while the skill is active |
| `effort` | `low` / `medium` / `high` / `max` |
| `context: fork` | Run in an isolated subagent |
| `agent` | Subagent type when forking |
| `hooks` | Skill-scoped lifecycle hooks |

## 4. Dropped from convention

These were once proposed as ecosystem extensions but adoption never converged. **Do not add to new files.** When auditing an old file with these fields, prefer to delete rather than maintain.

| Field | Why dropped |
|---|---|
| `invocation` | Only `general/` itself uses it; downstream packages rely on `description` keyword-matching |
| `context_tokens` / `context_tokens_total` | 0/12 packages set it; agents don't read it |
| `canonical-location` | 1/12; drift detection never built |
| `see-also` | 0/12; cross-references live in body markdown links instead |

## 5. Per-leaf frontmatter (minimum)

Leaves under SKILL.md carry only:

```yaml
---
name: <leaf-topic>
description: <one-line summary>
tags: [<package>, <category>, ...]
---
```

`allowed-tools`, `primary_interface`, `interfaces` are **SKILL.md-only** — leaves inherit from the index.

## Cross-references

- [03_skill-md-as-index.md](03_skill-md-as-index.md) — SKILL.md template that uses the recommended fields
- [13_standard-template.md](13_standard-template.md) — copy-paste scaffold matching this convention
- [12_quality-checklist.md](12_quality-checklist.md) — release-gate verification
