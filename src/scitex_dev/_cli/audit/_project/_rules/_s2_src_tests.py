"""§2 src<->tests mirror and test-quality rules.

Rule literals extracted verbatim from `_registry.py` (1286 lines, cap 512)
— pure move, no behaviour change. The corpus ASSEMBLY (severity/slug
tables, co-located merges, the final `_patch` apply) deliberately stays
together in `_rules/__init__.py`. See GITIGNORED/REFACTORING.md.
"""

from __future__ import annotations

from ._rule import Rule

RULES_S2_SRC_TESTS: list[Rule] = [
        # §2 src ↔ tests mirror -------------------------------------------------
        Rule(
            "PS-201",
            "§2",
            "src/<pkg>/ exists but tests/<pkg>/ is missing — every package needs the tests/<pkg>/ parent",
            slug="tests-pkg-parent-missing",
        ),
        Rule(
            "PS-202",
            "§2",
            "src/<pkg>/<sub>/ has files but tests/<pkg>/<sub>/ is missing",
            slug="src-tests-mirror-dir-missing",
        ),
        Rule(
            "PS-203",
            "§2",
            "loose test_*.py at tests/ root that should live inside tests/<pkg>/...",
            slug="loose-top-level-test",
        ),
        Rule(
            "PS-204",
            "§2",
            "orphan test file: tests/<pkg>/<path>/test_*.py with no matching src/<pkg>/<path>/*.py",
            slug="orphan-test-file",
        ),
        Rule(
            "PS-205",
            "§2",
            "wrong public/private prefix (private `_foo.py` must be tested by `test__foo.py`, not `test_foo.py`)",
            slug="test-name-prefix-mismatch",
        ),
        Rule(
            "PS-145",
            "§1",
            (
                "source reads another scitex package's user-state tree "
                "(`~/.scitex/<other-pkg>/...`) or `SCITEX_<OTHER>_*` env "
                "var directly. Cross-package state coupling breaks "
                "`SCITEX_DIR` relocation and standalone-ability. Use the "
                "plugin-port pattern: expose your own `SCITEX_<THIS>_*_DIRS` "
                "slot and let consumers populate it. See "
                "_skills/general/01_ecosystem/06_local-state-directories.md "
                "§9.5."
            ),
            slug="local-state-cross-package-read",
        ),
        Rule(
            "PS-146",
            "§1",
            (
                "pyproject.toml declares an install-time hook (hatch build "
                "hook or setuptools cmdclass) that creates `~/.scitex/"
                "<pkg-short>/` — `pip install` side-effects break wheel "
                "inertness, fresh-CI runs, and `$SCITEX_DIR` relocation. "
                "Drop the hook and rely on lazy `PathManager` mkdir on "
                "first write (§3.5)."
            ),
            slug="local-state-pip-install-side-effect",
        ),
        Rule(
            "PS-147",
            "§1",
            (
                "source writes an eval-form shell-completion line "
                '(`eval "$(_<NAME>_COMPLETE=bash_source <bin>)"`) into '
                "the user's rc file. The eval form re-invokes the binary "
                "on every shell start (~0.4s/binary). Use the cache-file "
                "pattern instead: generate the completion once into "
                "`~/.scitex/<pkg-short>/runtime/completion/<binary>` and "
                "have rc `source` it. See _skills/general/03_interface/02_"
                "cli/03_required-introspection-commands.md."
            ),
            slug="local-state-eval-completion",
        ),
        Rule(
            "PS-150",
            "§1",
            (
                "pyproject.toml `[project.optional-dependencies.dev]` does not "
                "declare `scitex-dev` (or `scitex-dev[cli-audit]`). "
                '`tests/develop/test_audit.py` calls `shutil.which("scitex-dev")` '
                "and pytest.skip()s when absent — i.e. the audit-conformance gate "
                "silently does NOT run in CI's fresh venv. Add `scitex-dev>=0.11.5` "
                "(or current latest) to `[dev]` so the gate fires."
            ),
        ),
        Rule(
            "PS-164",
            "§1",
            (
                "GitHub Actions workflow naming/structure violates convention "
                "(one file = one check, descriptive kebab-case filename; see "
                "_skills/general/02_package/12_workflows-naming.md). Three "
                "sub-checks: vague filename in denylist, multi-job file with "
                "unrelated job IDs, or `name:` field mismatching the filename."
            ),
            slug="workflow-naming",
        ),
        Rule(
            "PS-151",
            "§1",
            (
                "scitex-dev pin floor in `[dev]` is below the known-good version "
                "(currently 0.11.5). Older scitex-dev releases ship a smaller / "
                "differently-classified rule corpus, so the same package gets "
                "different audit verdicts depending on which scitex-dev wheel "
                "PyPI happens to surface. Bump the floor to the current minimum."
            ),
        ),
        Rule(
            "PS-206",
            "§2",
            "placeholder-only test (no `def test_` or `class Test`)",
        ),
        Rule(
            "PS-206b",
            "§2",
            (
                "import-smoke-only test (`def test_*` exists but the file "
                "has no assertion at all — `assert`, `pytest.raises`, "
                "`mock.assert_*`, `self.assertX`, etc.). Pure "
                "`importlib.import_module(...)` smokes pass PS-206 + PS-202 "
                "without exercising behaviour. Add a real assertion or "
                "delete the file."
            ),
        ),
        Rule(
            "PS-210",
            "§2",
            (
                "`[dev]` extras incomplete — an optional `[X]` extra dep is "
                "imported unguarded by the test suite but missing from `[dev]` "
                "(see _skills/general/01_ecosystem/02_dependency-and-version-"
                "pinning.md `[dev]` extras completeness — fastmcp lesson, "
                "2026-05-02). A bare `pip install -e .[dev]` will fail at "
                "test-collection."
            ),
        ),
        Rule(
            "PS-207",
            "§2",
            (
                "empty test directory (no `test_*.py` files, only `__pycache__/` "
                "or nothing) — created during a partial migration but never filled. "
                "Either move the corresponding `tests/<sub>/test_*.py` files in, "
                "or remove the empty dir."
            ),
        ),
        Rule(
            "PS-211",
            "§2",
            (
                "missing `tests/smoke/` layer (fast <60s subprocess-driven CLI "
                "happy-path tests). Every SciTeX package with a CLI should keep "
                "a small set of subprocess-level smoke tests that run on every "
                "PR. Required: ≥1 `tests/smoke/test_*.py` AND register the "
                "`smoke` pytest marker in `[tool.pytest.ini_options].markers`. "
                "Opt-out: `[tool.scitex_dev]\\nno_cli = true` in pyproject.toml. "
                "Severity W during ecosystem adoption — will promote to E."
            ),
            slug="tests-smoke-layer-missing",
        ),
        Rule(
            "PS-212",
            "§2",
            (
                "missing `tests/e2e/` layer (slow end-to-end workflows against "
                "real subsystems). Required: ≥1 `tests/e2e/test_*.py`, register "
                "the `e2e` pytest marker, and gate execution via the `RUN_E2E=1` "
                "env var so the suite is skipped by default. Opt-out: "
                "`[tool.scitex_dev]\\nno_e2e = true` in pyproject.toml. "
                "Severity W during ecosystem adoption — will promote to E."
            ),
            slug="tests-e2e-layer-missing",
        ),
]

# EOF
