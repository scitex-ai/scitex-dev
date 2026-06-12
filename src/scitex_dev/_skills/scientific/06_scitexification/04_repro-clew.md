---
description: |
  [TOPIC] Scitexification Stage 4 — Reproducibility via Clew claims
  [DETAILS] Stage 4 of the 5-stage scitexification arc: final-mile
  assertions ("accuracy was X%", "effect size was Y") become registered
  Clew **claims**, each evidence-bound to the file that produced it via
  `scitex_clew.register_claim(...)`. The downstream submission JSON
  (`claims.json` / `submission.json`) is COMPOSED by iterating
  registered claims through `scitex_clew.list_claims()` +
  `scitex_clew.verify_claim()` and filtering to `source_verified=True`
  — NEVER hand-written. Once stage 4 lands, every numeric claim in the
  paper has a verifiable lineage back to the file (and the stage-1 +
  stage-2 + stage-3 DAG that produced it).
tags: [scitexification, scitexification-repro-clew]
---

<!--
Status: STUB — landed alongside SKILL.md so the umbrella's
`04_repro-clew.md` link in the "5-stage table" resolves to a real file
instead of a 404. Full content (the `register_claim` signature, the
`source` / `evidence` field conventions, the `verify_claim` predicate
contract, the `list_claims` filtering recipe, and the
`submission.json` composition idiom) will land in a follow-up PR
scoped to this chapter only — see #119 for the five-chapter rollout
plan. Cross-package details (the full `scitex_clew` public surface)
live in `scitex-clew`'s own SKILL.md per the scitexification umbrella's
delegation convention.
-->

# Stage 4 — Reproducibility via Clew claims

The accountability step. Every numeric assertion the paper makes
("accuracy was 92.3%", "effect size was 0.41", "the model converged in
14 epochs") becomes a registered Clew claim with an `evidence:` field
pointing to the file that produced it (a `stx.io.save` output from
stage 1, a figure from stage 3, a CSV from a downstream analysis).
The submission JSON the venue wants is then COMPOSED by walking the
registered claims via `scitex_clew.list_claims()` + filtering to
`verify_claim(...)._source_verified is True` — not hand-edited.

> **What changes**: every place a number is assembled into a
> downstream submission JSON / report.
> **What stays the same**: what you are claiming, your numbers.

## Translation table (sketch)

| Original | SciTeX equivalent |
|---|---|
| Hand-edited `claims.json` / `submission.json` | `scitex_clew.list_claims()` → filter → emit |
| `{"claim": "acc=92.3%", "source": "I ran step_3.py"}` | `scitex_clew.register_claim(name="acc", value=0.923, source=PATH_TO_STAGE1_OUTPUT)` |
| Manual cross-check of numbers between paper and code | `scitex_clew.verify_claim(name)` returns the source file hash + recomputed value |

Full inventory and the corner cases (multi-source claims, derived
claims, the `claim_set` / `claim_group` aggregation pattern, partial
verification on incomplete runs) are pending — see the **Status** note
at the top of this file.

## Follow-up

- The full `scitex_clew` public surface (`register_claim`,
  `list_claims`, `verify_claim`, the underlying `_tracker` / `_observer`
  wiring) lives in `scitex-clew`'s own SKILL.md.
- Stage 1 ([`01_io-patterns.md`](01_io-patterns.md)) is the precondition
  — without `stx.io.save` outputs there are no files to evidence-bind.
- Stage 5 ([`05_naming-and-numbering.md`](05_naming-and-numbering.md))
  gives the evidence paths their canonical (zero-filled, sortable)
  form so a `claims.json` is stable across re-runs.

See also: [`00_playbook.md`](00_playbook.md) for the universal
pre-flight + done-condition + the **honest source-grounding** norm
that this stage's `verify_claim` enforces; [`SKILL.md`](SKILL.md) for
the 5-stage table this chapter belongs to. The clew-specific
specialisations in `scientific/04_clew_*.md` compose ON TOP of this
chapter for clew-tracked-translation workflows.
