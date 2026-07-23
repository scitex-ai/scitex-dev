---
description: |
  [TOPIC] Scitexification — SSoT/build status and references.
  [DETAILS] The SSoT-status maintenance note, the 2026-06-13 status
  checklist (overview drafted, chapters written/dogfooded, tag-syntax
  and discovery-contract still pending, chapter-04-uses-primitives
  rationale), and the full reference list (per-pkg SKILLs, template
  scaffold, research-project/clew/private-skills siblings). Moved
  verbatim out of SKILL.md.
tags: [scitexification, scitexification-status-and-references]
---

<!--
SSoT status (2026-06-13):
  - This SKILL.md is the overview / index for the 6-file scitexification series.
  - The 01-05 chapter files are WRITTEN (substantive content: translation
    inventories, the symlink_to= idiom, worked before/after examples, and
    corner cases per stage), delegating full per-package API surface to the
    companion pkg SKILLs. (They superseded the 2026-06-12 #167 link-stubs.)
  - Discovery (consumer-side `spec.claude.skills: [scitexification]` declarative
    interface) is gated on a separate scitex-dev / SAC contract decision; see
    A2A thread `48d2324b` (proj-paper-scitex-clew ↔ proj-scitex-dev) and
    the "Discovery" section below.
-->

## Status (2026-06-13)

- ✅ This overview SKILL.md drafted.
- ✅ Chapters `01–05` **written** (substantive: per-stage translation
  inventories, the `symlink_to=` DAG idiom, worked before/after examples,
  corner cases; full per-pkg API delegated to the companion SKILLs).
  Dogfooded during the proj-paper-scitex-clew prompt retirement (the
  solver auto-loads this skill instead of a bespoke prompt).
- ⏳ Parent + sub-tag discovery syntax (`scitexification` vs
  `scitexification.io`) requires a small extension in
  `scitex-dev/_cli/skills/_tags.py` — separate issue to be filed.
- ✅ Chapter 04 uses scitex-clew **primitives** (`list_claims`,
  `verify_claim`, `render_dag`) rather than proposing a new
  `emit_results` API. Rationale: scitex-clew stays general-purpose;
  the output/results shape (which keys, which schema) is an experiment-
  specific concern, owned by the consumer (proj-paper-scitex-clew,
  MNIST template, etc.) as a 10-line iterate+filter+emit helper.
  Per operator decision (Telegram msg 125).
- ⏳ Consumer-side discovery contract (`spec.claude.skills:
  [scitexification]` auto-loading) tracked in A2A thread `48d2324b`
  between proj-paper-scitex-clew ↔ proj-scitex-dev.

## References

- `~/.claude/skills/scitex/scitex-io/SKILL.md` — full `stx.io` API surface.
- `~/.claude/skills/scitex/scitex-session/SKILL.md` — `@stx.session.start`
  contract + CONFIG mechanics.
- `~/.claude/skills/scitex/scitex-clew/SKILL.md` — clew primitives,
  registration, verification.
- `~/.claude/skills/scitex/figrecipe/SKILL.md` — figrecipe figure types,
  publication-quality defaults.
- `~/.claude/skills/scitex/scitex-template/SKILL.md` — the cookiecutter
  research-project scaffold (the *target* shape of scitexification).
- [`../02_research-project_*`](../) — what the scitexified result should
  look like structurally.
- [`../04_clew_*`](../) — Clew-tracked specialization of stages 1+2+4.
- [`../05_private-skills_01_consumer-project.md`](../05_private-skills_01_consumer-project.md)
  — where consumer-project-private notes live (post-scitexification).
