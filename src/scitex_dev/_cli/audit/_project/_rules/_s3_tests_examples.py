"""§3 tests/ subdirectory convention and §5 examples/notebook rules.

Rule literals extracted verbatim from `_registry.py` (1286 lines, cap 512)
— pure move, no behaviour change. The corpus ASSEMBLY (severity/slug
tables, co-located merges, the final `_patch` apply) deliberately stays
together in `_rules/__init__.py`. See GITIGNORED/REFACTORING.md.
"""

from __future__ import annotations

from ._rule import Rule

RULES_S3_TESTS_EXAMPLES: list[Rule] = [
        # §3 tests/ subdirectory convention -------------------------------------
        Rule(
            "PS-301",
            "§3",
            "top-level ./htmlcov/ exists — coverage reports should live in tests/coverage/ (gitignored)",
        ),
        Rule(
            "PS-302",
            "§3",
            "unrecognized subdir at tests/ root (must be tests/<pkg>/ or one of the known categories: scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/results/logs/reports/custom)",
        ),
        Rule(
            "PS-303",
            "§3",
            "examples/<name>.{py,sh,ipynb} has no matching tests/examples/test_<name>.py",
        ),
        Rule(
            "PS-501",
            "§5",
            (
                "examples/<n>_*.py main() does not use @stx.session — the "
                "canonical pattern (see ~/proj/figrecipe/examples/ and "
                "~/proj/scitex-python/examples/01_session.py) decorates main "
                "with @stx.session for auto-CLI, auto-organized output "
                "(SDIR_RUN/FINISHED_SUCCESS/<id>/), config injection, and "
                "session reproducibility. Replace manual `OUTPUT_DIR = "
                "Path(__file__).parent / '<n>_out'` boilerplate with `OUT = "
                "Path(CONFIG.SDIR_RUN)` inside the decorated main()."
            ),
        ),
        Rule(
            "PS-502",
            "§5",
            (
                "examples/<n>_*_out/ exists but is empty (or contains only "
                "__pycache__) — the example was never run end-to-end. Either "
                "execute it once so SciTeX's session machinery populates the "
                "FINISHED_SUCCESS marker, or remove the empty _out/ if the "
                "example doesn't yet work."
            ),
        ),
        Rule(
            "PS-503",
            "§5",
            (
                "examples/<n>_*_out/ has no FINISHED_SUCCESS/<session_id>/ "
                "subdir — the demo's already-run artefacts must be tracked "
                "in git so users see them on GitHub. Run the example once "
                "with @stx.session and commit the FINISHED_SUCCESS dir."
            ),
            slug="examples-need-finished-success",
        ),
        Rule(
            "PS-504",
            "§5",
            (
                "examples/<n>.ipynb has no committed cell outputs — looks "
                "nbstripped. GitHub renders cell outputs inline, so the "
                "demo is invisible without them. Re-run the notebook and "
                "commit with outputs intact."
            ),
        ),
        Rule(
            "PS-505",
            "§5",
            (
                "examples/<n>.ipynb has a sibling test "
                "tests/examples/test_<n>.py but the test does not invoke "
                "`nbconvert --execute` or `pytest --nbval` — runpy/import "
                "tricks don't execute notebooks. Mirror the .py "
                "smoke-test convention with one of those commands."
            ),
        ),
        Rule(
            "PS-506",
            "§5",
            (
                "examples/<n>.ipynb imports matplotlib but lacks the "
                "`%matplotlib inline` cell magic — figure outputs won't "
                "embed in the notebook, so GitHub-rendered cells will be "
                "blank. Add `%matplotlib inline` near the top."
            ),
        ),
        Rule(
            "PS-507",
            "§5",
            (
                "examples/<n>.ipynb imports matplotlib but does not call "
                "`plt.show()` (or rely on inline auto-display) — figures "
                "may not appear in the rendered cell outputs. Call "
                "`plt.show()` explicitly after each plot."
            ),
        ),
        Rule(
            "PS-508",
            "§5",
            (
                "examples/<n>.ipynb contains warning output in committed "
                "cells (DeprecationWarning, UserWarning, FutureWarning, "
                "RuntimeWarning, or stderr-stream `Warning:` text). "
                "Demos must be clean — silence the warning at the source, "
                "filter it explicitly with `warnings.filterwarnings`, or "
                "fix the underlying cause before re-running and committing."
            ),
        ),
]

# EOF
