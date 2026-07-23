---
description: |
  [TOPIC] Scientific Figures — typography, encoding, thresholds & report layout
  [DETAILS] Second half of the universal figure standards: axis-label typography and casing, regression/scatter annotation, legends for every encoded channel (colour, marker size), implication thresholds for effect-size/delta panels, chartjunk reduction, PDF-report layout, and the consolidated anti-patterns list. Read alongside [`01_figures_01_standards.md`](01_figures_01_standards.md), which carries the comparison/scale/colour-map rules those anti-patterns refer to.
tags: [scitex-scientific-figures-standards]
---

# Scientific Figure Standards — typography, encoding & report layout

Continuation of [`01_figures_01_standards.md`](01_figures_01_standards.md)
(comparison rules, colour maps, robust limits). These are the typography,
per-channel encoding, threshold, chartjunk, PDF-layout, and anti-pattern rules.

## Axis Labels & Typography

- **Capital first letter + clear words**: "Phase Frequency (Hz)", not "phase freq".
  This applies to **all** text — legends, categorical tick labels, annotations,
  and panel titles — not only axis labels ("Density", "Preictal", not "density").
- **Italicize mathematical & statistical symbols** — variables, *R²*, *p*, *n*,
  *β* are math, not prose; set them in italic.
- **Titles: the minimal sufficient identifier**, short and clear (e.g. "Patient
  #10", not a sentence). An overlong title that is hard to parse is a defect.
- **Abbreviate consistently or not at all.** If space forces abbreviation,
  abbreviate *both* paired axes the same way — "Amp. Freq. (Hz)" must pair with
  "Phase Freq. (Hz)"; never abbreviate one axis and spell out the other.
- **Use an en-dash (–) for numeric ranges**, not a hyphen or double-hyphen:
  "10–20 Hz", not "10--20 Hz".
- A per-tile / per-window **title shows the actual range it covers**, not just a
  single offset.

## Regression & Scatter Plots

- **Fit line in a neutral colour (black)** so it stands out from the (often
  coloured) data points.
- **Show the fitted equation** — e.g. `y = ax + b` with the actual coefficients.
- **Put the fit statistics (*R²*, *p*, *n*) next to the regression line**, not
  floating in a corner, with the symbols *italicized*.

## Encoded Channels Need a Legend

Any visual channel that carries a quantity must be decodable:

- **Colour → colorbar** (with units; see Color Maps above).
- **Marker size → a size legend.** If bubble size/area encodes a value, show a
  size legend and say in the caption what size means. A bubble chart whose size
  is unexplained is unreadable.

## Effect Sizes Need Implication Thresholds

A magnitude only means something against a reference. Whenever a figure shows an
effect size, a delta, or a difference, draw the threshold(s) that make it
interpretable:

- **Significance / clinical cutoff** — a horizontal line or shaded band at the
  decision boundary, so the reader sees which points cross it.
- **Effect-size reference lines** — small / medium / large markers where
  applicable (e.g. Cohen's *d* = 0.2 / 0.5 / 0.8).
- **A "meaningful difference" line on delta plots** — a Δ is only actionable
  beside the Δ that matters.

A bare effect-size or delta with no threshold leaves the "so what" unstated.

## Reduce Chartjunk

- **Hide spines / ticks that don't aid reading.** On a heatmap / image /
  comodulogram panel the box spines and redundant ticks add nothing — hide them
  and let the colorbar + axis labels carry the information.

## PDF Report Layout

When generating multi-figure scientific reports as a PDF:

- **Bookmarks**: every section navigable via PDF outline (use `fpdf2`'s
  `start_section()` or post-hoc `pikepdf` outline editing).
- **Size**: target under 10MB for email; reduce DPI to 100–150 or compress
  with `ghostscript` if needed.
- **Aspect ratios**: preserve the original aspect ratio of every embedded
  figure — read image dimensions before laying out.
- **Captions**: every figure has a numbered caption (Figure N: …) with a
  one-sentence description.
- **Page numbers** included.

## Anti-patterns

- Two heatmaps with different `vmin`/`vmax` "for clarity" — defeats the
  comparison.
- A diverging colormap centered at the data mean instead of zero — implies
  asymmetry where there isn't any.
- One figure per PDF page for a 50-figure report — unreadable, unprintable.
- Using `jet` "because it's colorful".
- A regression panel with the fit line in a data colour, no equation, and the
  stats floating in a corner instead of beside the line.
- A bubble chart with no size legend — the reader can't decode what size means.
- A panel that doesn't say whether it's pooled or a single subject, or omits `n`.
- Lowercase axis / legend / category labels ("density", "preictal") — capitalize
  the first letter.
- Box spines + redundant ticks left on a heatmap, adding visual noise.
- A long-tailed heatmap / histogram scaled to raw min–max so the bulk is
  squashed into a sliver — use percentile (1st–99th) limits and mark the
  clipped tail.
- An effect-size / Δ panel with no implication threshold — the reader can't
  tell which values are meaningful.
- A colormap panel with no colorbar / scalebar — colour with no visible scale
  is undecodable.
