---
description: |
  [TOPIC] Scitexification Stage 5 — Naming and numbering
  [DETAILS] Stage 5 of the 5-stage scitexification arc: `cnn_v3_final
  _FIXED2.py` becomes `scripts/03_cnn.py` (zero-filled, sortable,
  mirrored under `tests/`); opaque identifiers and ordinals become
  readable symlinks per the project convention in
  `02_research-project_09_id-readability-and-data-immutability.md`. This
  is the COSMETIC stage but it is what makes a SciTeX project navigable
  by a stranger (and by your future self) — the lexicographic-sort of
  `scripts/` matches the temporal-execution order of the DAG.
tags: [scitexification, scitexification-naming-numbering]
---

<!--
Status: STUB — landed alongside SKILL.md so the umbrella's
`05_naming-and-numbering.md` link in the "5-stage table" resolves to a
real file instead of a 404. Full content (the zero-fill rule, the
ordinal vs ID distinction, the `<ordinal>_<verb>` script-naming
convention, the tests/ mirror invariant, and the readable-symlink
recipe from project-structure-09) will land in a follow-up PR scoped to
this chapter only — see #119 for the five-chapter rollout plan.
Cross-skill details (the full project-structure convention) live in
`scientific/02_research-project_09_id-readability-and-data-immutability.md`
and `02_research-project_10_naming-and-numbering.md`.
-->

# Stage 5 — Naming and numbering

The navigability step. Filenames stop carrying state (`*_v3`,
`*_final`, `*_FIXED2`) and start carrying ordering — `scripts/03_cnn.py`
sits between `02_data_prep.py` and `04_eval.py`, mirrored exactly under
`tests/`. Opaque dataset identifiers (`patient_42`, `run_aB9c2`) keep
their machine-readable form on disk for immutability but gain readable
symlinks per the project convention so a human can navigate without
decoding.

> **What changes**: filenames, as a *concept*. The numbers themselves
> (after zero-fill).
> **What stays the same**: the script bodies, the data, the IDs.

## Translation table (sketch)

| Original | SciTeX equivalent |
|---|---|
| `cnn_v3_final_FIXED2.py` | `scripts/03_cnn.py` |
| `eval2.py` / `eval_old.py` / `eval_new.py` | `scripts/04_eval.py` (one canonical, history in git) |
| `tests/test_cnn.py` (alone) | `tests/scripts/test_03_cnn.py` (mirrors `scripts/` 1:1) |
| `data/patient_42_aB9c2.parquet` (immutable, opaque) | `data/by-id/patient_42_aB9c2.parquet` + readable symlink `data/by-name/alice_session_2.parquet` |

Full inventory and the corner cases (renumbering safely when a script
is inserted between 03 and 04, the `_DRAFT_` marker for in-flight
scripts, the `archive/` convention for retired scripts) are pending —
see the **Status** note at the top of this file.

## Follow-up

- The canonical project-structure convention lives in
  `scientific/02_research-project_09_id-readability-and-data-immutability.md`
  and `02_research-project_10_naming-and-numbering.md` — this chapter
  references them; do not duplicate the rules here.
- Stage 1 ([`01_io-patterns.md`](01_io-patterns.md)) → stage 4
  ([`04_repro-clew.md`](04_repro-clew.md)) are the preconditions: the
  files this stage names + numbers are the outputs of stages 1 + 3 and
  the evidence of stage 4.

See also: [`00_playbook.md`](00_playbook.md) for the universal
pre-flight + done-condition; [`SKILL.md`](SKILL.md) for the 5-stage
table this chapter belongs to.
