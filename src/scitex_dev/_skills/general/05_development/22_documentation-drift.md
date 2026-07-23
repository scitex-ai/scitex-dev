---
description: |
  [TOPIC] Documentation drift — the loosely-coupled sibling of version drift
  [DETAILS] Version drift is about which code runs where; documentation drift is
  the parallel axis — does the doc still match the code it describes? It is
  harder because docs are only loosely coupled to code, so they drift silently
  and become confidently wrong. Where it hides (README, `_skills/`, CLI help vs
  reference, docstrings, demos, cross-package refs), the existing scitex-dev
  detectors, and the three durable moves in preference order (generate from
  code; put under an audit rule; fix at the point of notice). Companion to
  13_version-drift-management.md.
tags: [scitex-general-development-version-drift]
---

# Documentation drift — the loosely-coupled sibling

## 7. Documentation drift — the loosely-coupled sibling

Version drift is about *which code runs where*. **Documentation drift**
is the parallel axis: does the doc still match the code it describes?
It is in some ways harder, because docs are only **loosely coupled** to
code — nothing forces a README, skill, CLI-reference, docstring, or
example to update when the code under it changes, so it drifts silently
and becomes *confidently wrong* (worse than absent — a reader trusts
it). The constitution's Principle 1 is the governing rule:
**documents and skills are never the source of truth; verify against
the code.**

Where it hides (drift layers, doc edition): `README.md` (sections,
badges, install/usage snippets), the `_skills/<pkg>/` tree, CLI
`--help` vs the hand-written CLI-reference, docstrings vs signatures,
`_demo_*.py`/examples vs the current API, and cross-package references
(one package's doc naming another's moved symbol).

Detectors that already exist in scitex-dev — use them, don't reinvent:

```bash
scitex-dev ecosystem audit-all <pkg>        # includes the doc-surface rules below
scitex-dev ecosystem audit-skills <pkg>     # _skills/<pkg>/ §1–§FM structure
```

- README structure / sections / badge rules (PS-1xx) — see
  `_cli/audit/_project/_check_readme_*.py`.
- Skills structure + self-explain quality —
  [04_skills-self-explain.md](04_skills-self-explain.md).
- Doc-surface precedence (which surface wins when two disagree) —
  [05_doc-surfaces.md](05_doc-surfaces.md).

Three durable moves, in preference order (mirror the version-drift
strategy: one SSoT + a cheap detector):

1. **Generate the doc from the code** so it *cannot* drift — CLI
   reference from `--help`, the API tree from introspection
   (`list-python-apis`), config docs from the schema. Generated docs
   are always in sync by construction.
2. **Put the assertion under an audit rule** where prose is
   unavoidable, so a drifted doc becomes a *red check* (the same
   feedback-loop principle as §4) instead of a silent lie.
3. **Fix at the point of notice** — a doc that contradicts the code is
   a bug in the doc; correct it then and there (constitution §3,
   keep-it-tidy), never treat it as "someone else's cleanup."
