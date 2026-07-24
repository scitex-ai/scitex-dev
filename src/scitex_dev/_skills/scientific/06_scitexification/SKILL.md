---
name: scitexification
description: |
  [WHAT] Scitexification — the verb: translate existing code (a script, a notebook, a small repo, a published-paper supplement) into SciTeX form so it gains the ecosystem's session-managed I/O, scitex-clew evidence binding, publication-quality figures, and project structure. Single source of truth for the migration act itself, package-agnostic; per-package patterns delegate to the per-pkg SKILL.md, and Clew-specific specialization layers on top of this skill via `scientific/04_clew_*`.
  [WHEN] You have existing code that works and want to bring it into the SciTeX ecosystem with minimal rewrite, OR an agent is asked to translate a research bundle, paper supplement, or one-off notebook into a SciTeX project. Load this skill BEFORE picking the per-chapter topic.
  [HOW] Read this SKILL.md first to orient on the 5-stage translation arc; then drill into the topic chapter you need next (`01_io-patterns`, `02_session-config`, `03_plt-patterns`, `04_repro-clew`, `05_naming-and-numbering`). Per-package details (full stx.io API surface, figrecipe figure types, etc.) live in the corresponding per-pkg SKILL.md — this skill references them rather than restating.
tags: [scitexification]
requires:
  # Scitexification is the translation act; the four package-level
  # companions supply the API knowledge an agent needs to actually
  # translate-and-resolve. Loading `scitexification` should also
  # surface these. See 00_playbook.md §"Required companion skills".
  - scitex-session
  - scitex-io
  - figrecipe
  - scitex-clew
user-invocable: true
primary_interface: skills
interfaces:
  python: 0-3
  cli: 0-3
  mcp: 0-3
  skills: 3
  http: 0
---

# Scitexification — the translation act

`pip install scitex-dev` (no extras needed for the skill itself).

> **scitexify** *(verb, derived)* — to convert existing research code into
> the SciTeX idiom: session-managed I/O, project-structured outputs, evidence-
> bound claims, publication-quality figures, mirrored test layout.

This skill is the **single source of truth** for the translation act. It is
deliberately package-agnostic at the top level; each chapter delegates
package-specific patterns to the corresponding per-pkg SKILL.md so the per-
package teams own the surface area they ship.

> **Canonical universal playbook — [00_playbook.md](00_playbook.md).** Read
> this first when scitexifying any artefact. It coins the vocabulary
> (`scitexify` / `scitexification` / `scitexified`), fixes the universal
> contract (universal inputs, pre-flight, phase dispatch, done condition,
> forbidden), and frames the **honest source-grounding** principle — "attempt
> every claim, ground where possible, and when ungroundable include the
> claim with `null` + a reason, NEVER silently omit" — as a general
> scientific-integrity norm independent of any specific evaluator. The
> per-chapter files (01–05) drill into stage-specific patterns; the
> `04_clew_*` siblings are clew-tracked specialisations that compose on
> top of the universal playbook.

## The 5-stage translation arc

The stage-by-stage overview table (chapter-linked) lives in
[13_five-stage-arc.md](13_five-stage-arc.md). In brief: stage 1 I/O
patterns → stage 2 session + config → stage 3 figures → stage 4 claims +
provenance → stage 5 naming + numbering. Stages 1+2 alone give a runnable
project; 3, 4, 5 are strictly additive.

## Chapters & further reading

- [00_playbook.md](00_playbook.md) — the canonical universal playbook (router).
- [01_io-patterns.md](01_io-patterns.md) — stage 1: I/O patterns.
- [02_session-config.md](02_session-config.md) — stage 2: session + config.
- [03_plt-patterns.md](03_plt-patterns.md) — stage 3: figrecipe figures.
- [04_repro-clew.md](04_repro-clew.md) — stage 4: clew claims + provenance.
- [05_naming-and-numbering.md](05_naming-and-numbering.md) — stage 5: naming + numbering.
- [06_companion-skills.md](06_companion-skills.md) — the four required companion skills + declarative loading.
- [07_preflight-and-dispatch.md](07_preflight-and-dispatch.md) — universal pre-flight rules + phase dispatch.
- [08_honest-grounding.md](08_honest-grounding.md) — the honest source-grounding integrity principle.
- [09_done-and-constraints.md](09_done-and-constraints.md) — done condition, forbidden floor, on-failure rule.
- [10_when-to-load-and-relationships.md](10_when-to-load-and-relationships.md) — when to load this skill + relationship to other skills.
- [11_discovery-and-pitfalls.md](11_discovery-and-pitfalls.md) — tags & discovery + the migration pitfalls.
- [12_status-and-references.md](12_status-and-references.md) — SSoT/build status + references.
- [13_five-stage-arc.md](13_five-stage-arc.md) — the 5-stage translation arc table (chapter-linked).
