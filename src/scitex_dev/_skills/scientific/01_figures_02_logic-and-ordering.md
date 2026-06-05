---
description: |
  [TOPIC] Scientific figure logic and ordering — universal principles for which figure can be where, in what sequence, with which representative.
  [DETAILS] Library- and tool-agnostic rules for the STORY structure of a paper's figures (and tables, and result-section paragraphs). Pairs with `01_figures_01_standards.md` (which covers RENDERING — color scale, aligned axes, layout — for an individual figure); this leaf covers ORDERING and DEPENDENCY between figures and across the manuscript. Six principles: (1) data progression (raw → analyzed), (2) representative-before-grouped, (3) results-section order MUST equal figure order, (4) no-undefined-before-use (figures follow a logical dependency graph — a panel can only appear once its terms are defined), (5) one fixed representative subject across all representative panels (raises reliability, prevents cherry-picking impressions), (6) consistent color scheme across the whole paper (every grouping → same color in every figure it appears in). V0 SKELETON awaiting operator iteration — the principles are firm but the worked-example phrasing and detail are seeded by the operator and meant to be refined by him.
tags: [scitex-scientific-figures-logic-and-ordering]
---

<!--
v0 skeleton status:
  - Principles 1-6 captured from operator's seed messages (msg 9220, 9221,
    9226, 9227). Phrasing is the agent's; the substance is the operator's.
  - The NeuroVista cohort-overview worked example below is the operator's
    own concrete illustration; keep his rationale intact when iterating.
  - Pair with `scitex-writer/_skills/scitex-writer/41_figure-first-communication.md`
    (the agreement protocol that operationalises this logic). This leaf
    is the WHY; that leaf is the HOW.
-->

# Scientific Figure Logic and Ordering

`pip install scitex-dev` (no extras needed for the skill itself).

Library- and tool-agnostic rules for the **story structure** of a paper's
figures and the ordering constraint they impose on the results section.
Pairs with [`01_figures_01_standards.md`](01_figures_01_standards.md) —
that leaf covers how to *render* an individual figure (color scale,
aligned axes, layout); this leaf covers which figure can be *where*, in
what *sequence*, and *with which representative*.

## When to load

Load when **any** of the following is true:

- You are about to decide what `Fig 1` should be for a paper, talk, or
  poster — and you have more than one candidate.
- You are about to re-order the figures of a near-final manuscript and
  want to know whether the dependency graph allows the new order.
- You are reviewing a draft and notice a figure uses a term that
  hasn't been defined yet.
- You are choosing colours for groups (treatment / control / cohort)
  and want them to read consistently across every figure in the
  paper.
