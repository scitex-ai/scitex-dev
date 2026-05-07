"""Category ST: Statistics rules (Phase 2)."""

from ._base import Rule

ST001 = Rule(
    id="STX-ST001",
    severity="warning",
    category="stats",
    message="`scipy.stats.ttest_ind()` — use `stx.stats.ttest_ind()` for auto effect size + CI",
    suggestion="Replace with `stx.stats.ttest_ind(a, b)` which includes Cohen's d and CI.",
    requires="scitex",
)

ST002 = Rule(
    id="STX-ST002",
    severity="warning",
    category="stats",
    message="`scipy.stats.mannwhitneyu()` — use `stx.stats.mannwhitneyu()` for auto effect size",
    suggestion="Replace with `stx.stats.mannwhitneyu(a, b)` which includes Cliff's delta.",
    requires="scitex",
)

ST003 = Rule(
    id="STX-ST003",
    severity="warning",
    category="stats",
    message="`scipy.stats.pearsonr()` — use `stx.stats.pearsonr()` for auto CI + power",
    suggestion="Replace with `stx.stats.pearsonr(a, b)` which includes CI and power analysis.",
    requires="scitex",
)

ST004 = Rule(
    id="STX-ST004",
    severity="warning",
    category="stats",
    message="`scipy.stats.f_oneway()` — use `stx.stats.anova_oneway()` for post-hoc + effect sizes",
    suggestion="Replace with `stx.stats.anova_oneway(*groups)` which includes eta-squared.",
    requires="scitex",
)

ST005 = Rule(
    id="STX-ST005",
    severity="warning",
    category="stats",
    message="`scipy.stats.wilcoxon()` — use `stx.stats.wilcoxon()` for auto effect size",
    suggestion="Replace with `stx.stats.wilcoxon(a, b)` which includes effect size and CI.",
    requires="scitex",
)

ST006 = Rule(
    id="STX-ST006",
    severity="warning",
    category="stats",
    message="`scipy.stats.kruskal()` — use `stx.stats.kruskal()` for post-hoc + effect sizes",
    suggestion="Replace with `stx.stats.kruskal(*groups)` which includes epsilon-squared.",
    requires="scitex",
)
