---
description: |
  [TOPIC] Scitexification — done condition, forbidden acts, on-failure.
  [DETAILS] The universal completion criteria (runs end-to-end, DAG
  terminus is a file, entry-count equals goal-count, every entry
  grounded-or-null-with-reason, pre-flight still green), the universal
  forbidden floor (silent omission, hand-written claims JSON,
  plt.savefig, editing $SRC, heavy data under ~, mixing path idioms),
  and the three-iterations-then-null on-failure rule. Moved verbatim
  out of 00_playbook.md.
tags: [scitexification, scitexification-done-condition]
---

## Done condition (universal)

A scitexification is complete when ALL of:

1. The project under `$WORKDIR` runs end-to-end. (`make solve` or
   equivalent exits 0.)
2. The DAG terminus exists and is a file — `claims.json` is the
   canonical default, but the playbook is agnostic to the schema.
3. The count of entries at the terminus equals the count of
   `$QUESTIONS_OR_GOALS` items (or the project's stated goal-count if
   unstructured).
4. Every entry has either `answer != null` with an evidence pointer, OR
   `answer == null` with a non-empty `reason`. Silent omission fails.
5. The five pre-flight items are still green (the project hasn't drifted
   during translation).

If any of (1)–(5) fail, the project is partially scitexified — that's a
valid state, but it should be recorded explicitly (e.g., README note,
issue) rather than presented as done.

## Forbidden (at the universal layer)

These are forbidden regardless of which downstream evaluator the project
feeds. Experiment-specific layers add more (e.g., an evaluator-blind
harness forbids reading the held-out answers); this list is the universal
floor.

- Silent omission of an ungroundable claim (see Honest Grounding).
- Hand-writing the results / claims JSON instead of composing it from
  registered claims via the appropriate API (e.g. iterate over
  registered claims via the project's claim-store API — `scitex_clew.
  list_claims()` for clew-tracked projects, the equivalent claim-store
  iterator for any other evaluator). Hand-written JSON drifts from the
  evidence-binding the registered claims actually carry.
- `matplotlib.pyplot.savefig(...)` directly — figures must enter the
  DAG via `stx.io.save`.
- Modifying the source-of-translation in `$SRC` (read-only by
  convention; copy first, transform the copy).
- Heavy data anywhere under `~` on HPC nodes (capacity quotas; use
  `$WORKDIR` or the cluster's scratch tier).
- Mixing `os.path.join(...)` and `CONFIG.PATH.<KEY>` for the same path
  inside the same script. Pick one per call site.

## On failure

Iterate at most **three times per stage**. If still blocked:

1. Record the blocker on the affected claim(s) as `answer: null` +
   `reason: <short>`.
2. Move on. A partially scitexified project with explicit nulls is more
   valuable than a fully scitexified project that took shortcuts.
3. Open an issue / leave a README note for the reviewer.

The honest-grounding principle gives you permission to ship the partial
result without over-fitting it.

## What this skill does NOT cover

Deliberately out of scope (each has its own dedicated home):

- **The target project structure** (`./config/`, `./data/`,
  `./scripts/`, `./tests/`, Makefile shape) →
  [`../02_research-project_*`](../).
- **Per-package API surface** (full `stx.io` type matrix, FigRecipe
  figure types, scitex-clew primitives) → the per-pkg SKILL.md in
  `~/.claude/skills/scitex/<pkg>/`.
- **Clew-specific / experiment-specific specialisation** (evaluator-blind
  scoring, run dispatch, completion signalling, output/results
  schemas) → [`../04_clew_*`](../). Read those AFTER this playbook
  when working in a clew-tracked flow.
- **The discovery contract** (consumer-side
  `spec.claude.skills: [scitexification]` auto-loading) — tracked
  separately in the SAC ↔ scitex-dev contract thread; not a
  scitexification concern.
