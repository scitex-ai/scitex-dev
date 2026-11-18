"""Vocabulary for STX-S008 (``_magic_numbers.py``): which literals are harmless.

Name / keyword / callee sets that separate an analysis parameter from a
structural, presentational or infrastructural literal. Kept apart from the
detector so the policy reads as one list.
"""

import re

__all__ = [
    "_TRIVIAL_NUMBERS",
    "_SKIP_NAMES",
    "_EXEMPT_KEYWORDS",
    "_LAYOUT_UNIT_SUFFIXES",
    "_EXEMPT_CALLEES",
    "_PLOT_MODULES",
    "_PLOT_RECEIVER",
    "_PLOT_METHODS",
    "_STYLE_KEYWORDS",
    "_SEED_KEYWORDS",
    "_SEED_CALLEES",
    "_ENUM_BASES",
]

# Numbers that are structural, not chosen: index/identity/halving.
_TRIVIAL_NUMBERS = frozenset({0, 1, -1, 2})

# Assignment targets that commonly hold non-config numeric values.
_SKIP_NAMES = frozenset(
    {
        "i",
        "j",
        "k",
        "n",
        "x",
        "y",
        "z",
        "idx",
        "count",
        "step",
        "argc",
        "pid",
        "fd",
        "rc",
        "status",
        "exit_code",
        "retval",
        "returncode",
    }
)

# Keyword / parameter names that describe array structure, numeric display,
# or process infrastructure — never an analysis choice.
_EXEMPT_KEYWORDS = frozenset(
    {
        # array structure
        "axis",
        "axes",
        "dim",
        "dims",
        "ndim",
        "ndmin",
        "ddof",
        "shape",
        "newshape",
        # numeric display / serialization
        "decimals",
        "ndigits",
        "precision",
        "indent",
        "width",
        "line_length",
        "linewidth",
        "protocol",
        "compresslevel",
        "compression",
        "compression_opts",
        "maxsplit",
        "stacklevel",
        "buffering",
        # process / IO infrastructure
        "timeout",
        "port",
        "verbose",
        "verbosity",
        "level",
        "n_jobs",
        "max_workers",
        "num_workers",
        "workers",
        "retries",
        "max_retries",
        "chunksize",
        "dpi",
        "code",
        "exit_code",
        "status",
        # presentation / source locations
        "zorder",
        "rotation",
        "line",
        "lineno",
        "line_number",
        "limit",
    }
)

# Keyword names carrying a layout unit (``x_mm=``, ``gap_pt=``) are figure /
# diagram geometry — presentation, not analysis.
_LAYOUT_UNIT_SUFFIXES = ("_mm", "_pt", "_px", "_cm", "_inch", "_inches")

# Calls whose keyword arguments are display/process plumbing.
_EXEMPT_CALLEES = frozenset(
    {
        "head",
        "tail",
        "round",
        "print",
        "format",
        "set_printoptions",
        "set_option",
        "option_context",
        "sleep",
        "exit",
        "basicConfig",
    }
)

# Plotting: every keyword of these calls is presentation (figrecipe's rules).
_PLOT_MODULES = frozenset(
    {"plt", "pyplot", "matplotlib", "mpl", "figrecipe", "fr", "sns", "seaborn"}
)
_PLOT_RECEIVER = re.compile(r"^(ax|axs|axes|fig|figure|panel|cbar|colorbar)\w*$")
_PLOT_METHODS = frozenset(
    {
        "plot",
        "scatter",
        "bar",
        "barh",
        "hist",
        "hist2d",
        "boxplot",
        "violinplot",
        "errorbar",
        "fill",
        "fill_between",
        "fill_betweenx",
        "axhline",
        "axvline",
        "axhspan",
        "axvspan",
        "imshow",
        "pcolormesh",
        "contour",
        "contourf",
        "text",
        "annotate",
        "legend",
        "step",
        "stem",
        "savefig",
        "subplots",
        "subplot",
        "add_subplot",
        "figure",
        "colorbar",
        "tick_params",
        "grid",
        "tight_layout",
        "subplots_adjust",
    }
)

# Matplotlib-style presentation keywords. A call carrying any of them
# (``Line2D(color=..., alpha=0.3)``, ``bbox=dict(facecolor=..., alpha=0.8)``)
# is presentation: its keywords are figrecipe's concern, not config's.
_STYLE_KEYWORDS = frozenset(
    {
        "color",
        "c",
        "colors",
        "facecolor",
        "fc",
        "edgecolor",
        "ec",
        "linewidth",
        "linewidths",
        "lw",
        "linestyle",
        "ls",
        "marker",
        "markersize",
        "ms",
        "markeredgewidth",
        "mew",
        "markeredgecolor",
        "mec",
        "markerfacecolor",
        "mfc",
        "fontsize",
        "labelsize",
        "fontweight",
        "cmap",
        "boxstyle",
        "arrowstyle",
        "hatch",
        "capsize",
        "elinewidth",
        "labelpad",
        "pad",
    }
)

# Seeds are parameters even when they are 0 or 1.
_SEED_KEYWORDS = frozenset({"seed", "random_state", "random_seed", "rng_seed"})
_SEED_CALLEES = frozenset(
    {
        "seed",
        "manual_seed",
        "manual_seed_all",
        "default_rng",
        "RandomState",
        "Random",
        "set_seed",
        "seed_everything",
        "fix_seeds",
        "PRNGKey",
    }
)

_ENUM_BASES = frozenset({"Enum", "IntEnum", "Flag", "IntFlag", "StrEnum"})


# EOF
