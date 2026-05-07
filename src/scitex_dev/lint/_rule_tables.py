"""Call-level rule lookup tables for the SciTeX checker."""

from . import rules

# Convenience aliases used by checker.py
S001, S002, S003 = rules.S001, rules.S002, rules.S003
S004, S005, S006 = rules.S004, rules.S005, rules.S006
S007, S008 = rules.S007, rules.S008
I001, I002, I003 = rules.I001, rules.I002, rules.I003
I006, I007 = rules.I006, rules.I007

# Names that refer to the scitex package (skip linting on these)
STX_NAMES = frozenset(("stx", "scitex"))

# Phase 2: Call-level rule lookup table {(module_alias, func_name): Rule}
# module_alias=None means match func_name on any object
CALL_RULES: dict = {
    # IO rules
    ("np", "save"): rules.IO001,
    ("numpy", "save"): rules.IO001,
    ("np", "load"): rules.IO002,
    ("numpy", "load"): rules.IO002,
    ("pd", "read_csv"): rules.IO003,
    ("pandas", "read_csv"): rules.IO003,
    (None, "to_csv"): rules.IO004,
    ("pickle", "dump"): rules.IO005,
    ("pickle", "dumps"): rules.IO005,
    ("json", "dump"): rules.IO006,
    (None, "savefig"): rules.IO007,
    # Plot rules
    (None, "show"): rules.P004,  # plt.show()
    # Stats rules -- scipy.stats.X()
    ("stats", "ttest_ind"): rules.ST001,
    ("stats", "mannwhitneyu"): rules.ST002,
    ("stats", "pearsonr"): rules.ST003,
    ("stats", "f_oneway"): rules.ST004,
    ("stats", "wilcoxon"): rules.ST005,
    ("stats", "kruskal"): rules.ST006,
    # Path rules
    ("os", "makedirs"): rules.PA003,
    ("os", "mkdir"): rules.PA003,
    ("os", "chdir"): rules.PA004,
}

# Axes method suggestions {func_name: Rule}
AXES_HINTS: dict = {
    "plot": rules.P001,
    "scatter": rules.P002,
    "bar": rules.P003,
}

# Modules to skip for axes hints
AXES_SKIP = frozenset(
    (
        "stx",
        "scitex",
        "os",
        "sys",
        "Path",
        "math",
        "np",
        "numpy",
        "pd",
        "pandas",
    )
)

# print() inside session
PRINT_RULE = rules.P005
