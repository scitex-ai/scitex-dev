"""Category P: Plotting rules (Phase 2)."""

from ._base import Rule

P001 = Rule(
    id="STX-P001",
    severity="info",
    category="plot",
    message="`ax.plot()` — consider `ax.stx_line()` for automatic CSV data export",
    suggestion="Replace `ax.plot(x, y)` with `ax.stx_line(x, y)` for tracked plotting.",
    requires="scitex",
)

P002 = Rule(
    id="STX-P002",
    severity="info",
    category="plot",
    message="`ax.scatter()` — consider `ax.stx_scatter()` for automatic CSV data export",
    suggestion="Replace `ax.scatter(x, y)` with `ax.stx_scatter(x, y)` for tracked plotting.",
    requires="scitex",
)

P003 = Rule(
    id="STX-P003",
    severity="info",
    category="plot",
    message="`ax.bar()` — consider `ax.stx_bar()` for automatic sample size annotation",
    suggestion="Replace `ax.bar(x, y)` with `ax.stx_bar(x, y)` for tracked plotting.",
    requires="scitex",
)

P004 = Rule(
    id="STX-P004",
    severity="info",
    category="plot",
    message="`plt.show()` is non-reproducible in batch/CI environments",
    suggestion="Remove `plt.show()` — figures are auto-saved in session output directory.",
)

P005 = Rule(
    id="STX-P005",
    severity="info",
    category="plot",
    message="`print()` inside @stx.session — use `logger` for tracked logging",
    suggestion="Replace `print(msg)` with `logger.info(msg)` (injected by @stx.session).",
    requires="scitex",
)

# NOTE: P006-P009 (style-override rules: s=, fontsize=, figsize=, linewidth=)
# are owned by figrecipe and shipped via figrecipe._linter_plugin. They are
# loaded into ALL_RULES through the entry-point plugin loader, not defined
# here, so the rules live in the package whose API they enforce.
