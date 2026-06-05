---
description: |
  [TOPIC] Paper-writing — thin reference leaf pointing to scitex-writer's canonical paper-writing skill set.
  [DETAILS] The agent ↔ user paper-writing FLOW (figure-first communication protocol, per-section flow scaffolds, manuscript-workflow conventions) is owned by scitex-writer's `_skills/scitex-writer/` series (leaves 14, 30–36, 40–43). This `scientific/07_paper-writing.md` leaf is intentionally a 30-line redirect so a reader who arrives at scitex-dev's `scientific/` looking for paper-writing flow gets pointed at the right place without scitex-dev shadowing the canonical content. Universal scientific-figure LOGIC + ORDERING rules (data progression, representative-before-grouped, results-order = figure-order, no-undefined-before-use, fixed representative subject, consistent color scheme) live in this directory as the tool-agnostic principles — see `01_figures_02_logic-and-ordering.md`. Honest-grounding norms from `06_scitexification/00_playbook.md` carry over.
tags: [scitex-scientific-paper-writing-reference]
requires:
  # Loading this reference leaf surfaces the canonical scitex-writer skill
  # plus the figure-logic / scitexify companions that the writer flow
  # depends on. The actual paper-writing content lives in scitex-writer;
  # this leaf is a pointer.
  - scitex-writer
---

# Paper-writing — reference

This is a thin reference leaf. The canonical paper-writing FLOW
content — the agent ↔ user agreement protocol, the figure-first
communication pattern (`Fig N` → `a./b./c.` panel agreement), the
per-section flow scaffolds, and the manuscript-workflow conventions
(including the `<proj-root>/paper -> .scitex/writer` symlink) — lives
in **scitex-writer** and is intentionally not duplicated here.

## Where the content lives

Load `scitex-writer` (or read directly from
`~/.claude/skills/scitex/scitex-writer/`) and consult:

- `40_paper-writing-protocol.md` — top-level agent ↔ user
  paper-writing umbrella protocol. Composition with the existing
  per-section templates + the in-flight discipline. The "write the
  paper WHILE running experiments" framing.
- `41_figure-first-communication.md` — the figure-first agreement
  protocol (`Fig N. <title>` then `a./b./c.` panels with intent),
  load-bearing for the rest of the flow. Pairs with
  [`01_figures_02_logic-and-ordering.md`](01_figures_02_logic-and-ordering.md)
  (universal LOGIC rules) which lives here in `scientific/`.
- `30_writing-abstract.md` / `31_writing-introduction.md` /
  `32_writing-methods.md` / `33_writing-discussion.md` /
  `36_writing-results.md` — per-section templates (operator-iterated
  voice).
- `26_writing-during-exploration.md` — in-flight discipline for
  drafting prose while experiments are still running (`\vclaim{}` /
  `\placeholder{}` / `\hlref{XXX}` / pre-submission grep gate).
- `14_manuscript-workflow.md` — end-to-end CLI workflow + the
  `<proj-root>/paper -> .scitex/writer` symlink convention.

## What stays in `scientific/`

The genuinely **tool-agnostic** scientific-reasoning rules — applicable
to a paper, a poster, a talk, an internal report — stay here:

- [`01_figures_01_standards.md`](01_figures_01_standards.md) — RENDERING
  standards (color scale, aligned axes, multi-panel layout, color maps,
  PDF report layout).
- [`01_figures_02_logic-and-ordering.md`](01_figures_02_logic-and-ordering.md)
  — LOGIC + ORDERING (data progression, representative-before-grouped,
  results-order = figure-order, no-undefined-before-use, fixed
  representative subject, consistent color scheme across the whole
  paper).
- [`00_planning_01_hypotheses-agreement.md`](00_planning_01_hypotheses-agreement.md)
  — hypothesis-list agreement BEFORE the analysis.
- [`06_scitexification/00_playbook.md`](06_scitexification/00_playbook.md)
  — universal honest-grounding norm (silent-attrition antipattern,
  three-state-collapse, separation-of-concerns rule). Manuscript claims
  inherit this — every paper-layer claim ladders back to a
  scitex-clew-registered claim.

## Why the split

scitex-writer is the **tool**. The flow content there speaks LaTeX,
BibTeX, `\vclaim{}`, the `caption_and_media/` directory layout, the
manuscript-workflow CLI. Loading scitex-writer is the right path for
anyone actually writing the manuscript.

`scientific/` carries the **tool-agnostic** layer: the principles that
hold even if you abandon scitex-writer for Overleaf or hand-typeset
the paper. A reader doing a poster or a talk loads only the
`scientific/` layer; they don't need the LaTeX surface.

This is the same split scitexification uses: `scientific/06_scitexification`
carries the universal translation act; per-package `SKILL.md` files
carry the package-specific API surface.
