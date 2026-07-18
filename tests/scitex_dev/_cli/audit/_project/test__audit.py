"""Tests for the project-structure auditor (PS<n> rules).

Each rule has at least one positive (rule fires on a synthetic broken repo)
and one negative (rule stays silent on a clean repo) test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project import RULES, audit_project
from scitex_dev._cli.audit._project._audit import (
    _check_top_level,
    _check_mirror,
    _check_tests_subdir_convention,
    _check_docs_structure,
    _check_placeholder_tests,
)


# ---------------------------------------------------------------------------
# Test repo fixtures
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, name: str = "demo-pkg") -> Path:
    """Build a minimal-but-valid SciTeX-shaped repo."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
    )
    import_name = name.replace("-", "_")
    src = tmp_path / "src" / import_name
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    tests = tmp_path / "tests" / import_name
    tests.mkdir(parents=True)
    (tmp_path / "tests" / "__init__.py").write_text("")
    # PS-133-PS-135 + PS-138: required community files at repo root.
    # README is intentionally NOT created here so test_ps106_silent_when_readme_missing
    # still represents "no README" — tests that need a README write their own.
    (tmp_path / "LICENSE").write_text("MIT\n")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
    (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n")
    (tmp_path / "CLA.md").write_text("# CLA\n")
    # examples/ + matching test left to individual tests so PS-136/PS-303
    # negative tests can still represent missing/mismatched states.
    return tmp_path


def _violations_for(repo: Path, name: str) -> list[str]:
    """Run the rule check functions directly and return the rule codes that fired."""
    from scitex_dev._cli.audit._project._audit import Violation, _src_pkg_dir
    from scitex_dev._cli.audit._project._check_flat_layout import check_flat_layout

    out: list = []
    _check_top_level(repo, out)
    _check_mirror(repo, name, out)
    _check_tests_subdir_convention(repo, name, out)
    _check_docs_structure(repo, out)
    _check_placeholder_tests(repo, out)
    src_pkg = _src_pkg_dir(repo, name)
    if src_pkg is not None:
        check_flat_layout(src_pkg, Violation, out)
    from scitex_dev._cli.audit._project._check_readme_badges import (
        check_coverage_badge,
    )

    check_coverage_badge(repo, Violation, out)
    from scitex_dev._cli.audit._project._check_readme_sections import (
        check_readme_sections,
    )

    check_readme_sections(repo, Violation, out)
    from scitex_dev._cli.audit._project._check_examples import (
        check_examples_conventions,
    )

    check_examples_conventions(repo, Violation, out)
    from scitex_dev._cli.audit._project._check_readme_structure import (
        check_readme_structure,
    )

    check_readme_structure(repo, Violation, out)
    from scitex_dev._cli.audit._project._audit import check_codecov_target

    check_codecov_target(repo, Violation, out)
    return [v.rule for v in out]


# Canonical compliant README used by negative tests for PS-107/109/110/111/112.
# Padded past the 200-byte threshold so PS-107 sees a "substantive" file.
_GOOD_README = (
    "# demo\n\n"
    "[![PyPI](https://badge.fury.io/py/demo.svg)](https://pypi.org/project/demo/)\n"
    "[![cov](https://codecov.io/gh/x/y/graph/badge.svg)](https://codecov.io/gh/x/y)\n"
    '<p align="center"><img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400"></p>\n\n'
    "## Installation\n\n```bash\npip install demo\n```\n\n"
    "## Quick Start\n\n```python\nimport demo\n```\n\n"
    "## Four Interfaces\n\n- Python API\n- CLI\n- MCP\n- Skills\n\n"
    "## Part of SciTeX\n\n"
    "`demo` is part of [SciTeX](https://scitex.ai).\n\n"
    ">Four Freedoms for Research\n>\n"
    ">0. Run.\n>1. Study.\n>2. Redistribute.\n>3. Modify.\n\n"
    '<p align="center"><a href="https://scitex.ai">'
    '<img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a></p>\n'
)


# ---------------------------------------------------------------------------
# Sanity / discovery
# ---------------------------------------------------------------------------


def test_rules_have_unique_codes_and_sections_len_codes_len_set_codes():
    # Arrange
    # Act
    # Assert
    codes = list(RULES.keys())
    assert len(codes) == len(set(codes)), "duplicate rule codes"
    sections = {r.section for r in RULES.values()}


def test_rules_have_unique_codes_and_sections_sections_1_2_3_4():
    # Arrange
    # Act
    # Assert
    codes = list(RULES.keys())
    sections = {r.section for r in RULES.values()}
    assert sections >= {"§1", "§2", "§3", "§4"}


def test_rule_namespace_is_ps_or_rp():
    # Arrange
    # Act
    # Assert
    # The project auditor hosts two rule families: PS-* (package-publish,
    # routed to project-type `pip`) and RP-* (research-project mirror,
    # routed to project-type `research`). `applies()` in _config/_loader.py
    # gates each family by project-type.
    assert all(c.startswith(("PS", "RP")) for c in RULES)


# ---------------------------------------------------------------------------
# §1 Top-level layout
# ---------------------------------------------------------------------------


def test_ps101_fires_when_pyproject_missing(tmp_path):
    # Bare dir, no pyproject
    # Arrange
    # Act
    # Assert
    rules = _violations_for(tmp_path, "demo")
    assert "PS-101" in rules


def test_ps102_fires_on_forbidden_top_level_dir(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path)
    (repo / "mgmt").mkdir()
    rules = _violations_for(repo, "demo-pkg")
    assert "PS-102" in rules


def test_ps103_fires_on_top_level_junk(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path)
    (repo / "tmp_quick.py").write_text("x = 1\n")
    rules = _violations_for(repo, "demo-pkg")
    assert "PS-103" in rules


def test_ps104_fires_on_playground(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path)
    (repo / ".playground").mkdir()
    rules = _violations_for(repo, "demo-pkg")
    assert "PS-104" in rules


# ---------------------------------------------------------------------------
# §2 src ↔ tests mirror
# ---------------------------------------------------------------------------


def test_ps201_fires_when_tests_pkg_parent_missing(tmp_path):
    """src/<pkg>/ exists, tests/ exists, but no tests/<pkg>/ parent."""
    # Arrange
    # Act
    # Assert
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "foo.py").write_text("def f(): pass\n")
    (tmp_path / "tests").mkdir()
    rules = _violations_for(tmp_path, "demo")
    assert "PS-201" in rules


