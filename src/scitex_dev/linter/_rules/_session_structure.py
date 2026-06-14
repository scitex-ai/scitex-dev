"""Category S: scitex-umbrella structure rules (STX-S001-S012).

These rules describe the ``@stx.session`` script structure: the
decorator, the ``__main__`` guard, argparse avoidance, the int exit
code, the ``import scitex as stx`` line, the INJECTED parameters, the
UPPER_CASE config naming, and module-scope magic numbers.

Absorbed into the engine in-house (umbrella-thinning Phase A) from the
umbrella's ``scitex._linter_plugin``. Every id, severity, category,
message, suggestion, and ``requires`` gate is preserved verbatim for
S001-S008. Note the ``requires`` fields are NOT uniform:
S001/S003/S004/S005/S006 gate on ``requires="scitex"`` (they reference
``@stx.session`` / ``import scitex``), while S002/S007/S008 are generic
structure/naming checks that fire regardless.

S009-S012 are the HARDCODE-LINT extension (operator directive,
2026-06-15). Their default severity is ``"warning"`` (library /
package / other project-types). When ``.scitex/dev/config.yaml`` lists
``project-type: research``, the checker upgrades them to ``"error"``
(blocking) — hardcoding paths/strings/params in a research repo
silently kills provenance.

  STX-S009 — string-literal in code body (outside ``config/``)
  STX-S010 — path-like string literal (``data/...``, ``*.csv`` …)
  STX-S011 — hardcoded parameter assignment in script
  STX-S012 — redundant print / logger after a scitex ``save()`` call
"""

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

# ---------------------------------------------------------------------------
# HARDCODE-LINT extension (operator directive 2026-06-15)
# ---------------------------------------------------------------------------
# S009-S012 default to "warning" so library / package / other-typed repos
# get a soft signal. The checker (``_naming_checker.py``) upgrades them to
# "error" when ``.scitex/dev/config.yaml`` lists ``project-type: research``
# — see ``_resolve_hardcode_severity()``.
# ``config/`` is the ONLY exempt directory: that tree legitimately holds
# provenance-bearing literal values (model dims, cohort names, paths).
# Anything outside ``config/`` that hardcodes is flagged.

S009 = Rule(
    id="STX-S009",
    severity="warning",
    category="structure",
    message=(
        "String literal outside config/ — move to config/*.yaml for "
        "provenance. (Default severity: warning. project-type: research "
        "upgrades to error.)"
    ),
    suggestion=(
        "Hardcoded strings in a research script hide what was run.\n"
        "Move to config/*.yaml and resolve via CONFIG:\n"
        "  # config/COHORT.yaml\n"
        "  NAME: fig01_cohort\n"
        "\n"
        "  # scripts/fig01.py\n"
        "  CONFIG = load_configs()\n"
        "  cohort = CONFIG.COHORT.NAME    # 'fig01_cohort'\n"
        "Suppress per-line with `# stx-allow: STX-S009` when the literal is "
        "intrinsic (an error message, log key, etc.)."
    ),
)

S010 = Rule(
    id="STX-S010",
    severity="warning",
    category="structure",
    message=(
        "Path-like string literal outside config/ — paths drive I/O and "
        "MUST live in config/PATH.yaml. (Default: warning. project-type: "
        "research upgrades to error.)"
    ),
    suggestion=(
        "Hardcoded paths break provenance and reproducibility. Move to "
        "config/PATH.yaml:\n"
        "  # config/PATH.yaml\n"
        "  COHORT_DIR: data/fig01_cohort\n"
        "\n"
        "  # scripts/fig01.py\n"
        "  CONFIG = load_configs()\n"
        "  stx.io.load(CONFIG.PATH.COHORT_DIR + '/raw.csv')\n"
        "Suppress per-line with `# stx-allow: STX-S010`."
    ),
)

S011 = Rule(
    id="STX-S011",
    severity="warning",
    category="structure",
    message=(
        "Hardcoded parameter (UPPER_CASE = literal) in a script outside "
        "config/ — parameters belong in config/. (Default: warning. "
        "project-type: research upgrades to error.)"
    ),
    suggestion=(
        "Lift module-scope UPPER_CASE literals to config/*.yaml and read "
        "via CONFIG. Numeric → CONFIG.MODEL.HIDDEN_DIM; string → "
        "CONFIG.COHORT.NAME; path → CONFIG.PATH.DATA. Anything in "
        "config/*.py is exempt because that tree IS the source of truth.\n"
        "Suppress per-line with `# stx-allow: STX-S011`."
    ),
)

S012 = Rule(
    id="STX-S012",
    severity="warning",
    category="structure",
    message=(
        "Redundant log after scitex ``save()`` — the save call auto-logs. "
        "Drop the extra print / logger.info."
    ),
    suggestion=(
        "``stx.io.save`` / ``logger.success`` already records the artifact "
        "path + sha. The follow-up print is duplicated provenance:\n"
        "  stx.io.save(df, 'out.csv')\n"
        "  print('saved')              # ← redundant, remove\n"
        "Suppress per-line with `# stx-allow: STX-S012`."
    ),
)
