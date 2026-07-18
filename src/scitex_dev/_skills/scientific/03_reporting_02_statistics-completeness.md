---
description: |
  [TOPIC] Statistics Completeness Doctrine (the six required elements)
  [DETAILS] Operator-issued hard reporting rule (2026-07-05): every reported
  statistic must carry all six of n / 95% CI / method name / p-value / effect
  size / test statistic, or it is incomplete. Where to put the six when the
  main text is crowded (captions, a dedicated stats table, footnotes), a
  worked example, and how this differs from significance-only reporting.
  Use when writing any Results section, figure caption, or stats table for a
  manuscript or analysis report.
tags: [scitex-scientific-reporting-statistics-completeness]
---

# Statistics Completeness Doctrine

Operator-issued hard rule (2026-07-05, relayed via NeuroVista, adopted
fleet-wide as default). Applies to every reported statistic in a manuscript,
figure, table, or analysis report — not just the "headline" ones.

## The six required elements

A reported statistic is **incomplete** unless all six of the following
appear somewhere the reader can find them:

1. **Sample size** — `n` (or `n` per group/condition).
2. **95% confidence interval** — around the estimate, not just the point
   value.
3. **Statistical method / test name** — e.g. "paired t-test", "Wilcoxon
   signed-rank", "linear mixed model with subject random intercept".
4. **p-value** — exact value (or `p < 0.001` when below display
   precision) — never a bare significance star with no number behind it.
5. **Effect size** — Cohen's d, Cliff's delta, r, eta-squared, odds ratio,
   etc. — whichever is conventional for the test used.
6. **Test statistic** — `t(df)=`, `W=`, `F(df1,df2)=`, `chi2(df)=`, etc.

No stat is complete without all six. A p-value alone, or a p-value plus
effect size but no CI or no `n`, is not sufficient.

## Where the six elements live

The main text does not have to carry all six inline — that would make dense
Results sections unreadable. Push them to wherever fits, as long as they
appear **somewhere the reader can find them without re-running the
analysis**:

- **Panel captions** — for a per-figure statistic, put the six in the
  caption (pairs with
  [01_figures_01_standards.md](01_figures_01_standards.md)'s numbered-caption
  rule).
- **A dedicated stats table** — for a paper reporting many comparisons, one
  table with columns `n | test | statistic | df | p | effect size (95% CI)`
  is often the cleanest home; the main text then just states the direction
  and points at the table.
- **Footnotes** — for a single stat cited in passing in the main text.

What is **not** acceptable: reporting only a p-value or significance star in
the main text with the other five elements nowhere in the manuscript
(including supplement).

## Worked example

Bad (incomplete — only p-value + a vague "effect"):

> Seizure-onset latency was significantly shorter in the treatment group
> (p < 0.05).

Good (all six present, split between text and caption):

> Seizure-onset latency was shorter in the treatment group (Figure 3).

Figure 3 caption:

> **Figure 3: Seizure-onset latency by group.** Treatment (n=42) vs control
> (n=38), Welch's t-test: t(71.2)=3.14, p=0.0024, Cohen's d=0.71 (95% CI
> 0.24–1.18).

Or, for a paper with many comparisons, a stats table row:

| Comparison | n | Test | Statistic | p | Effect size (95% CI) |
|---|---|---|---|---|---|
| Onset latency, treatment vs control | 42 / 38 | Welch's t-test | t(71.2)=3.14 | 0.0024 | d=0.71 (0.24–1.18) |

## Relationship to other doctrine

This is a completeness rule, not a test-choice rule — it does not tell you
*which* test to use (that is a `scitex-stats` API/methodology concern; ping
that package's skill for test selection). It only says: whichever test you
ran, report all six elements about it, somewhere findable.

Pairs with:
- [03_reporting_01_pdf-reports.md](03_reporting_01_pdf-reports.md) — the
  PDF-report Methods/Results section structure this doctrine slots into.
- [01_figures_01_standards.md](01_figures_01_standards.md) — numbered
  caption rule (the six elements are exactly the kind of content a
  caption should carry when the stat is figure-scoped).

## Enforcement status

Doctrine-only today (no automated check). A natural follow-up is a linter
rule (in the `project-type: research` severity family alongside
STX-S001/S002 and the verb-form checks) that flags a reported p-value with
no accompanying n/CI/effect-size/test-statistic nearby — filed separately,
not yet built. Until then, this is enforced by review, not by hook.
