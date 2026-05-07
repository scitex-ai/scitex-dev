"""Category FM: Figure/Millimeter rules."""

from ._base import Rule

FM001 = Rule(
    id="STX-FM001",
    severity="warning",
    category="figure",
    message="`figsize=` detected — inch-based figure sizing is imprecise for publications",
    suggestion=(
        "Use mm-based sizing: `stx.plt.subplots(axes_width_mm=40, axes_height_mm=28)` "
        "or `fig, ax = fr.subplots(axes_width_mm=40, axes_height_mm=28)` for precise control."
    ),
    requires="figrecipe",
)

FM002 = Rule(
    id="STX-FM002",
    severity="warning",
    category="figure",
    message="`tight_layout()` detected — layout is unpredictable across plot types",
    suggestion=(
        "Use mm-based margins: `stx.plt.subplots(margin_left_mm=15, margin_bottom_mm=12)` "
        "for deterministic layout control."
    ),
    requires="figrecipe",
)

FM003 = Rule(
    id="STX-FM003",
    severity="warning",
    category="figure",
    message='`bbox_inches="tight"` detected — can crop important elements unpredictably',
    suggestion=(
        "Use `fr.save(fig, './plot.png')` or `stx.io.save(fig, './plot.png')` "
        "which handle cropping intelligently."
    ),
    requires="figrecipe",
)

FM004 = Rule(
    id="STX-FM004",
    severity="info",
    category="figure",
    message="`constrained_layout=True` detected — conflicts with mm-based layout control",
    suggestion="Use mm-based layout from `stx.plt.subplots()` instead of constrained_layout.",
    requires="figrecipe",
)

FM005 = Rule(
    id="STX-FM005",
    severity="info",
    category="figure",
    message="`subplots_adjust()` with hardcoded fractions — fragile across figure sizes",
    suggestion=(
        "Use mm-based spacing: `stx.plt.subplots(space_w_mm=8, space_h_mm=10)` "
        "for size-independent layout."
    ),
    requires="figrecipe",
)

FM006 = Rule(
    id="STX-FM006",
    severity="info",
    category="figure",
    message="`plt.savefig()` detected — no provenance tracking",
    suggestion=(
        "Use `fr.save(fig, './plot.png')` or `stx.io.save(fig, './plot.png')` "
        "for recipe tracking and provenance."
    ),
    requires="figrecipe",
)

FM007 = Rule(
    id="STX-FM007",
    severity="info",
    category="figure",
    message="`rcParams` direct modification detected — hard to maintain across figures",
    suggestion="Use figrecipe style presets: `fr.load_style('SCITEX')` for consistent styling.",
    requires="figrecipe",
)

FM008 = Rule(
    id="STX-FM008",
    severity="warning",
    category="figure",
    message="`set_size_inches()` detected — bypasses mm-based layout control",
    suggestion=(
        "Use mm-based sizing: `fr.subplots(axes_width_mm=40, axes_height_mm=28)` "
        "or `stx.plt.subplots(axes_width_mm=40, axes_height_mm=28)` for precise control."
    ),
    requires="figrecipe",
)

FM009 = Rule(
    id="STX-FM009",
    severity="warning",
    category="figure",
    message="`ax.set_position()` detected — conflicts with mm-based layout control",
    suggestion=(
        "Use mm-based margins: `fr.subplots(margin_left_mm=15, margin_bottom_mm=12)` "
        "or `stx.plt.subplots(margin_left_mm=15, margin_bottom_mm=12)` for deterministic layout."
    ),
    requires="figrecipe",
)
