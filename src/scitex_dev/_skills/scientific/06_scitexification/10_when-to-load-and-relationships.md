---
description: |
  [TOPIC] Scitexification — when to load, and relationship to other skills.
  [DETAILS] The load/do-not-load gate for the scitexification series
  (inherited working code, research-bundle/supplement/notebook
  translation, the hand-writing-claims-JSON and copy-paste-matplotlib
  stop signs) and how this skill composes with — rather than duplicates
  — project structure, per-package API surfaces, the clew-specific
  siblings, and PDF reporting. Moved verbatim out of SKILL.md.
tags: [scitexification, scitexification-when-to-load]
---

## When to load this skill

Load when **any** of the following is true:

- You inherited working code (script, notebook, small repo) and want it
  inside the ecosystem with minimal rewrite.
- An agent is asked to translate a research bundle, paper supplement,
  or one-off notebook into a SciTeX project.
- You are about to hand-write `data/results/claims.json` (or any
  results/output JSON, etc.) — **stop**, read chapter `04_repro-clew`,
  use the API.
- You are about to copy-paste a `matplotlib` figure call from a paper
  template — **stop**, read chapter `03_plt-patterns`, use the figrecipe
  pattern.

Do **not** load this skill when:

- You are starting a brand-new SciTeX project from scratch — go to
  [`../02_research-project_*`](../) (project structure rules).
- You are auditing or building a SciTeX **package** (i.e. publishing
  scitex-xxx) — go to [`../../general/`](../../general/) (engineering
  rules for package authors).

## Relationship to other skills

This skill **does not duplicate** content elsewhere; it composes them.

- For project **structure** (where files go, what `./config/` looks like,
  what `./data/` allows): see `../02_research-project_*`. This skill
  assumes a working knowledge of that structure as the *target* of the
  translation.
- For per-package **API surface** (the full `stx.io` save/load type
  matrix, figrecipe's figure types, scitex-clew's primitive operations):
  see the per-pkg SKILL.md (`~/.claude/skills/scitex/scitex-io/`,
  `.../figrecipe/`, `.../scitex-clew/`). This skill teaches *which*
  primitive to reach for during translation, not *what* the primitive
  does internally.
- For **Clew-specific** translation (project-aware DAG, evidence-bound
  claims, the validity chain): see `04_clew_*` skills. Those are
  specializations of scitexification stages 1+2+4 for the Clew-tracked
  flow. If you only need to scitexify and *don't* need Clew
  verifiability, ignore the `04_clew_*` skills.
- For **PDF reporting** (recurring scientific PDF deliverables): see
  `03_reporting_*`. Reporting is a *downstream* concern; scitexify first,
  then report.
