"""Tests for the project-structure auditor (PS<n> rules).

Each rule has at least one positive (rule fires on a synthetic broken repo)
and one negative (rule stays silent on a clean repo) test.
"""

from __future__ import annotations

from pathlib import Path


from scitex_dev._cli_audit_project import RULES, audit_project
from scitex_dev._cli_audit_project._audit import (
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
    return tmp_path


def _violations_for(repo: Path, name: str) -> list[str]:
    """Run the rule check functions directly and return the rule codes that fired."""
    out: list = []
    _check_top_level(repo, out)
    _check_mirror(repo, name, out)
    _check_tests_subdir_convention(repo, name, out)
    _check_docs_structure(repo, out)
    _check_placeholder_tests(repo, out)
    return [v.rule for v in out]


# ---------------------------------------------------------------------------
# Sanity / discovery
# ---------------------------------------------------------------------------


def test_rules_have_unique_codes_and_sections():
    codes = list(RULES.keys())
    assert len(codes) == len(set(codes)), "duplicate rule codes"
    sections = {r.section for r in RULES.values()}
    assert sections >= {"§1", "§2", "§3", "§4"}


def test_rule_namespace_is_ps():
    assert all(c.startswith("PS") for c in RULES)


# ---------------------------------------------------------------------------
# §1 Top-level layout
# ---------------------------------------------------------------------------


def test_ps101_fires_when_pyproject_missing(tmp_path):
    # Bare dir, no pyproject
    rules = _violations_for(tmp_path, "demo")
    assert "PS101" in rules


def test_ps102_fires_on_forbidden_top_level_dir(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "mgmt").mkdir()
    rules = _violations_for(repo, "demo-pkg")
    assert "PS102" in rules


def test_ps103_fires_on_top_level_junk(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "tmp_quick.py").write_text("x = 1\n")
    rules = _violations_for(repo, "demo-pkg")
    assert "PS103" in rules


def test_ps104_fires_on_playground(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / ".playground").mkdir()
    rules = _violations_for(repo, "demo-pkg")
    assert "PS104" in rules


# ---------------------------------------------------------------------------
# §2 src ↔ tests mirror
# ---------------------------------------------------------------------------


def test_ps201_fires_when_tests_pkg_parent_missing(tmp_path):
    """src/<pkg>/ exists, tests/ exists, but no tests/<pkg>/ parent."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "foo.py").write_text("def f(): pass\n")
    (tmp_path / "tests").mkdir()
    rules = _violations_for(tmp_path, "demo")
    assert "PS201" in rules


def test_ps202_fires_on_unmatched_subdir(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "sub").mkdir()
    (repo / "src" / "demo" / "sub" / "x.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS202" in rules


def test_ps203_fires_on_loose_top_level_test(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "test__cache.py").write_text("def test_x(): assert True\n")
    rules = _violations_for(repo, "demo")
    assert "PS203" in rules


def test_ps203_silent_for_meta_test(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "test_examples.py").write_text("def test_x(): assert True\n")
    rules = _violations_for(repo, "demo")
    assert "PS203" not in rules


def test_ps204_fires_on_orphan_test(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_nonexistent.py").write_text(
        "def test_x(): assert True\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS204" in rules


def test_ps205_fires_on_wrong_prefix(tmp_path):
    """Source `_foo.py` (private) tested by `test_foo.py` (single _) is wrong."""
    repo = _make_repo(tmp_path, "demo")
    (repo / "src" / "demo" / "_foo.py").write_text("def f(): pass\n")
    (repo / "tests" / "demo" / "test_foo.py").write_text("def test_f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS205" in rules


def test_ps206_fires_on_placeholder_test(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_foo.py").write_text(
        "# Add your tests here\n"
        "if __name__ == '__main__':\n"
        "    import pytest; pytest.main([__file__])\n"
    )
    (repo / "src" / "demo" / "foo.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS206" in rules


def test_ps206_silent_when_real_test_present(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "demo" / "test_foo.py").write_text(
        "def test_f():\n    assert True\n"
    )
    (repo / "src" / "demo" / "foo.py").write_text("def f(): pass\n")
    rules = _violations_for(repo, "demo")
    assert "PS206" not in rules


# ---------------------------------------------------------------------------
# §3 tests/ subdir convention
# ---------------------------------------------------------------------------


def test_ps301_fires_on_top_level_htmlcov(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "htmlcov").mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS301" in rules


def test_ps302_fires_on_unrecognized_subdir(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "tests" / "weird_extra_dir").mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS302" in rules


def test_ps302_silent_for_known_categories(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    for sub in ["scripts", "examples", "skills", "agentic", "integration", "e2e"]:
        (repo / "tests" / sub).mkdir()
    rules = _violations_for(repo, "demo")
    assert "PS302" not in rules


def test_ps303_fires_on_example_without_test(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir()
    (repo / "examples" / "01_demo.py").write_text("print('demo')\n")
    rules = _violations_for(repo, "demo")
    assert "PS303" in rules


def test_ps303_silent_when_test_present(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "examples").mkdir()
    (repo / "examples" / "01_demo.py").write_text("print('demo')\n")
    (repo / "tests" / "examples").mkdir()
    (repo / "tests" / "examples" / "test_01_demo.py").write_text(
        "def test_x(): assert True\n"
    )
    rules = _violations_for(repo, "demo")
    assert "PS303" not in rules


# ---------------------------------------------------------------------------
# §4 docs/ structure
# ---------------------------------------------------------------------------


def test_ps401_fires_when_to_claude_not_gitignored(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "docs" / "to_claude").mkdir(parents=True)
    rules = _violations_for(repo, "demo")
    assert "PS401" in rules


def test_ps401_silent_when_to_claude_is_gitignored(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "docs" / "to_claude").mkdir(parents=True)
    (repo / ".gitignore").write_text("docs/to_claude/\n")
    rules = _violations_for(repo, "demo")
    assert "PS401" not in rules


# ---------------------------------------------------------------------------
# End-to-end via audit_project()
# ---------------------------------------------------------------------------


def test_audit_project_returns_2_when_repo_missing():
    # Pass an obviously-missing distribution and no repo override
    # → resolver fails, returns 2.
    rc = audit_project("nonexistent-pkg-zzz", repo=None)
    assert rc == 2


def test_audit_project_clean_repo_returns_0(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    rc = audit_project("demo", repo=repo)
    assert rc == 0


def test_audit_project_dirty_repo_returns_1(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "mgmt").mkdir()  # forbidden top-level dir
    rc = audit_project("demo", repo=repo)
    assert rc == 1


def test_audit_project_rule_filter_restricts(tmp_path):
    repo = _make_repo(tmp_path, "demo")
    (repo / "mgmt").mkdir()  # PS102
    (repo / "tmp_quick.py").write_text("x=1\n")  # PS103
    # JSON mode is easier to assert against:
    import json as _json
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit_project("demo", repo=repo, json_out=True, rules={"PS102"})
    payload = _json.loads(buf.getvalue())
    codes = {v["rule"] for v in payload["violations"]}
    assert codes == {"PS102"}