- You are agreeing on the figure list with the user (via the
  scitex-writer figure-first agreement protocol — see
  [Related](#related)) and need the constraint set that determines
  what figure CAN be `Fig N`.

## The six principles

### 1. Data progression — raw before analyzed

When the paper shows both the raw signal (or the raw sample, the
raw image, the raw recording) and an analyzed/derived version of it,
the raw view comes FIRST. The reader must see what the input looks
like before they can judge what the analysis pulled out of it.

Implication: if `Fig 2` is "spectrogram of channel C in condition X",
then a panel showing the **raw trace of channel C in condition X**
belongs earlier — typically inside `Fig 1` or as an inset / sister
panel of `Fig 2`. Never show the analyzed output without the raw input
somewhere upstream.

This applies recursively: if a downstream figure shows a model
prediction, the inputs the model consumed must appear upstream of it.

### 2. Representative-before-grouped

For any quantity that has both a single-subject representative panel
AND an across-subjects grouped (aggregate / mean / boxplot) panel, the
representative comes FIRST.

Why: the grouped panel is uninterpretable until the reader knows what
a single instance of the thing looks like. "Mean ± SEM across 9
subjects" reads as a number; "one subject's seizure trace with the
extracted feature highlighted, then mean ± SEM across the 9 subjects"
reads as a finding.

The pair (representative, grouped) is often the cleanest atomic story
unit in a results paragraph. Stage 2 of the
[scitexify universal playbook](06_scitexification/00_playbook.md)
gives you the artefact discipline; this principle gives you the
presentation order.

### 3. Results-section order MUST equal figure order

The results section is read top-to-bottom; figures are referenced
top-to-bottom; the figure NUMBERS are top-to-bottom. These three
orders are not three orders — they are one order, replicated.

Implication: if the results section's paragraphs were ordered
(P1: cohort, P2: feature extraction, P3: classifier, P4: across-subjects
generalisation), the figures must be ordered
(Fig 1: cohort, Fig 2: feature extraction, Fig 3: classifier,
Fig 4: across-subjects generalisation). Mismatching them is a
rewrite-everything bug.

The
[scitex-writer figure-first agreement protocol](#related)
exists in part to make this constraint visible before either prose or
plot code is written. Agree on the figure list with the user FIRST;
the results-section paragraph order follows mechanically.

### 4. No-undefined-before-use — figures follow a dependency graph

**A panel can only appear once its terms have been defined.** Terms
include: cohort identifiers (the `n_sz` / `n_ic` / `n_months` style
counts), variable names (`α` / `β` / `γ` band names; condition
acronyms; channel-grid labels), measurement procedures, baselines.

A figure that uses term `X` before term `X` is defined either in
prose or in an earlier figure is **undefined-before-use** — a
strict-order violation that forces the reader to scroll forward to
disambiguate, which they won't.

Practically: figures form a **dependency graph**. Each figure's
definition set requires that some upstream figure (or upstream
methods / introduction prose) has introduced the term. The figure
ORDER is constrained by the topological sort of that graph. There
may be more than one valid topological sort; pick the one that
reads as a story.

This is the constraint that determines what CAN be `Fig 1`.

### Worked example (operator seed)

```
## Fig 1. NeuroVista cohort overview
a. 9 patients: n_sz / n_ic / n_months (post-day-100)
b. α/β/γ pattern-classification labels
c. 16ch grid + Karoly-9 extraction rationale
```

> Operator's rationale (paraphrased): you cannot make THIS `Fig 1`
> unless `n_sz` / `n_ic` / `IC` and the `α` / `β` / `γ`
> pathological-channel definitions have been introduced. So the
> definitional dependency graph determines what CAN be `Fig 1`. In
> this case, the `Fig 1` itself BECOMES the introducer for those
> terms — panel `a.` defines `n_sz` / `n_ic` / `n_months`, panel
> `b.` introduces the `α` / `β` / `γ` labelling, panel `c.`
> introduces the channel grid and the Karoly-9 extraction. That
> is *why* it's `Fig 1`: because if it isn't, every later figure
> would reference undefined terms.

Use the panel format above as the canonical shape for figure
agreement: `## Fig N. <title>` then `a./b./c.` panels with a
one-sentence definitional or comparison intent each. (Lowercase
panel letters; the
[scitex-writer figure-first agreement protocol](#related)
uses this exact shape so the agreement markdown copy-pastes into
FigRecipe filenames + manuscript LaTeX + SI index without
translation.)

### 5. One fixed representative subject across ALL representative panels

When the paper carries multiple representative-subject panels (one in
`Fig 1`, one in `Fig 2`, possibly more), **the same subject is used
every time** unless there is a stated scientific reason to switch.

Why two pieces:

- **Reliability.** A reader who recognises Subject 03 in `Fig 1`
  recognises Subject 03 in `Fig 2`. The same person's data tells a
  coherent story; the same person's data with a switch in `Fig 2`
  reads as a hidden mystery.
- **Anti-cherry-picking impression.** If `Fig 1.a` shows Subject 03,
  `Fig 2.a` shows Subject 07, and `Fig 3.a` shows Subject 11, a
  reasonable reader assumes the panels were selected to make each
  point land. Fixing one representative subject across all
  representative panels removes that suspicion at the structural
  level.

Pick the representative subject during stage 1 of paper writing,
document the choice (e.g. `## Fig 1.a — Subject S03; same subject
used in Fig 2.a, Fig 3.a`), and stick to it.

If a particular panel needs a different representative for a stated
reason (e.g. only Subject S07 has both modalities recorded), call out
the switch in the figure caption and the results-paragraph sentence
that references the panel.

### 6. Consistent color scheme across the whole paper

Every grouping that recurs across figures (treatment / control,
seizure / interictal, cohort A / cohort B, condition X / condition Y)
**uses the SAME colour in every figure it appears in**.

Why: cross-figure consistency turns colour into a re-usable label.
Once the reader learns "treatment is blue, control is grey" in
`Fig 1`, every later figure with those groups becomes interpretable
without re-reading the legend.

For per-figure rendering details (which colour MAP to use for
diverging vs sequential vs categorical data, why not `jet`, etc.)
see [`01_figures_01_standards.md` § Color Maps](01_figures_01_standards.md#color-maps).
This leaf adds the cross-figure CONSISTENCY rule on top.

### 7. Config-driven figure parameters (cross-figure)

Every figure parameter that recurs across figures — the colour
assignment from §6, the fixed representative subject ID from §5, any
group → label mapping, any per-cohort baseline value — **lives in
project config**, not hardcoded in plot scripts.

Concretely: a scitexified project carries a directory like
`~/proj/<project>/configs/*.yaml` (or `<proj-root>/config/*.yaml`,
matching `02_research-project_03_project-structure-config-and-data.md`'s
config tree) with files such as:

```yaml
# config/COLORS.yaml
groups:
  seizure: "#D62728"        # red
  interictal: "#1F77B4"     # blue
  baseline: "#7F7F7F"       # grey

# config/REPRESENTATIVE.yaml
subject_id: "Pat10"         # used in every Fig N.a representative panel
                             # see §5 — switch only with stated reason
```

Every figure script (`plot_fig1.py`, `plot_fig2.py`, ...) reads from
these files at the top of the script and uses the resolved values.

Why:

- **Consistency by construction.** §5 and §6 become impossible to
  violate accidentally — there is no "the colour I typed in panel
  3.b" because the colour is never typed in panel 3.b.
- **Swap-once.** Renaming a group, switching the representative
  subject, retuning a palette are one-line edits to the config.
  Every figure picks up the change on next render. No per-script
  search-and-replace.
- **Auditable.** A reviewer reading the figure scripts sees the
  config reference (`CONFIG.groups.seizure`), not a magic hex
  string — and can trace back to the single source.
- **Provenance.** The config file enters the DAG with the
  manuscript (under scitex-clew session hashes), so the colour /
  representative-subject choice is itself a registered claim.

This generalises §5 (representative subject) and §6 (colour scheme)
into a single discipline: **cross-figure parameters live in config,
not in scripts.**

### 8. Visual encoding channels — dimensionality of representation

A figure can encode only a finite number of **data dimensions** in a
single panel. Each dimension maps to a **visual channel**, and the
channels have a precedence (some channels carry information more
reliably than others). The decision "how do I represent N data
elements in one figure?" is the decision "which N channels do I use,
in what precedence order?"

This is classic data-viz theory (Bertin's *visual variables*) framed
for scientific figures.

#### The precedence ladder

| Channel | What it encodes | Precedence |
|---|---|---|
| **Position on an axis** (1D) | A single value. | Strongest — the eye reads position accurately. |
| **Position in 2D (x, y)** | Two values (or one as `x` and one as `y`). | Next strongest — joint position is the basis of every scatter, every line plot, every heatmap. |
| **Colour** | A third value (continuous → colormap, categorical → palette). | Next — colour reads as ordinal / categorical more reliably than as exact value. |
| **Spatial layout / faceting** | A discrete grouping variable (one panel per cohort, one row per condition). | Used when colour is exhausted or the comparison demands separate panels. |
| **3D depth** | A fourth continuous value. | Weakest — depth perception is fragile in 2D media; use sparingly. |

#### "How to represent N elements" — the enumeration

- **1 element** → position along one axis (a bar, a single value on
  a number line).
- **2 elements** → 2D position (a scatter point, a heatmap cell, an
  image pixel — `(x, y)` jointly).
- **3 elements** → 2D position + one more channel: usually
  **colour** (`(x, y, c)` → a coloured scatter; a heatmap value);
  occasionally **3D** (`(x, y, z)` axes) or **faceting** (`(x, y)`
  per panel of a grid that varies a third grouping variable).
- **4 elements** → 2D position + colour + size (marker size scales
  with the fourth value); OR 2D position + colour + facet rows /
  facet columns.
- **5+ elements** → either multi-panel composition (compose more
  than one figure; the multi-panel rules in
  [§3](#3-results-section-order-must-equal-figure-order) and
  [§4](#4-no-undefined-before-use--figures-follow-a-dependency-graph)
  apply) or dimensionality-reduction first (PCA / UMAP / t-SNE; the
  reduced 2D representation becomes the position channel and the
  number of "elements" drops back to 2-3).

#### The precedence principle

Use the strongest available channel first. Promoting a value from
"colour" to "position on an axis" (when there's a free axis to spend)
**makes the comparison easier to read**. Demoting a value from
"position" to "colour" (when an axis is needed for something more
load-bearing) **trades reading accuracy for compactness**.

The decision is per-panel: each panel `a./b./c.` makes its own
encoding choice based on what it's trying to show. The agreement
artefact from
`~/.claude/skills/scitex/scitex-writer/41_figure-first-communication.md`
(step 2: per-panel intent sentence) is where this decision is
recorded — "panel `a.` shows X vs Y as a 2D scatter coloured by
cohort" makes the encoding explicit.

#### When you've run out of channels

If a panel needs to encode more data dimensions than the available
channels permit, the answer is **split the panel** (per
[§3](#3-results-section-order-must-equal-figure-order) on
results-order = figure-order) or **summarise first** (per
[§2](#2-representative-before-grouped) representative-before-grouped:
show one representative slice as a separate panel, then the aggregate
over the missing dimension).

Trying to cram all dimensions into one panel via novel encodings (a
glyph with seven properties, a 3D plot with colour and size and
animation) almost always produces a panel the reader cannot decode.

## Honest grounding (carryover from scitexification)

These principles compose with the honest-grounding norm from
[`06_scitexification/00_playbook.md`](06_scitexification/00_playbook.md):

- If a planned figure can't be made (data didn't pan out, the panel
  is ambiguous), **it does not silently disappear from the figure
  list.** It is either kept in the manuscript with explicit text
  ("Fig 3 was planned but the X measurement was inconclusive; see
  SI methods §M.4") OR moved to supplementary materials with the
  same disclosure. **Silent omission** of a planned figure is the
  same silent-attrition bug at the figure-list layer.
- The figure-LIST agreement (scitex-writer leaf 41) is the surface
  that makes silent omission detectable: a planned figure that's
  no longer present in the final manuscript is visible by diffing
  against the agreed list.

## Anti-patterns

- "Let me put the most impressive figure first" → violates #4. The
  most impressive figure usually depends on definitions established
  earlier; making it `Fig 1` forces the reader to chase forward
  references.
- Showing the aggregate plot before the single-subject example → #2.
- Using one subject for `Fig 1`'s representative panel and a
  different subject for `Fig 2`'s representative panel without
  explanation → #5.
- "Treatment is blue in `Fig 1`, then orange in `Fig 3` because
  orange looks nicer here" → #6.
- A single panel using six visual channels at once (3D + colour + size
  + marker shape + edge style + opacity) to encode "everything we
  measured" → violates #8. Split the panel; the reader cannot
  decode six channels.
- Re-ordering the results section without re-numbering the figures
  (or vice versa) → #3.
- Showing a derived/analyzed quantity without ever showing the raw
  signal it came from → #1.

## Related

- [`01_figures_01_standards.md`](01_figures_01_standards.md) — universal
  scientific-figure RENDERING standards (color scale, aligned axes,
  layout, color maps). This leaf adds the LOGIC + ORDERING dimension on
  top.
- [`06_scitexification/00_playbook.md`](06_scitexification/00_playbook.md)
  — universal scientific-integrity norm (honest source-grounding,
  silent-attrition antipattern). The figure-list integrity rule above
  is the figure-layer specialisation.
- `~/.claude/skills/scitex/scitex-writer/_skills/scitex-writer/41_figure-first-communication.md`
  *(to-be-landed)* — the agent↔user agreement PROTOCOL that
  operationalises this logic (Fig N → `a./b./c.` panel agreement,
  before any plot code or prose). This leaf is the WHY; that leaf is
  the HOW.
- [`00_planning_01_hypotheses-agreement.md`](00_planning_01_hypotheses-agreement.md)
  — hypothesis-list agreement BEFORE the analysis. Hypotheses
  constrain which figures the paper must carry; the figure-logic
  above constrains how those figures must be ordered.
