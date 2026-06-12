---
description: |
  [TOPIC] Scitexification Stage 3 — Figure (plt) patterns
  [DETAILS] Stage 3 of the 5-stage scitexification arc: every
  `plt.savefig(...)` becomes `stx.io.save(fig, ..., symlink_to=...)` so
  the figure is bound to a session output (and joins the DAG built in
  stages 1 + 2); every visual style choice ladders up to figrecipe's
  publication-quality primitives (axis labels, font sizes, colour
  palettes, multi-panel layout). Once stage 3 lands, figures are
  first-class session outputs (not loose `.png`s in the cwd) and can be
  referenced from clew claims at stage 4.
tags: [scitexification, scitexification-plt]
---

<!--
Status: STUB — landed alongside SKILL.md so the umbrella's
`03_plt-patterns.md` link in the "5-stage table" resolves to a real
file instead of a 404. Full content (the inventory of every `plt.*` /
`fig.*` call that benefits from a figrecipe primitive, the
`stx.io.save(fig, ...)` DAG-binding semantics, the multi-panel + legend
+ axis-label conventions, and the figrecipe `recipe` → `figure` flow)
will land in a follow-up PR scoped to this chapter only — see #119 for
the five-chapter rollout plan. Cross-package details (the full
`figrecipe` primitive surface) live in `figrecipe`'s own SKILL.md per
the scitexification umbrella's delegation convention.
-->

# Stage 3 — Figure (plt) patterns

The publication-quality step. `plt.savefig(...)` calls become
`stx.io.save(fig, ..., symlink_to=...)` so the figure lands under the
session-managed output root (DAG-bound, not loose); raw matplotlib calls
that encode visual choices (axis labels, font sizes, colour palettes,
multi-panel grids) get rewritten in figrecipe primitives so the look
matches publication style without bespoke tweaking.

> **What changes**: every `plt.savefig`; every place visual style is
> encoded by hand.
> **What stays the same**: figure intent (what comparison, what axis
> labels), what information the figure carries.

## Translation table (sketch)

| Original | SciTeX equivalent |
|---|---|
| `plt.savefig("fig.png")` | `stx.io.save(fig, "fig.png", symlink_to=...)` |
| `plt.figure(figsize=(8,6)); ax = plt.gca(); ax.set_xlabel(...); ax.set_ylabel(...); plt.tight_layout(); plt.savefig(...)` | `recipe = figrecipe.Recipe(...); fig = recipe.build(...); stx.io.save(fig, ...)` |
| Hand-tuned colour palettes (`plt.cm.viridis(...)`) | `COLORS.<NAME>` (injected via stage 2) or `figrecipe`'s palette primitives |
| Multi-panel layout via `plt.subplot2grid` / `gridspec` | `figrecipe`'s layout primitive (single-call, publication-style) |

Full inventory and the corner cases (animated figures, 3D plots,
seaborn passthrough, MNE/scientific-Python integration) are pending —
see the **Status** note at the top of this file.

## Follow-up

- The full `figrecipe` primitive surface (recipe / palette / layout /
  primitive types — boxplot / violin / scatter / hist / etc.) lives in
  `figrecipe`'s own SKILL.md.
- Stage 1 ([`01_io-patterns.md`](01_io-patterns.md)) supplies the
  `stx.io.save` DAG-binding hook; stage 2
  ([`02_session-config.md`](02_session-config.md)) supplies the
  session-managed output root.
- Stage 4 ([`04_repro-clew.md`](04_repro-clew.md)) references stage-3
  figure paths in registered claims so a clew claim can cite the exact
  figure file that backs it.

See also: [`00_playbook.md`](00_playbook.md) for the universal
pre-flight + done-condition; [`SKILL.md`](SKILL.md) for the 5-stage
table this chapter belongs to.
