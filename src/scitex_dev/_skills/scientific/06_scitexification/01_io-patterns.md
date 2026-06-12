---
description: |
  [TOPIC] Scitexification Stage 1 — I/O patterns
  [DETAILS] Stage 1 of the 5-stage scitexification arc: every `open()` /
  `np.load` / `pd.read_csv` / `pickle.load` becomes `stx.io.load(...)`;
  every `np.save` / `pickle.dump` / `df.to_csv` becomes `stx.io.save(...,
  symlink_to=...)`. Once both halves are mechanically swapped, DAG
  composition (output of step N is the input of step N+1) becomes
  visible at the filesystem level — which is the precondition every
  later stage builds on (config wins at stage 2, the figure DAG hooks
  at stage 3, evidence-binding at stage 4, naming/numbering at stage 5).
tags: [scitexification, scitexification-io]
---

<!--
Status: STUB — landed alongside SKILL.md so the umbrella's `01_io-patterns.md`
link in the "5-stage table" resolves to a real file instead of a 404.
Full content (the complete inventory of `open()` / pd / np / pickle
calls and their `stx.io.{load,save}` equivalents, including the
`symlink_to=` DAG-binding idiom and the corner cases around `mode="ab"`,
`dtype="object"` pickles, and on-disk format auto-detection) will land
in a follow-up PR scoped to this chapter only — see #119 for the
five-chapter rollout plan. Cross-package details (the full `stx.io`
public surface) live in `scitex-io`'s own `SKILL.md` per the
scitexification umbrella's delegation convention.
-->

# Stage 1 — I/O patterns

The mechanical translation step. Every read becomes `stx.io.load(...)`,
every write becomes `stx.io.save(..., symlink_to=...)`. The DAG that
was implicit in the original script (`step_2.py` reads what `step_1.py`
wrote) becomes explicit on disk: each output path appears as a symlink
under the step that consumed it, so a later `find` or a clew lineage
walk can reconstruct the pipeline from the filesystem alone.

> **What changes**: every I/O call site.
> **What stays the same**: your algorithm, your data shapes, your
> business logic. This stage is a mechanical rewrite, not a redesign.

## Translation table (sketch)

| Original | SciTeX equivalent |
|---|---|
| `open(path).read()` / `open(path, "rb").read()` | `stx.io.load(path)` |
| `np.load(path)` / `np.loadtxt(path)` | `stx.io.load(path)` |
| `pd.read_csv(path)` / `pd.read_parquet(path)` | `stx.io.load(path)` |
| `pickle.load(open(path, "rb"))` | `stx.io.load(path)` |
| `np.save(path, arr)` / `np.savetxt(path, arr)` | `stx.io.save(arr, path, symlink_to=...)` |
| `pickle.dump(obj, open(path, "wb"))` | `stx.io.save(obj, path, symlink_to=...)` |
| `df.to_csv(path)` / `df.to_parquet(path)` | `stx.io.save(df, path, symlink_to=...)` |
| `plt.savefig(path)` | `stx.io.save(fig, path, symlink_to=...)` (covered in detail in **Stage 3**) |

Full inventory and the corner-case rules are pending — see the **Status**
note at the top of this file.

## Follow-up

- The full `stx.io.{load, save}` API surface (auto-detected formats,
  `symlink_to=` semantics, `verbose=`, error handling) lives in the
  `scitex-io` package's own SKILL.md — load that companion skill when
  this chapter says \"see scitex-io for the full surface\".
- Stage 2 ([`02_session-config.md`](02_session-config.md)) replaces the
  script's `if __name__ == "__main__":` entry-point with
  `@stx.session.start(...)` so the I/O calls land under a session-managed
  output directory automatically.

See also: [`00_playbook.md`](00_playbook.md) for the universal
pre-flight + done-condition; [`SKILL.md`](SKILL.md) for the 5-stage
table this chapter belongs to.
