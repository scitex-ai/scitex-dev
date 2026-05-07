"""Category S: Structure rules."""

from ._base import Rule

S001 = Rule(
    id="STX-S001",
    severity="error",
    category="structure",
    message="Missing @stx.session or @stx.module decorator on main function",
    suggestion=(
        "Add @stx.session (for scripts) or @stx.module (for cloud modules).\n"
        "  @stx.session\n"
        "  def main(...):\n"
        "      return 0\n"
        "If this is library code (not a script), add its directory to library_dirs:\n"
        "  [tool.scitex-linter]\n"
        '  library_dirs = ["src", "tests", "apps", "config", "docs"]\n'
        "  Or: SCITEX_DEV_LINTER_NON_SCRIPT_DIRS=src,tests,apps,config,docs"
    ),
    requires="scitex",
)

S002 = Rule(
    id="STX-S002",
    severity="error",
    category="structure",
    message="Missing `if __name__ == '__main__'` guard",
    suggestion=(
        "Add `if __name__ == '__main__': main()` at the end of the script.\n"
        "If this is library code (not a script), add its directory to library_dirs:\n"
        "  [tool.scitex-linter]\n"
        '  library_dirs = ["src", "tests", "apps", "config", "docs"]\n'
        "  Or: SCITEX_DEV_LINTER_NON_SCRIPT_DIRS=src,tests,apps,config,docs"
    ),
)

S003 = Rule(
    id="STX-S003",
    severity="error",
    category="structure",
    message="argparse detected — @stx.session auto-generates CLI from function signature",
    suggestion=(
        "Remove `import argparse` and define parameters as function arguments:\n"
        "  @stx.session\n"
        "  def main(data_path: str, threshold: float = 0.5):\n"
        "      # Auto-generates: --data-path, --threshold"
    ),
    requires="scitex",
)

S004 = Rule(
    id="STX-S004",
    severity="warning",
    category="structure",
    message="@stx.session function should return an integer exit code",
    suggestion="Add `return 0` for success at the end of your session function.",
    requires="scitex",
)

S005 = Rule(
    id="STX-S005",
    severity="warning",
    category="structure",
    message="Missing `import scitex as stx`",
    suggestion="Add `import scitex as stx` to use SciTeX modules.",
    requires="scitex",
)

S006 = Rule(
    id="STX-S006",
    severity="warning",
    category="structure",
    message="@stx.session function missing explicit INJECTED parameters",
    suggestion=(
        "Declare auto-injected values explicitly in the function signature:\n"
        "  @stx.session\n"
        "  def main(\n"
        "      CONFIG=stx.session.INJECTED,\n"
        "      plt=stx.session.INJECTED,\n"
        "      COLORS=stx.session.INJECTED,\n"
        "      rngg=stx.session.INJECTED,\n"
        "      logger=stx.session.INJECTED,\n"
        "  ):\n"
        "      return 0"
    ),
    requires="scitex",
)

S007 = Rule(
    id="STX-S007",
    severity="warning",
    category="structure",
    message="load_configs() result should be assigned to an UPPER_CASE variable",
    suggestion=(
        "Use UPPER_CASE for config variables — they hold project constants:\n"
        "  CONFIG = load_configs()          # good\n"
        "  config = load_configs()          # bad — looks like a local variable"
    ),
)

S008 = Rule(
    id="STX-S008",
    severity="info",
    category="structure",
    message="Magic number in module scope — consider centralizing in config/",
    suggestion=(
        "Move hard-coded values to config/*.yaml and load with load_configs():\n"
        "  # config/MODEL.yaml\n"
        "  HIDDEN_DIM: 256\n"
        "  DROPOUT: 0.3\n"
        "\n"
        "  # script.py\n"
        "  CONFIG = load_configs()\n"
        "  CONFIG.MODEL.HIDDEN_DIM    # 256"
    ),
)
