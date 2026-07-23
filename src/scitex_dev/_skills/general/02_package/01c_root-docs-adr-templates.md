---
description: |
  [TOPIC] Package Root — docs/, ADRs, and templates/
  [DETAILS] The auxiliary root directories for a SciTeX package. Covers `./docs` (human-facing docs, `./docs/sphinx/`, `./docs/assets/`, `./docs/to_claude/`, `./docs/adr/`, `./GITIGNORED/`), the production-served Sphinx HTML bundled in `src/<pkg>/_sphinx_html/`, Architecture Decision Records (location + filename, the lean five-section template, PS-173 enforcement), and the `./templates` wheel-vs-git payload separation for bulky content excluded from the PyPI wheel. Companion to [01_project-structure-root.md](01_project-structure-root.md).
tags: [scitex-general-package-project-structure-root]
---

# Root `docs/`, ADRs, and `templates/`

> Parent leaf: [`./root`](01_project-structure-root.md).

## `./docs` — human-facing documentation

- README is the entry point; deeper docs live here (`./docs/installation.md`, `./docs/details/<topic>.md`).
- `./docs/sphinx/` — Sphinx source tree (`conf.py`, `index.rst`, `*.rst`/`*.md`). See [`04_docs/02_sphinx.md`](../04_docs/02_sphinx.md) for the canonical layout.
- `./docs/sphinx/_build/` — local Sphinx build output. Gitignored.
- `./docs/assets/` — figures, screenshots, diagrams referenced from README and other docs.
- `./docs/to_claude/` — agent context files (guidelines, hooks, examples). **Must be gitignored** — local-machine artifacts, not part of the shipped repo.
- `./docs/adr/` — Architecture Decision Records. See [Architecture Decision Records (ADRs)](#architecture-decision-records-adrs) below.
- `./GITIGNORED/` — catch-all file-based scratch channel.

### Production-served Sphinx HTML — bundled in `src/<pkg>/_sphinx_html/`

For a package's docs to appear on **<https://scitex.ai/apps/docs/>** after `pip install <pkg>`, the **pre-built HTML must ship inside the wheel**. Convention:

```
docs/sphinx/_build/html/        # local Sphinx output; gitignored
src/<pkg>/_sphinx_html/         # bundled in the wheel; refreshed at release
```

`scitex_dev.docs.get_docs(format="html")` resolves first to the in-wheel `_sphinx_html/`, then falls back to local `_build/`. See [04_docs/02_sphinx.md](../04_docs/02_sphinx.md) for full release recipe.

## Architecture Decision Records (ADRs)

An **ADR** captures one significant architectural decision: the context that forced it, the decision taken, and the consequences. ADRs are a **recommended (not mandated)** ecosystem convention — a repo with no `docs/adr/` is fine. But the moment you *do* keep ADRs, they follow a fixed shape so they stay scannable across the ecosystem.

**Scope: all project kinds** — package, research, grant, draft. Any repo with non-obvious architectural decisions benefits.

### Location + filename

ADRs live at `docs/adr/NNNN-<kebab-slug>.md`:

- `NNNN` — 4-digit zero-padded **sequential** number (`0001`, `0002`, …). The sequence is the chronological order decisions were taken.
- `<kebab-slug>` — lowercase kebab-case summary (`isolation-hardening`, `a2a-v1-compliance`).

```
docs/adr/
├── 0001-isolation-hardening.md
├── 0002-runtime-home-directory.md
└── 0003-a2a-v1-compliance.md
```

### Lean template (exactly five sections)

```markdown
# ADR: <Short title> (<YYYY-MM-DD>)

## Status
Proposed | Accepted | Superseded by ADR-NNNN | Deprecated.

## Context
The forces at play — what problem / pressure forced a decision. (A
`## Problem` heading is the common synonym and is accepted.)

## Decision
What we decided to do, stated as a positive assertion.

## Consequences
What becomes easier and what becomes harder as a result — the
trade-offs, follow-ups, and things now ruled out.
```

Keep it lean. The proven exemplar set is **`scitex-agent-container/docs/adr/`** (0001 isolation-hardening, 0004 a2a-v1-compliance, 0009 claude-setup-delivery) — mirror that depth and tone. Tolerated variants the auditor accepts: `**Status:**` as a bold-line instead of an H2; `## Problem` in place of `## Context`; `## Decisions` (plural) in place of `## Decision`. Sections beyond the five (Implementation, Rationale, References, Addendum, …) are welcome — the five are the *minimum*.

### Enforcement (PS-173, warn during adoption)

`scitex-dev ecosystem audit-project` runs **PS-173** *only when `docs/adr/` exists*:

- (a) every `*.md` matches `NNNN-<kebab-slug>.md` (4-digit prefix, kebab slug);
- (b) each ADR has a title (H1) plus Status / Context / Decision / Consequences.

A repo with **no** `docs/adr/` produces **no finding** (presence is recommended, not mandated). Severity is **W during adoption** — promote to E once the ecosystem's ADR dirs comply.

## `./templates` — wheel-vs-git payload separation

When a package ships **bulky content** that belongs in git but should NOT bloat the PyPI wheel (e.g. `scitex-template/templates/<id>/` ~22 MB scaffolds), vendor it under `./templates/`, exclude from the wheel via hatch, and fetch on first use into `~/.scitex/<pkg-short>/cache/`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]
# templates/ NOT in the wheel — populated at runtime by a shallow clone
```

When NOT to use: anything imported by `src/`, small (<100 KB) static data, content the package can't function without.
