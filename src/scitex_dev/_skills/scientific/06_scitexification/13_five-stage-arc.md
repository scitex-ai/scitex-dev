---
description: |
  [TOPIC] Scitexification — the 5-stage translation arc (chapter-linked).
  [DETAILS] The stage-by-stage overview table with per-chapter links:
  stage 1 I/O patterns, stage 2 session + config, stage 3 figrecipe
  figures, stage 4 clew claims + provenance, stage 5 naming + numbering
  — plus the "stages 1+2 = minimum viable, 3/4/5 strictly additive"
  note. Moved verbatim out of SKILL.md.
tags: [scitexification, scitexification-five-stage-arc]
---

## The 5-stage translation arc

Scitexification is **not** a search-and-replace. It is five staged transforms
each of which holds independently:

| Stage | Chapter | What changes | What stays the same |
|---|---|---|---|
| 1 | [01_io-patterns](01_io-patterns.md) | Every `open()` / `np.load` / `pd.read_csv` / `pickle.load` becomes `stx.io.load(...)`; every `np.save` / `pickle.dump` / `df.to_csv` becomes `stx.io.save(..., symlink_to=...)`. DAG composition (output of step N is input of step N+1) becomes visible at the filesystem level. | Your algorithm. Your data shapes. Your business logic. |
| 2 | [02_session-config](02_session-config.md) | The script entry-point becomes `@stx.session.start(...)`; magic numbers and paths become `CONFIG.<KEY>` lookups against `config/*.yaml`; logging becomes the session logger. | Function call structure. Module organization. Test cases. |
| 3 | [03_plt-patterns](03_plt-patterns.md) | Every `plt.savefig(...)` becomes a `stx.io.save(fig, ...)` (so the figure is bound to a session output), and every visual style choice ladders up to figrecipe's publication-quality primitives. | Figure intent (what comparison, what axis labels). What information the figure carries. |
| 4 | [04_repro-clew](04_repro-clew.md) | Final-mile assertions (`accuracy was X%`, `effect size was Y`) become registered Clew **claims**, each evidence-bound to the file that produced it; the results/output JSON is composed by iterating registered claims through `scitex_clew.list_claims()` + `scitex_clew.verify_claim()` and filtering to `source_verified=True`, not hand-written. | What you are claiming. Your numbers. |
| 5 | [05_naming-and-numbering](05_naming-and-numbering.md) | `cnn_v3_final_FIXED2.py` becomes `scripts/03_cnn.py` (zero-filled, sortable, mirrored under `tests/`); IDs and ordinals become readable symlinks per `02_research-project_09`. | Your filenames as a *concept*. The numbers themselves (after zero-fill). |

Doing stages 1+2 alone gets you a *runnable* SciTeX project — stage 3+ are
strictly additive. If a project's deadline is tight, stages 1+2 are the
minimum viable scitexification; stages 3, 4, 5 land in subsequent PRs.
