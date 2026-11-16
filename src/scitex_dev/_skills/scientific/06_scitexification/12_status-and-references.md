---
description: |
  [TOPIC] Scitexification — scope status and references.
  [DETAILS] What this skill series covers today (chapters 00–13 written,
  the open discovery-syntax item, why stage 4 uses scitex-clew
  primitives instead of a bespoke results API) and the full reference
  list (per-package SKILLs, template scaffold, research-project / clew /
  private-skills siblings).
tags: [scitexification, scitexification-status-and-references]
---

## Status

- ✅ Overview `SKILL.md` + universal playbook `00_playbook.md`.
- ✅ Stage chapters `01–05` written: per-stage translation inventories,
  the `symlink_to=` DAG idiom, worked before/after examples, corner
  cases. Full per-package API surface is delegated to the companion
  SKILLs (see [06_companion-skills.md](06_companion-skills.md)).
- ⏳ Parent + sub-tag discovery syntax (`scitexification` vs
  `scitexification.io`) needs a small extension in
  `scitex-dev/_cli/skills/_tags.py`. Until then, load the umbrella tag
  (see [11_discovery-and-pitfalls.md](11_discovery-and-pitfalls.md)).
- ✅ Stage 4 uses scitex-clew **primitives** (`add_claim`, `list_claims`,
  `verify_claim`, `render_dag`) rather than a new `emit_results` API.
  Rationale: scitex-clew stays general-purpose; *which* keys and schema
  a results file carries is a project-specific concern, owned by the
  project as a short iterate + filter + emit helper over
  `list_claims()`.

## References

- `~/.claude/skills/scitex/scitex-io/SKILL.md` — full `stx.io` API surface.
- `~/.claude/skills/scitex/scitex-session/SKILL.md` — the `@stx.session`
  decorator contract + CONFIG mechanics.
- `~/.claude/skills/scitex/scitex-clew/SKILL.md` — clew primitives,
  registration, verification.
- `~/.claude/skills/scitex/figrecipe/SKILL.md` — figrecipe figure types,
  publication-quality defaults.
- `~/.claude/skills/scitex/scitex-template/SKILL.md` — the cookiecutter
  research-project scaffold (the *target* shape of scitexification).
- [`../02_research-project_*`](../) — what the scitexified result should
  look like structurally.
- [`../04_clew_01_dag-as-map-and-evidence.md`](../04_clew_01_dag-as-map-and-evidence.md)
  — what the clew DAG is (map while building, evidence when publishing).
- [`../04_clew_03_translation-template.md`](../04_clew_03_translation-template.md)
  — a concrete clew-tracked project skeleton (Makefile, scripts, gate).
- [`../05_private-skills_01_consumer-project.md`](../05_private-skills_01_consumer-project.md)
  — where project-private notes live (post-scitexification).
