---
description: |
  [TOPIC] Scientific Figures
  [DETAILS] Universal, library-agnostic standards for publication-quality scientific figures — comparison rules (shared colour scale, aligned axes, consistent sample-size annotations), multi-panel layout grids, colour-map selection for categorical vs continuous vs divergent data, typography and legend placement, PDF-report layout (aspect, DPI, bleed), and how to justify breaking each rule. Pairs with `figrecipe/21_scientific-figure-patterns.md` for matplotlib-specific implementation code. Use when designing any figure for a manuscript, poster, or talk; when reviewing a plot for common pitfalls; or when auditing an ecosystem output for scientific rigour.
tags: [scitex-scientific-figures-standards]
---

# Scientific Figure Standards (universal principles)

Library-agnostic rules for scientific figures. For figrecipe/matplotlib code
patterns that implement these rules, see
[../../figrecipe/21_scientific-figure-patterns.md](../../figrecipe/21_scientific-figure-patterns.md).

## Comparison Figures: Mandatory Rules

When comparing conditions (treatment vs control, pre vs post, seizure vs
interictal, etc.):

1. **Same color scale.** Both panels MUST share identical `vmin`/`vmax` so
   intensities are directly comparable. Compute the global min/max across all
   compared conditions BEFORE drawing. For diverging data, use a symmetric
   range (`vabs = max(|vmin|, |vmax|)`, then `vmin=-vabs, vmax=vabs`). If the
   data is heavy-tailed, share a **percentile** range across conditions instead
   of raw min/max — see Robust Limits for Long-Tailed Data.
2. **Aligned axes.** Use shared x and y across the panels. Remove redundant
   tick labels on inner axes — only label the outer edges.
3. **Side-by-side layout.** Place conditions horizontally (or in a small grid)
   for direct visual comparison. Label each panel clearly with the condition
   name.
4. **Same axis range** on x and y, even if one condition has less data — the
   visual comparison is destroyed by mismatched ranges.
5. **One shared colorbar** for the comparison group (not one per panel) so
   the color↔value mapping is unambiguous.

## Representative Examples Must Be Genuinely Typical

A panel labelled "representative" (subject / channel / trial / window) must be
typical of the population it stands for — **not** the strongest or most
photogenic case:

- **Pick by a stated, reproducible criterion** (median effect, nearest-to-mean),
  never by eye, and state that criterion in the caption.
- **Cross-check against the population.** A representative *control* must NOT
  exhibit the *effect* you attribute to the experimental condition; if it does,
  it is not a valid control — re-select it.
- This is the presentation counterpart to the no-synthetic-data policy
  ([01_figures_03](01_figures_03_no-synthetic-data-policy.md)): the data is
  real, but a cherry-picked real example is its own integrity failure.

## State What Each Panel Shows

The reader must never have to guess what the data is:

- **Population / unit** — is it pooled across the cohort, or a single subject /
  channel / trial / window? State it.
- **Sample size** — annotate `n` (e.g. `n = 12 seizures`). A panel with no `n`
  is incomplete.

Put it in the title, a corner annotation, or the caption — consistently across
panels.

## Multi-Panel Layout for Per-Subject Reports

- One subject (patient/participant/sample) per page, with all conditions for
  that subject shown together in a grid (e.g., 2×2 or 2×3).
- NOT one figure per page — that explodes page count and breaks comparison.
- Target page count: ~1–2 pages per subject (e.g., 15–25 pages for 15 subjects).

## Temporal Plots with Shared Time Axis

Stack a heatmap above its averaged profile (or any two plots that share time):
- Use a shared x axis for both panels.
- Allocate vertical space proportionally (e.g., heatmap : line ≈ 3 : 1).
- Hide x tick labels on the upper panel; show only on the bottom panel.

## Binned / Windowed Axes

- **Consistent, explicit half-open interval notation** for bins/windows:
  `[-32, -16)`, `[-16, -1)`, `[0, 2)`, `[2, 10)` — the `[a, b)` form makes the
  bounds and which end is inclusive unambiguous.
- **Show the complete series of windows** — don't drop intermediate bins; a gap
  in the sequence misleads the reader.

## Color Maps

- **Diverging data** (positive/negative around 0): `RdBu_r` or `coolwarm`.
- **Sequential data** (0 → max): `viridis` or `plasma`.
- **Never use `jet`** — perceptually non-uniform; misrepresents data.
- **A colorbar (a.k.a. scalebar) is MANDATORY for EVERY colormap, on EVERY
  panel** that encodes a numerical quantity in colour (z-score, rate, effect
  size), with **units in the label**. No exceptions — a numeric colour axis with
  no colorbar is a defect, not a stylistic choice. A shared comparison group
  still shows one colorbar; no panel may rely on colour with no scale visible.

## Robust Limits for Long-Tailed Data

A few extreme values must not dictate the axis / colour range. A long tail
stretches the scale until the bulk of the data is squashed into a sliver and the
real differences — the point of the figure — become invisible.

- **Set limits by percentiles, not raw min/max**, when the data is heavy-tailed:
  e.g. `vmin, vmax = np.percentile(data, [1, 99])`. The informative mass of the
  distribution then fills the range and differences become legible.
- **Disclose the clipping.** Clipping the tail *for visibility* is legitimate;
  hiding that you did it is not. Saturate out-of-range values to a distinct
  colour (`cmap.set_over` / `set_under`) and/or state the window in the caption
  ("colour clipped at 1st–99th pct").
- **Keep limits shared for comparisons.** Compute the percentile limits ONCE
  across ALL compared conditions (not per panel) so the panels stay directly
  comparable (see Comparison Figures).

## More figure standards

Typography, regression annotation, per-channel legends, effect-size thresholds,
chartjunk, PDF-report layout, and the consolidated anti-patterns list live in
[01_figures_04_typography-encoding-and-report-layout.md](01_figures_04_typography-encoding-and-report-layout.md).