def test_ps202_fires_on_unmatched_subdir(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "sub").mkdir()
    (repo / "src" / "demo" / "sub" / "x.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS-202" in rules


def test_ps203_fires_on_loose_top_level_test(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "test__cache.py").write_text("def test_x(): assert True\n")
    rules = _violations_for(repo, "demo")
    assert "PS-203" in rules


def test_ps203_strict_no_meta_test_exemption(tmp_path):
    """Strict: any test_*.py at tests/ root violates, even meta-tests."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "test_examples.py").write_text("def test_x(): assert True\n")
    rules = _violations_for(repo, "demo")
    assert "PS-203" in rules


def test_ps204_fires_on_orphan_test(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_nonexistent.py").write_text(
        "def test_x(): assert True\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-204" in rules


def test_ps204_silent_for_dunder_main(tmp_path):
    """Regression: src/<pkg>/__main__.py paired with tests/<pkg>/test___main__.py
    is the correct mirror — must NOT be flagged as orphan."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "__main__.py").write_text("def main(): pass\n")
    (repo / "tests" / "demo" / "test___main__.py").write_text("def test_main(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS-204" not in rules


def test_ps205_fires_on_wrong_prefix(tmp_path):
    """Source `_foo.py` (private) tested by `test_foo.py` (single _) is wrong."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "_foo.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_foo.py").write_text("def test_f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS-205" in rules


def test_ps206_fires_on_placeholder_test(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_foo.py").write_text(
        "# Add your tests here\n"
        "if __name__ == '__main__':\n"
        "    import pytest; pytest.main([__file__])\n"
    )
    (repo / "src" / "demo" / "foo.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS-206" in rules


def test_ps206_silent_when_real_test_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_foo.py").write_text(
        "def test_f():\n    assert True\n"
    )
    (repo / "src" / "demo" / "foo.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS-206" not in rules


def test_ps206_silent_for_factory_assigned_test(tmp_path):
    """`test_x = make_*(...)` is a valid pytest collectable, not a placeholder."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_skills.py").write_text(
        "from somewhere import make_skill_quality_tests\n"
        "test_skills_quality = make_skill_quality_tests()\n"
    )
    (repo / "src" / "demo" / "foo.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS-206" not in rules


# ---------------------------------------------------------------------------
# §3 tests/ subdir convention
# ---------------------------------------------------------------------------


def test_ps301_fires_on_top_level_htmlcov(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "htmlcov").mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS-301" in rules


def test_ps302_fires_on_unrecognized_subdir(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "weird_extra_dir").mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS-302" in rules


def test_ps302_silent_for_known_categories(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    for sub in ["scripts", "examples", "skills", "agentic", "integration", "e2e"]:
        (repo / "tests" / sub).mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS-302" not in rules


def test_ps303_fires_on_example_without_test(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("print('demo')\n")
    rules = _violations_for(repo, "demo")
    assert "PS-303" in rules


def test_ps303_silent_when_test_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("print('demo')\n")
    (repo / "tests" / "examples").mkdir()
    (repo / "tests" / "examples" / "test_01_demo.py").write_text(
        "def test_x(): assert True\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-303" not in rules


# ---------------------------------------------------------------------------
# §4 docs/ structure
# ---------------------------------------------------------------------------


def test_ps401_fires_when_to_claude_not_gitignored(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "docs" / "to_claude").mkdir(parents=True)
    rules = _violations_for(repo, "demo")
    assert "PS-401" in rules


def test_ps401_silent_when_to_claude_is_gitignored(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "docs" / "to_claude").mkdir(parents=True)
    (repo / ".gitignore").write_text("docs/to_claude/\n")
    rules = _violations_for(repo, "demo")
    assert "PS-401" not in rules


# ---------------------------------------------------------------------------
# End-to-end via audit_project()
# ---------------------------------------------------------------------------


def test_audit_project_returns_2_when_repo_missing():
    # Pass an obviously-missing distribution and no repo override
    # → resolver fails, returns 2.
    # Arrange
    # Act
    # Assert
    rc = audit_project("nonexistent-pkg-zzz", repo=None)
    assert rc == 2


def test_audit_project_clean_repo_returns_0(tmp_path):
    """The new-rules subset (PS-133-138, layout, dirs) must pass on a clean fixture.

    The full audit runs every rule (badge, README sections, four-freedoms,
    interfaces — see PS-106/PS-110b/PS-120/PS-131) and would need a fully
    compliant real-world README to pass. That's covered by per-rule
    negative tests; here we just confirm the structural rules pass.
    """
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_GOOD_README)
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("# demo\n")
    (repo / "tests" / "examples").mkdir(parents=True, exist_ok=True)
    (repo / "tests" / "examples" / "test_01_demo.py").write_text(
        "def test_demo(): pass\n"
    )
    structural = {
        "PS-101",
        "PS-102",
        "PS-103",
        "PS-104",
        "PS-105",
        "PS-133",
        "PS-134",
        "PS-135",
        "PS-136",
        "PS-137",
        "PS-138",
        "PS-201",
        "PS-202",
        "PS-203",
        "PS-204",
        "PS-205",
        "PS-301",
        "PS-302",
        "PS-303",
        "PS-401",
        "PS-402",
    }
    rc = audit_project("demo", repo=repo, rules=structural)
    assert rc == 0


def test_audit_project_dirty_repo_returns_1(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "mgmt").mkdir()  # forbidden top-level dir
    rc = audit_project("demo", repo=repo)
    assert rc == 1


def test_audit_project_rule_filter_restricts(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "mgmt").mkdir()  # PS-102
    (repo / "tmp_quick.py").write_text("x=1\n")  # PS-103
    # JSON mode is easier to assert against:
    import json as _json
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit_project("demo", repo=repo, json_out=True, rules={"PS-102"})
    payload = _json.loads(buf.getvalue())
    codes = {v["rule"] for v in payload["violations"]}
    assert codes == {"PS-102"}


# ---------------------------------------------------------------------------
# PS-108 — flat package layout
# ---------------------------------------------------------------------------


def test_ps108_fires_on_prefix_cluster(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    src = repo / "src" / "demo"
    (src / "_cli_a.py").write_text("")
    (src / "_cli_b.py").write_text("")
    (src / "_cli_c.py").write_text("")
    rules = _violations_for(repo, "demo")
    assert "PS-108" in rules


def test_ps108_silent_below_threshold(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    src = repo / "src" / "demo"
    (src / "_cli_a.py").write_text("")
    (src / "_cli_b.py").write_text("")
    rules = _violations_for(repo, "demo")
    assert "PS-108" not in rules


def test_ps108_silent_when_subpkg_absorbs_cluster(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    src = repo / "src" / "demo"
    (src / "_cli").mkdir()
    (src / "_cli" / "__init__.py").write_text("")
    (src / "_cli_a.py").write_text("")
    (src / "_cli_b.py").write_text("")
    (src / "_cli_c.py").write_text("")
    rules = _violations_for(repo, "demo")
    assert "PS-108" not in rules


def test_ps108_rolls_up_multiple_clusters_len_out_1(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    src = repo / "src" / "demo"
    for n in ("a", "b", "c"):
        (src / f"_cli_{n}.py").write_text("")
        (src / f"_skills_{n}.py").write_text("")
    # Direct call: assert single rolled-up violation mentions both prefixes.
    from scitex_dev._cli.audit._project._audit import Violation
    from scitex_dev._cli.audit._project._check_flat_layout import check_flat_layout

    out: list = []
    check_flat_layout(src, Violation, out)
    assert len(out) == 1


def test_ps108_rolls_up_multiple_clusters_cli__in_out_0_detail_and_skills__in_out(
    tmp_path,
):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    src = repo / "src" / "demo"
    for n in ("a", "b", "c"):
        (src / f"_cli_{n}.py").write_text("")
        (src / f"_skills_{n}.py").write_text("")
    # Direct call: assert single rolled-up violation mentions both prefixes.
    from scitex_dev._cli.audit._project._audit import Violation
    from scitex_dev._cli.audit._project._check_flat_layout import check_flat_layout

    out: list = []
    check_flat_layout(src, Violation, out)
    assert "cli_*" in out[0].detail and "skills_*" in out[0].detail


# ---------------------------------------------------------------------------
# PS-108 / PS-108b slug regression — the `[CODE §X slug]` shown in
# audit-all output must describe the ACTUAL rule (flat-package-layout),
# not a long-retired README-badge rule that used to live at this code.
# ---------------------------------------------------------------------------


def test_ps108_slug_describes_flat_layout_not_readme_badge():
    # Arrange
    rule = RULES["PS-108"]
    # Act
    slug = rule.slug
    # Assert
    assert "readme" not in slug


def test_ps108b_slug_describes_flat_layout_not_readme_badge():
    # Arrange
    rule = RULES["PS-108b"]
    # Act
    slug = rule.slug
    # Assert
    assert "readme" not in slug


# ---------------------------------------------------------------------------
# PS-204 enrichment — actionable orphan-test hints (basename + sibling listing)
# ---------------------------------------------------------------------------


def test_ps204_hint_suggests_move_on_unique_basename_len_ps204_1(tmp_path):
    """Refactor scenario: src/<pkg>/foo.py moved to src/<pkg>/sub/foo.py;
    the orphan test_foo.py should be told where to relocate."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "sub").mkdir()
    (repo / "src" / "demo" / "sub" / "foo.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_foo.py").write_text("def test_x(): pass\n")
    out: list = []
    from scitex_dev._cli.audit._project._audit import _check_mirror

    _check_mirror(repo, "demo", out)
    ps204 = [v for v in out if v.rule == "PS-204"]
    assert len(ps204) == 1


def test_ps204_hint_suggests_move_on_unique_basename_src_likely_moved_in_ps204_0_detail(
    tmp_path,
):
    """Refactor scenario: src/<pkg>/foo.py moved to src/<pkg>/sub/foo.py;
    the orphan test_foo.py should be told where to relocate."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "sub").mkdir()
    (repo / "src" / "demo" / "sub" / "foo.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_foo.py").write_text("def test_x(): pass\n")
    out: list = []
    from scitex_dev._cli.audit._project._audit import _check_mirror

    _check_mirror(repo, "demo", out)
    ps204 = [v for v in out if v.rule == "PS-204"]
    assert "src likely moved" in ps204[0].detail


def test_ps204_hint_suggests_move_on_unique_basename_sub_foo_py_in_ps204_0_detail(
    tmp_path,
):
    """Refactor scenario: src/<pkg>/foo.py moved to src/<pkg>/sub/foo.py;
    the orphan test_foo.py should be told where to relocate."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "sub").mkdir()
    (repo / "src" / "demo" / "sub" / "foo.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_foo.py").write_text("def test_x(): pass\n")
    out: list = []
    from scitex_dev._cli.audit._project._audit import _check_mirror

    _check_mirror(repo, "demo", out)
    ps204 = [v for v in out if v.rule == "PS-204"]
    assert "sub/foo.py" in ps204[0].detail


def test_ps204_hint_suggests_move_on_unique_basename_tests_demo_sub_test_foo_py_in_ps204_0_de(
    tmp_path,
):
    """Refactor scenario: src/<pkg>/foo.py moved to src/<pkg>/sub/foo.py;
    the orphan test_foo.py should be told where to relocate."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "sub").mkdir()
    (repo / "src" / "demo" / "sub" / "foo.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_foo.py").write_text("def test_x(): pass\n")
    out: list = []
    from scitex_dev._cli.audit._project._audit import _check_mirror

    _check_mirror(repo, "demo", out)
    ps204 = [v for v in out if v.rule == "PS-204"]
    assert "tests/demo/sub/test_foo.py" in ps204[0].detail


def test_ps204_hint_lists_siblings_when_no_basename_match_len_ps204_1(tmp_path):
    """When no src file matches the expected basename, list what *is* in the
    mirror dir so the agent can correlate."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "bar.py").write_text("def f(): pass\n")
    (repo / "src" / "demo" / "baz.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_qux.py").write_text("def test_x(): pass\n")
    out: list = []
    from scitex_dev._cli.audit._project._audit import _check_mirror

    _check_mirror(repo, "demo", out)
    ps204 = [v for v in out if v.rule == "PS-204"]
    assert len(ps204) == 1
    detail = ps204[0].detail


def test_ps204_hint_lists_siblings_when_no_basename_match_bar_py_in_detail_and_baz_py_in_detail(
    tmp_path,
):
    """When no src file matches the expected basename, list what *is* in the
    mirror dir so the agent can correlate."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "bar.py").write_text("def f(): pass\n")
    (repo / "src" / "demo" / "baz.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_qux.py").write_text("def test_x(): pass\n")
    out: list = []
    from scitex_dev._cli.audit._project._audit import _check_mirror

    _check_mirror(repo, "demo", out)
    ps204 = [v for v in out if v.rule == "PS-204"]
    detail = ps204[0].detail
    assert "bar.py" in detail and "baz.py" in detail


# ---------------------------------------------------------------------------
# PS-106 — coverage badge required in README
# ---------------------------------------------------------------------------


def test_ps106_fires_when_no_coverage_badge(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text("# demo\n\nA package.\n")
    rules = _violations_for(repo, "demo")
    assert "PS-106" in rules


def test_ps106_silent_with_codecov_badge(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        "# demo\n\n[![cov](https://codecov.io/gh/x/y/graph/badge.svg)](https://codecov.io/gh/x/y)\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-106" not in rules


def test_ps106_silent_with_shields_codecov_badge(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        "# demo\n\n![cov](https://img.shields.io/codecov/c/github/x/y)\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-106" not in rules


def test_ps106_silent_when_readme_missing(tmp_path):
    """No README → PS-101/future PS-107 catches it; PS-106 stays quiet."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    rules = _violations_for(repo, "demo")
    assert "PS-106" not in rules


# ---------------------------------------------------------------------------
# PS-501 / PS-502 — examples conventions
# ---------------------------------------------------------------------------


def test_ps501_fires_when_main_lacks_stx_session(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text(
        "def main():\n    print('hi')\n\nif __name__ == '__main__':\n    main()\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-501" in rules


def test_ps501_silent_with_stx_session(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text(
        "import scitex as stx\n@stx.session\ndef main():\n    pass\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-501" not in rules


def test_ps501_silent_when_no_def_main(tmp_path):
    """Pure imperative scripts without main() are a separate concern."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("print('hi')\n")
    rules = _violations_for(repo, "demo")
    assert "PS-501" not in rules


def test_ps502_fires_on_empty_out_dir(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("def main(): pass\nmain()")
    (repo / "examples" / "01_demo_out").mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS-502" in rules


def test_ps502_silent_when_out_dir_has_content(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("def main(): pass\nmain()")
    out_dir = repo / "examples" / "01_demo_out"
    out_dir.mkdir()
    fs = out_dir / "FINISHED_SUCCESS" / "session_id"
    fs.mkdir(parents=True)
    (fs / "result.png").write_bytes(b"PNG")
    rules = _violations_for(repo, "demo")
    assert "PS-502" not in rules


def test_ps502_silent_when_only_ipynb_owns_stem(tmp_path):
    """`.ipynb`-only stems: `_out/` is legacy, do not flag."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.ipynb").write_text(
        '{"cells": [{"cell_type": "code", "source": "x=1", "outputs": [{}]}], '
        '"metadata": {}, "nbformat": 4, "nbformat_minor": 5}'
    )
    (repo / "examples" / "01_demo_out").mkdir()  # legacy empty
    rules = _violations_for(repo, "demo")
    assert "PS-502" not in rules


# ---------------------------------------------------------------------------
# PS-503 — _out/ must contain FINISHED_SUCCESS/<session_id>/ from @stx.session
# ---------------------------------------------------------------------------


def test_ps503_fires_when_out_dir_has_no_finished_success(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.py").write_text("def main(): pass\nmain()")
    out_dir = repo / "examples" / "01_demo_out"
    out_dir.mkdir()
    # Has content (so PS-502 is silent) but no FINISHED_SUCCESS/<id>/.
    (out_dir / "stale_artefact.png").write_bytes(b"PNG")
    rules = _violations_for(repo, "demo")
    assert "PS-503" in rules


def test_ps503_silent_when_only_ipynb_owns_stem(tmp_path):
    """`.ipynb`-only stems: cell outputs ARE the demo, no FINISHED_SUCCESS needed."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / "01_demo.ipynb").write_text(
        '{"cells": [{"cell_type": "code", "source": "x=1", "outputs": [{}]}], '
        '"metadata": {}, "nbformat": 4, "nbformat_minor": 5}'
    )
    out_dir = repo / "examples" / "01_demo_out"
    out_dir.mkdir()
    (out_dir / "stale_artefact.png").write_bytes(b"PNG")
    rules = _violations_for(repo, "demo")
    assert "PS-503" not in rules


def test_ps503_silent_when_finished_success_id_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    out_dir = repo / "examples" / "01_demo_out"
    out_dir.mkdir()
    fs_id = out_dir / "FINISHED_SUCCESS" / "2026Y-05M-07D-01h00m00s_demo-main"
    fs_id.mkdir(parents=True)
    (fs_id / "fig.png").write_bytes(b"PNG")
    rules = _violations_for(repo, "demo")
    assert "PS-503" not in rules


# ---------------------------------------------------------------------------
# PS-504 / PS-506 / PS-507 — .ipynb examples conventions
# ---------------------------------------------------------------------------


def _write_notebook(path, cells):
    import json

    nb = {
        "cells": cells,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(nb))


def _code_cell(source, outputs=()):
    return {
        "cell_type": "code",
        "source": source,
        "outputs": list(outputs),
        "execution_count": None,
        "metadata": {},
    }


def test_ps504_fires_when_notebook_has_no_outputs(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [_code_cell("print('hello')")],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-504" in rules


def test_ps504_silent_when_notebook_has_outputs(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "print('hello')",
                outputs=[
                    {"output_type": "stream", "name": "stdout", "text": "hello\n"}
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-504" not in rules


def test_ps506_fires_when_notebook_imports_mpl_without_inline_magic(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.show()",
                outputs=[
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "X"},
                        "metadata": {},
                    }
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-506" in rules


def test_ps506_silent_when_inline_magic_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "%matplotlib inline\nimport matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.show()",
                outputs=[
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "X"},
                        "metadata": {},
                    }
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-506" not in rules


def test_ps507_fires_when_notebook_imports_mpl_without_plt_show(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "%matplotlib inline\nimport matplotlib.pyplot as plt\nplt.plot([1,2,3])",
                outputs=[
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "X"},
                        "metadata": {},
                    }
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-507" in rules


def test_ps506_507_silent_when_notebook_does_not_import_mpl_ps_506_not_in_rules(
    tmp_path,
):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "x = 1\nprint(x)",
                outputs=[{"output_type": "stream", "name": "stdout", "text": "1\n"}],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-506" not in rules


def test_ps506_507_silent_when_notebook_does_not_import_mpl_ps_507_not_in_rules(
    tmp_path,
):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "x = 1\nprint(x)",
                outputs=[{"output_type": "stream", "name": "stdout", "text": "1\n"}],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-507" not in rules


# ---------------------------------------------------------------------------
# PS-505 — .ipynb test must use nbconvert / nbval
# ---------------------------------------------------------------------------


def test_ps505_fires_when_ipynb_test_uses_subprocess_python(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [_code_cell("x=1", outputs=[{"output_type": "stream", "text": "ok"}])],
    )
    test_dir = repo / "tests" / "examples"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "test_01_demo.py").write_text(
        "import subprocess\n"
        "def test_runs():\n"
        "    subprocess.run(['python', '01_demo.ipynb'])\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-505" in rules


def test_ps505_silent_when_ipynb_test_uses_nbconvert(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [_code_cell("x=1", outputs=[{"output_type": "stream", "text": "ok"}])],
    )
    test_dir = repo / "tests" / "examples"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "test_01_demo.py").write_text(
        "import subprocess\n"
        "def test_runs():\n"
        "    subprocess.run(['jupyter', 'nbconvert', '--execute', '--to', 'notebook', '01_demo.ipynb'])\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-505" not in rules


def test_ps508_fires_on_stderr_stream_warning(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "import warnings\nwarnings.warn('old API', DeprecationWarning)",
                outputs=[
                    {
                        "output_type": "stream",
                        "name": "stderr",
                        "text": "DeprecationWarning: old API\n",
                    }
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-508" in rules


def test_ps508_fires_on_error_output_with_warning_class(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "raise FutureWarning('x')",
                outputs=[
                    {
                        "output_type": "error",
                        "ename": "FutureWarning",
                        "evalue": "x",
                        "traceback": [],
                    }
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-508" in rules


def test_ps508_silent_on_clean_stdout(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "print('hello')",
                outputs=[
                    {"output_type": "stream", "name": "stdout", "text": "hello\n"}
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-508" not in rules


def test_ps508_silent_on_real_exception_not_warning(tmp_path):
    """`output_type=error` for a real exception (KeyError, ValueError) is not a warning."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [
            _code_cell(
                "raise KeyError('x')",
                outputs=[
                    {
                        "output_type": "error",
                        "ename": "KeyError",
                        "evalue": "x",
                        "traceback": [],
                    }
                ],
            )
        ],
    )
    rules = _violations_for(repo, "demo")
    assert "PS-508" not in rules


def test_ps505_silent_when_ipynb_test_uses_nbval(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir(exist_ok=True)
    _write_notebook(
        repo / "examples" / "01_demo.ipynb",
        [_code_cell("x=1", outputs=[{"output_type": "stream", "text": "ok"}])],
    )
    test_dir = repo / "tests" / "examples"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "test_01_demo.py").write_text(
        "import subprocess\n"
        "def test_runs():\n"
        "    subprocess.run(['pytest', '--nbval-lax', 'examples/'])\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-505" not in rules


# ---------------------------------------------------------------------------
# PS-141 / PS-142 / PS-143 / PS-144 — README structure rules
# ---------------------------------------------------------------------------


_README_HEADER = (
    "# demo\n\n"
    '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
    '<p align="center"><b>tagline</b></p>\n\n'
    "<!-- scitex-badges:start --><!-- scitex-badges:end -->\n\n"
)


def _good_pas_table():
    return (
        "## Problem and Solution\n\n"
        "| # | Problem | Solution |\n"
        "|---|---------|----------|\n"
        "| 1 | **Hilbert** under-doubles positive freqs at low f0/fs. | "
        "**Hard-step mask** brings the analytic-signal envelope back to scipy parity at every fs. |\n\n"
    )


def _full_compliant_readme():
    # Canonical order (PS-143, updated 2026-05):
    #   Problem and Solution → Demo / Quick Start → Installation
    #   → Architecture → <N> Interfaces → Part of SciTeX
    return (
        _README_HEADER
        + _good_pas_table()
        + "## Demo\n\n![Hilbert](docs/hilbert.png)\n\n"
        + "## Installation\n\n```bash\npip install demo\n```\n\n"
        + "## Architecture\n\n```\ndemo/\n├── core/\n│   └── __init__.py\n└── cli/\n```\n\n"
        + "## 2 Interfaces\n\nPython API and CLI.\n\n"
        + "## Part of SciTeX\n\nPart of SciTeX.\n"
    )


def test_ps141_fires_when_demo_section_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        _README_HEADER
        + _good_pas_table()
        + "## Installation\n\npip install demo\n\n"
        + "## Architecture\n\n```\nfile-tree\n├── x\n│   └── y\n```\n\n"
        + "## 2 Interfaces\n\nx\n\n"
        + "## Part of SciTeX\n\nx\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-141" in rules


def test_ps141_fires_when_demo_section_has_no_visual(tmp_path):
    # PS-141 fires only when BOTH Demo and Architecture lack a visual
    # — the "one diagram is enough, but at least one is required" rule.
    # Strip visuals from both sections so the violation can surface.
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _full_compliant_readme()
    body = body.replace(
        "## Demo\n\n![Hilbert](docs/hilbert.png)",
        "## Demo\n\nLook at this cool thing.",
    )
    body = body.replace(
        "## Architecture\n\n```\ndemo/\n├── core/\n│   └── __init__.py\n└── cli/\n```",
        "## Architecture\n\nThis package is a flat single module.",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-141" in rules


def test_ps141_silent_with_mermaid_demo(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _full_compliant_readme().replace(
        "## Demo\n\n![Hilbert](docs/hilbert.png)",
        "## Demo\n\n```mermaid\ngraph TD\nA-->B\n```",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-141" not in rules


def test_ps142_fires_when_architecture_section_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        _full_compliant_readme().replace(
            "## Architecture\n\n```\ndemo/\n├── core/\n│   └── __init__.py\n└── cli/\n```\n\n",
            "",
        )
    )
    rules = _violations_for(repo, "demo")
    assert "PS-142" in rules


def test_ps142_fires_when_architecture_section_has_no_diagram(tmp_path):
    # Architecture lacks a diagram AND Demo also lacks one — without
    # both being empty, PS-142's "one diagram is enough" fallback kicks
    # in and suppresses the violation.
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _full_compliant_readme()
    body = body.replace(
        "## Architecture\n\n```\ndemo/\n├── core/\n│   └── __init__.py\n└── cli/\n```",
        "## Architecture\n\nThis package is a flat single module.",
    )
    body = body.replace(
        "## Demo\n\n![Hilbert](docs/hilbert.png)",
        "## Demo\n\nLook at this cool thing.",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-142" in rules


def test_ps142_silent_with_filetree(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_full_compliant_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-142" not in rules


# REGRESSION (PS-142 truncation): the checker used to read only the first
# 16384 chars of a README, so a perfectly present `## Architecture` section
# living past that offset was reported as "missing mandatory
# `## Architecture`" — a false positive shipped to the whole fleet. A check
# that cannot see the whole input must not report ABSENCE.
_OLD_README_WINDOW = 16384


def _readme_structure_details(repo: Path, rule: str) -> list[str]:
    """Return the detail strings `check_readme_structure` emitted for `rule`."""
    from scitex_dev._cli.audit._project._audit import Violation
    from scitex_dev._cli.audit._project._check_readme_structure import (
        check_readme_structure,
    )

    out: list = []
    check_readme_structure(repo, Violation, out)
    return [v.detail for v in out if v.rule == rule]


def _readme_with_architecture_past_old_window() -> str:
    """A compliant README padded so `## Architecture` lands past 16 KiB.

    Canonical section order is preserved, so PS-143 must stay silent too.
    """
    body = _full_compliant_readme()
    filler = "\nPadding line to push later sections past the old window.\n" * 400
    return body.replace("## Architecture\n", filler + "\n## Architecture\n", 1)


@pytest.fixture
def repo_with_late_architecture(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_readme_with_architecture_past_old_window())
    return repo


def test_fixture_actually_places_architecture_past_the_old_window():
    # Arrange: guards the regression fixture itself — if padding ever stops
    # pushing Architecture past 16 KiB, the tests below pass vacuously.
    # Act
    body = _readme_with_architecture_past_old_window()
    # Assert
    assert body.index("## Architecture") > _OLD_README_WINDOW


def test_ps142_silent_when_architecture_sits_past_the_old_16kib_window(
    repo_with_late_architecture,
):
    # Arrange
    repo = repo_with_late_architecture
    # Act
    rules = _violations_for(repo, "demo")
    # Assert
    assert "PS-142" not in rules


def test_ps143_silent_when_sections_sit_past_the_old_16kib_window(
    repo_with_late_architecture,
):
    # Arrange
    repo = repo_with_late_architecture
    # Act
    rules = _violations_for(repo, "demo")
    # Assert
    assert "PS-143" not in rules


def test_ps142_still_fires_when_architecture_genuinely_missing_in_long_readme(
    tmp_path,
):
    # CONTROL for the truncation fix: proves the window was removed, not the
    # rule weakened. A LONG README (past the old 16 KiB boundary) that really
    # has no `## Architecture` must still be reported as missing.
    # Arrange
    repo = _make_repo(tmp_path, "demo")
    body = _readme_with_architecture_past_old_window().replace(
        "## Architecture\n\n```\ndemo/\n├── core/\n│   └── __init__.py\n└── cli/\n```\n\n",
        "",
    )
    (repo / "README.md").write_text(body)
    # Act
    rules = _violations_for(repo, "demo")
    # Assert
    assert "PS-142" in rules


def test_ps142_fires_when_late_architecture_section_body_is_empty(tmp_path):
    # Proves the late section is actually PARSED, not merely located: an
    # `## Architecture` past the old window with no diagram in its body (and
    # no Demo/Quick Start visual fallback) must report the body violation.
    # Arrange
    repo = _make_repo(tmp_path, "demo")
    body = _readme_with_architecture_past_old_window()
    body = body.replace(
        "## Architecture\n\n```\ndemo/\n├── core/\n│   └── __init__.py\n└── cli/\n```",
        "## Architecture\n",
    )
    body = body.replace(
        "## Demo\n\n![Hilbert](docs/hilbert.png)",
        "## Demo\n\nLook at this cool thing.",
    )
    (repo / "README.md").write_text(body)
    # Act
    details = _readme_structure_details(repo, "PS-142")
    # Assert
    assert any("no diagram" in d for d in details), details


def test_read_readme_returns_whole_file_not_a_head_slice(tmp_path):
    # Arrange
    from scitex_dev._cli.audit._project._readme_structure_shared import read_readme

    readme = tmp_path / "README.md"
    text = "# demo\n\n" + ("x" * 40000) + "\n\n## Architecture\n\n```mermaid\nA-->B\n```\n"
    readme.write_text(text)
    # Act
    got = read_readme(readme)
    # Assert
    assert got == text


def test_ps143_fires_when_architecture_appears_before_installation(tmp_path):
    # Updated 2026-05: Demo / Quick Start are now allowed BEFORE
    # Installation (Quick Start lives between Problem-and-Solution and
    # Installation per the new canonical order). The misordering this
    # test now checks is Architecture before Installation.
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        _README_HEADER
        + _good_pas_table()
        + "## Demo\n\n![x](y.png)\n\n"
        + "## Architecture\n\n```\nx/\n├── a\n│   └── b\n```\n\n"
        + "## Installation\n\npip install demo\n\n"
        + "## 2 Interfaces\n\nx\n\n"
        + "## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-143" in rules


def test_ps143_silent_on_canonical_order(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_full_compliant_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-143" not in rules


def test_ps144_fires_when_cell_has_no_bold(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _full_compliant_readme().replace(
        "| 1 | **Hilbert** under-doubles positive freqs at low f0/fs. | "
        "**Hard-step mask** brings the analytic-signal envelope back to scipy parity at every fs. |",
        "| 1 | Hilbert under-doubles positive freqs at low f0/fs. | "
        "Hard-step mask matches scipy. |",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-144" in rules


def test_ps144_fires_when_entire_cell_is_bold(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _full_compliant_readme().replace(
        "| 1 | **Hilbert** under-doubles positive freqs at low f0/fs. | "
        "**Hard-step mask** brings the analytic-signal envelope back to scipy parity at every fs. |",
        "| 1 | **Hilbert under-doubles positive freqs at low f0/fs.** | "
        "**Hard-step mask matches scipy.** |",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-144" in rules


def test_ps144_fires_when_cell_too_long(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    long_text = "x " * 110  # 220+ chars
    body = _full_compliant_readme().replace(
        "| 1 | **Hilbert** under-doubles positive freqs at low f0/fs. | "
        "**Hard-step mask** brings the analytic-signal envelope back to scipy parity at every fs. |",
        f"| 1 | **Hilbert** {long_text} | **scipy** {long_text} |",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-144" in rules


def test_ps144_silent_on_well_formed_cell(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_full_compliant_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-144" not in rules


# ---------------------------------------------------------------------------
# PS-152 / PS-153 / PS-154 / PS-155 — extended README structure rules
# ---------------------------------------------------------------------------


_GOOD_BADGES_BLOCK = (
    "<!-- scitex-badges:start -->\n"
    '<p align="center">'
    '<a href="x"><img src="https://img.shields.io/pypi/v/x" alt="PyPI"></a>'
    "</p>\n"
    '<p align="center">'
    '<a href="x"><img src="https://img.shields.io/badge/tests-x" alt="Tests"></a>'
    "</p>\n"
    "<!-- scitex-badges:end -->\n\n"
)

_GOOD_INSTALL = '## Installation\n\n```bash\nuv pip install "demo[all]"\n```\n\n'

_GOOD_ARCH_MERMAID = "## Architecture\n\n```mermaid\nflowchart LR\n    A --> B\n```\n\n"


def _clean_readme():
    """README that satisfies PS-141..148 + PS-152..155."""
    return (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n![Hilbert](docs/hilbert.png)\n\n"
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + "## 2 Interfaces\n\nPython API and CLI.\n\n"
        + "## Part of SciTeX\n\nPart of SciTeX.\n"
    )


# ---- PS-152: split Problem / Solution -----------------------------------


def test_ps152_fires_on_split_problem_solution(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        _README_HEADER
        + "## Problem\n\nThings hurt.\n\n"
        + "## Solution\n\nWe fix them.\n\n"
        + "## Demo\n\n![x](y.png)\n\n"
        + "## Installation\n\n```bash\nuv pip install demo\n```\n\n"
        + "## Architecture\n\n```mermaid\nflowchart LR\nA-->B\n```\n\n"
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-152" in rules


def test_ps152_fires_on_problem_only(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        _README_HEADER
        + "## Problem\n\nThings hurt.\n\n"
        + "## Demo\n\n![x](y.png)\n\n"
        + "## Installation\n\n```bash\nuv pip install demo\n```\n\n"
        + "## Architecture\n\n```mermaid\nflowchart LR\nA-->B\n```\n\n"
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-152" in rules


def test_ps152_silent_on_merged_problem_and_solution(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_clean_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-152" not in rules


# ---- PS-153: Architecture file-tree without mermaid ---------------------


def test_ps153_fires_when_architecture_has_filetree_without_mermaid(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # _full_compliant_readme() uses a pure file-tree Architecture body.
    (repo / "README.md").write_text(_full_compliant_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-153" in rules


def test_ps153_silent_when_architecture_is_mermaid(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_clean_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-153" not in rules


# ---- PS-154: Installation canonical form --------------------------------


def test_ps154_fires_when_no_uv_pip_install_line(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # _full_compliant_readme() uses `pip install demo`, not `uv pip install`.
    (repo / "README.md").write_text(_full_compliant_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-154" in rules


def test_ps154_fires_when_extras_table_outside_details(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        _README_HEADER
        + _good_pas_table()
        + "## Demo\n\n![x](y.png)\n\n"
        + "## Installation\n\n"
        + "```bash\nuv pip install demo\n```\n\n"
        + "| extra | description |\n"
        + "|-------|-------------|\n"
        + "| all   | everything  |\n\n"
        + _GOOD_ARCH_MERMAID
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-154" in rules


def test_ps154_silent_on_canonical_installation(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_clean_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-154" not in rules


def test_ps154_silent_when_extras_table_inside_details(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        _README_HEADER
        + _good_pas_table()
        + "## Demo\n\n![x](y.png)\n\n"
        + "## Installation\n\n"
        + "```bash\nuv pip install demo\n```\n\n"
        + "<details><summary>Extras</summary>\n\n"
        + "| extra | description |\n"
        + "|-------|-------------|\n"
        + "| all   | everything  |\n\n"
        + "</details>\n\n"
        + _GOOD_ARCH_MERMAID
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-154" not in rules


# ---- PS-155: badge row layout -------------------------------------------


def test_ps155_fires_when_badge_block_has_no_p_center_rows(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # _README_HEADER has an empty <!-- scitex-badges:start/end --> block
    # (zero <p align="center"> opening tags inside it).
    (repo / "README.md").write_text(_full_compliant_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-155" in rules


def test_ps155_fires_when_badge_block_has_one_row(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    header = (
        "# demo\n\n"
        "<!-- scitex-badges:start -->\n"
        '<p align="center"><img src="x" alt="PyPI"></p>\n'
        "<!-- scitex-badges:end -->\n\n"
    )
    body = (
        header
        + _good_pas_table()
        + "## Demo\n\n![x](y.png)\n\n"
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-155" in rules


def test_ps155_silent_on_two_p_center_rows(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_clean_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-155" not in rules


# ---- PS-159: figure / table numbering must be 1, 2, 3, ... -------------


def _readme_with_captions(figure_captions: str = "", table_captions: str = "") -> str:
    """README that satisfies most rules; caller injects caption text."""
    return (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\nSee figure below.\n\n"
        + figure_captions
        + _GOOD_INSTALL
        + "## Architecture\n\n"
        + "```mermaid\nflowchart LR\n    A --> B\n```\n\n"
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + table_captions
        + "## 2 Interfaces\n\nPython API and CLI.\n\n"
        + "## Part of SciTeX\n\nPart of SciTeX.\n"
    )


def test_ps159_fires_when_figure_1_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # Mermaid arch block exists; caption uses Figure 2 and Figure 3 — no Figure 1.
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n"
        + '<img src="docs/a.png" alt="a">\n\n'
        + '<p align="center"><sub><b>Figure 2.</b> A.</sub></p>\n\n'
        + '<img src="docs/b.png" alt="b">\n\n'
        + '<p align="center"><sub><b>Figure 3.</b> B.</sub></p>\n\n'
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    # Actually drop Figure 1 to make the test meaningful:
    body = body.replace(
        '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n', ""
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-159" in rules


def test_ps159_fires_when_figure_numbers_have_gap(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n"
        + '<img src="docs/a.png" alt="a">\n\n'
        + '<p align="center"><sub><b>Figure 1.</b> A.</sub></p>\n\n'
        + '<img src="docs/b.png" alt="b">\n\n'
        + '<p align="center"><sub><b>Figure 3.</b> B.</sub></p>\n\n'
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-159" in rules


def test_ps159_fires_when_figure_number_duplicated(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n"
        + '<img src="docs/a.png" alt="a">\n\n'
        + '<p align="center"><sub><b>Figure 1.</b> A.</sub></p>\n\n'
        + '<img src="docs/b.png" alt="b">\n\n'
        + '<p align="center"><sub><b>Figure 2.</b> B.</sub></p>\n\n'
        + '<img src="docs/c.png" alt="c">\n\n'
        + '<p align="center"><sub><b>Figure 2.</b> C.</sub></p>\n\n'
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-159" in rules


def test_ps159_silent_on_sequential_figure_numbers(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n"
        + '<img src="docs/a.png" alt="a">\n\n'
        + '<p align="center"><sub><b>Figure 1.</b> A.</sub></p>\n\n'
        + '<img src="docs/b.png" alt="b">\n\n'
        + '<p align="center"><sub><b>Figure 2.</b> B.</sub></p>\n\n'
        + '<img src="docs/c.png" alt="c">\n\n'
        + '<p align="center"><sub><b>Figure 3.</b> C.</sub></p>\n\n'
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 4.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-159" not in rules


def test_ps159_silent_when_no_figures_or_tables(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # _clean_readme has a mermaid arch block (captionable figure) but no
    # `<b>Figure N.</b>` captions at all — PS-159 stays quiet (it only
    # fires when at least one numbered caption exists). PS-160 is the
    # one that catches the missing caption.
    (repo / "README.md").write_text(_clean_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-159" not in rules


# ---- PS-160: every figure / table needs a caption ----------------------


def test_ps160_fires_when_mermaid_block_has_no_caption(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # _clean_readme has a mermaid arch block but no Figure caption.
    (repo / "README.md").write_text(_clean_readme())
    rules = _violations_for(repo, "demo")
    assert "PS-160" in rules


def test_ps160_fires_when_img_data_figure_has_no_caption(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n"
        + '<img src="docs/hilbert.png" alt="hilbert">\n\n'
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    # 2 captionable (img + mermaid) but only 1 caption.
    assert "PS-160" in rules


def test_ps160_silent_when_every_figure_has_caption(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\n"
        + '<img src="docs/hilbert.png" alt="hilbert">\n\n'
        + '<p align="center"><sub><b>Figure 1.</b> Hilbert.</sub></p>\n\n'
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 2.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-160" not in rules


def test_ps160_silent_for_pas_and_details_tables(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # P&S table + a <details>-wrapped extras table, plus mermaid arch
    # WITH a caption. Should be PS-160-silent (both tables are exempt;
    # mermaid is captioned).
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\nNo figures here.\n\n"
        + '## Installation\n\n```bash\nuv pip install "demo[all]"\n```\n\n'
        + "<details><summary>Extras</summary>\n\n"
        + "| extra | description |\n|-------|-------------|\n| all | x |\n\n"
        + "</details>\n\n"
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-160" not in rules


def test_ps160_fires_when_pipe_table_has_no_caption(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _GOOD_BADGES_BLOCK
        + _good_pas_table()
        + "## Demo\n\nSome data:\n\n"
        + "| col1 | col2 |\n|------|------|\n| a | b |\n\n"
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-160" in rules


# ---------------------------------------------------------------------------
# PS-107 / PS-109 / PS-110 / PS-111 / PS-112 — README convention rules
# ---------------------------------------------------------------------------


def test_ps107_fires_on_missing_sections(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # Body is over 200 bytes but lacks any of the required H2 sections.
    (repo / "README.md").write_text(
        "# demo\n\nA package without the canonical sections. " + ("x " * 100)
    )
    rules = _violations_for(repo, "demo")
    assert "PS-107" in rules


def test_ps107_silent_on_canonical_readme(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_GOOD_README)
    rules = _violations_for(repo, "demo")
    assert "PS-107" not in rules


def test_ps107_accepts_quickstart_one_word(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _GOOD_README.replace("## Quick Start", "## Quickstart")
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-107" not in rules


def test_ps107_silent_when_readme_too_small(tmp_path):
    """Tiny placeholder READMEs should not be audited."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text("# demo\n")
    rules = _violations_for(repo, "demo")
    assert "PS-107" not in rules


def test_ps109_fires_when_pypi_badge_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _GOOD_README.replace(
        "[![PyPI](https://badge.fury.io/py/demo.svg)](https://pypi.org/project/demo/)\n",
        "",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-109" in rules


def test_ps109_silent_with_shields_pypi_badge(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _GOOD_README.replace(
        "https://badge.fury.io/py/demo.svg",
        "https://img.shields.io/pypi/v/demo.svg",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-109" not in rules


def test_ps110_fires_when_four_freedoms_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _GOOD_README.split(">Four Freedoms")[0]
    (repo / "README.md").write_text(body + ("filler " * 30))
    rules = _violations_for(repo, "demo")
    assert "PS-110" in rules


def test_ps110_silent_with_four_freedoms(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_GOOD_README)
    rules = _violations_for(repo, "demo")
    assert "PS-110" not in rules


def test_ps111_fires_with_banned_email(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_GOOD_README + "\nContact: ywatanabe@scitex.ai\n")
    rules = _violations_for(repo, "demo")
    assert "PS-111" in rules


def test_ps111_silent_without_banned_email(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_GOOD_README)
    rules = _violations_for(repo, "demo")
    assert "PS-111" not in rules


def test_ps112_fires_when_logo_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _GOOD_README.replace(
        '<p align="center"><img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400"></p>\n\n',
        "",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-112" in rules


def test_ps112_silent_with_assets_images_path(tmp_path):
    """docs/assets/images/scitex-logo-*.png path is also valid."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = _GOOD_README.replace(
        "docs/scitex-logo-blue-cropped.png",
        "docs/assets/images/scitex-logo-blue-cropped.png",
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-112" not in rules


def test_readme_rules_silent_when_readme_missing(tmp_path):
    """No README → all PS-107/109/110/111/112 stay quiet (PS-101 covers it)."""
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    rules = _violations_for(repo, "demo")
    for code in ("PS-107", "PS-109", "PS-110", "PS-111", "PS-112"):
        assert code not in rules


# ---------------------------------------------------------------------------
# PS-161: codecov.yml coverage target must be >= 90% (not auto)
# ---------------------------------------------------------------------------


def test_ps161_silent_when_target_is_90(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "codecov.yml").write_text(
        "coverage:\n"
        "  status:\n"
        "    project:\n"
        "      default:\n"
        "        target: 90%\n"
        "    patch:\n"
        "      default:\n"
        "        target: 90%\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-161" not in rules


def test_ps161_fires_when_project_target_below_90(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "codecov.yml").write_text(
        "coverage:\n  status:\n    project:\n      default:\n        target: 80%\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-161" in rules


def test_ps161_fires_when_target_is_auto(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "codecov.yml").write_text(
        "coverage:\n  status:\n    project:\n      default:\n        target: auto\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-161" in rules


def test_ps161_silent_when_codecov_yml_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    rules = _violations_for(repo, "demo")
    assert "PS-161" not in rules


def test_ps161_fires_when_patch_target_below_90(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "codecov.yml").write_text(
        "coverage:\n"
        "  status:\n"
        "    project:\n"
        "      default:\n"
        "        target: 90%\n"
        "    patch:\n"
        "      default:\n"
        "        target: 50%\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS-161" in rules


# ---------------------------------------------------------------------------
# PS-162: README badge block must contain a Codecov badge
# ---------------------------------------------------------------------------


_BADGES_BLOCK_WITH_CODECOV = (
    "<!-- scitex-badges:start -->\n"
    '<p align="center">'
    '<a href="x"><img src="https://img.shields.io/pypi/v/demo" alt="PyPI"></a>'
    "</p>\n"
    '<p align="center">'
    '<a href="https://codecov.io/gh/owner/demo">'
    '<img src="https://codecov.io/gh/owner/demo/branch/develop/graph/badge.svg" '
    'alt="Coverage"></a>'
    '<a href="https://demo.readthedocs.io/en/latest/">'
    '<img src="https://img.shields.io/readthedocs/demo?label=Read%20the%20Docs" '
    'alt="Read the Docs"></a>'
    "</p>\n"
    "<!-- scitex-badges:end -->\n\n"
)

_BADGES_BLOCK_WITHOUT_CODECOV = (
    "<!-- scitex-badges:start -->\n"
    '<p align="center">'
    '<a href="x"><img src="https://img.shields.io/pypi/v/demo" alt="PyPI"></a>'
    "</p>\n"
    '<p align="center">'
    '<a href="https://demo.readthedocs.io/en/latest/">'
    '<img src="https://img.shields.io/readthedocs/demo?label=Read%20the%20Docs" '
    'alt="Read the Docs"></a>'
    "</p>\n"
    "<!-- scitex-badges:end -->\n\n"
)

_BADGES_BLOCK_WITHOUT_RTD = (
    "<!-- scitex-badges:start -->\n"
    '<p align="center">'
    '<a href="x"><img src="https://img.shields.io/pypi/v/demo" alt="PyPI"></a>'
    "</p>\n"
    '<p align="center">'
    '<a href="https://codecov.io/gh/owner/demo">'
    '<img src="https://codecov.io/gh/owner/demo/branch/develop/graph/badge.svg" '
    'alt="Coverage"></a>'
    "</p>\n"
    "<!-- scitex-badges:end -->\n\n"
)

_BADGES_BLOCK_RTD_OWN = (
    "<!-- scitex-badges:start -->\n"
    '<p align="center">'
    '<a href="x"><img src="https://img.shields.io/pypi/v/demo" alt="PyPI"></a>'
    "</p>\n"
    '<p align="center">'
    '<a href="https://codecov.io/gh/owner/demo">'
    '<img src="https://codecov.io/gh/owner/demo/branch/develop/graph/badge.svg" '
    'alt="Coverage"></a>'
    '<a href="https://demo.readthedocs.io/en/latest/">'
    '<img src="https://readthedocs.org/projects/demo/badge/?version=latest" '
    'alt="Docs"></a>'
    "</p>\n"
    "<!-- scitex-badges:end -->\n\n"
)


def _readme_with_custom_badges(block: str) -> str:
    return (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + block
        + _good_pas_table()
        + "## Demo\n\n![Hilbert](docs/hilbert.png)\n\n"
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nPython API and CLI.\n\n"
        + "## Part of SciTeX\n\nPart of SciTeX.\n"
    )


def test_ps162_silent_when_codecov_badge_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        _readme_with_custom_badges(_BADGES_BLOCK_WITH_CODECOV)
    )
    rules = _violations_for(repo, "demo")
    assert "PS-162" not in rules


def test_ps162_fires_when_codecov_badge_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        _readme_with_custom_badges(_BADGES_BLOCK_WITHOUT_CODECOV)
    )
    rules = _violations_for(repo, "demo")
    assert "PS-162" in rules


def test_ps162_silent_when_badges_block_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    # _full_compliant_readme assumes no badges block — use a minimal
    # README missing the markers entirely.
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _good_pas_table()
        + "## Demo\n\n![Hilbert](docs/hilbert.png)\n\n"
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-162" not in rules


# ---------------------------------------------------------------------------
# PS-163: README badge block must contain a Read-the-Docs badge
# ---------------------------------------------------------------------------


def test_ps163_silent_when_shields_rtd_badge_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        _readme_with_custom_badges(_BADGES_BLOCK_WITH_CODECOV)
    )
    rules = _violations_for(repo, "demo")
    assert "PS-163" not in rules


def test_ps163_silent_when_readthedocs_org_badge_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(_readme_with_custom_badges(_BADGES_BLOCK_RTD_OWN))
    rules = _violations_for(repo, "demo")
    assert "PS-163" not in rules


def test_ps163_fires_when_rtd_badge_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    (repo / "README.md").write_text(
        _readme_with_custom_badges(_BADGES_BLOCK_WITHOUT_RTD)
    )
    rules = _violations_for(repo, "demo")
    assert "PS-163" in rules


def test_ps163_silent_when_badges_block_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _make_repo(tmp_path, "demo")
    body = (
        "# demo\n\n"
        '<p align="center"><img src="docs/scitex-logo.png" alt="logo"></p>\n\n'
        + _good_pas_table()
        + "## Demo\n\n![Hilbert](docs/hilbert.png)\n\n"
        + _GOOD_INSTALL
        + _GOOD_ARCH_MERMAID
        + '<p align="center"><sub><b>Figure 1.</b> arch.</sub></p>\n\n'
        + "## 2 Interfaces\n\nx\n\n## Part of SciTeX\n\nx\n"
    )
    (repo / "README.md").write_text(body)
    rules = _violations_for(repo, "demo")
    assert "PS-163" not in rules


# ---------------------------------------------------------------------------
# CAPABILITY knob -> no-umbrella gates PS-501 / PS-503.
# (Split out of the former _project/test__capability_knob.py orphan; these
# exercise audit_project's capability-filtering path, whose mirror src is
# this module's _project/_audit.py.) Operator directive 2026-06-22.
# ---------------------------------------------------------------------------


def _write_caps_config(repo: Path, capabilities: list[str] | None) -> None:
    """Write a `.scitex/dev/config.yaml` for `repo`, optionally with caps."""
    cfg_dir = repo / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    body = "project-type:\n  - pip\n"
    if capabilities is not None:
        body += "audit:\n  capabilities:\n"
        for cap in capabilities:
            body += f"    - {cap}\n"
    (cfg_dir / "config.yaml").write_text(body, encoding="utf-8")


def _make_ps501_repo(tmp_path: Path, capabilities: list[str] | None) -> Path:
    """A package whose examples/01_*.py has main() but no @stx.session (PS-501)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "01_demo.py").write_text(
        'def main():\n    print("hi")\n\n\nif __name__ == "__main__":\n    main()\n',
        encoding="utf-8",
    )
    _write_caps_config(tmp_path, capabilities)
    return tmp_path


def _capknob_audit_json(repo: Path, rules: set[str]) -> dict:
    import contextlib as _contextlib
    import io as _io
    import json as _json2

    buf = _io.StringIO()
    with _contextlib.redirect_stdout(buf):
        audit_project(
            "demo-pkg", repo=repo, json_out=True, rules=rules, severity="info"
        )
    return _json2.loads(buf.getvalue())


def test_ps501_fires_without_capability(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=None)
    # Act
    payload = _capknob_audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert {v["rule"] for v in payload["violations"]} == {"PS-501"}


def test_ps501_not_skipped_without_capability(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=None)
    # Act
    payload = _capknob_audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert payload["capability_skips"] == []


def test_ps501_dropped_with_no_umbrella(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    payload = _capknob_audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert payload["violations"] == []


def test_ps501_skip_is_clean_exit_with_no_umbrella(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    payload = _capknob_audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert payload["exit_code"] == 0


def test_ps501_skip_is_recorded_visibly_in_json(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    payload = _capknob_audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert {"rule": "PS-501", "capability": "no-umbrella"} in payload[
        "capability_skips"
    ]


def test_ps501_skip_emits_human_notice(tmp_path, capsys):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    audit_project("demo-pkg", repo=repo, rules={"PS-501"}, severity="info")
    # Assert
    assert "skipped (declared capability: no-umbrella)" in capsys.readouterr().err


def test_no_mcp_does_not_skip_ps501(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-mcp"])
    # Act
    payload = _capknob_audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert {v["rule"] for v in payload["violations"]} == {"PS-501"}
