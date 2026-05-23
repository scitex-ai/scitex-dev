"""Tests for RP-2xx — research-project scripts ↔ tests/scripts mirror.

Covers both the standalone check (`check_research_mirror`) and the
category-aware behaviour of `audit_project` for `project-type: research`
repos: package-publish PS rules are skipped, the RP mirror rules fire,
and clean research repos pass.

No mocks (NM001-003) — real temp repos built with `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._config import write_config
from scitex_dev._cli.audit._project._audit import audit_project
from scitex_dev._cli.audit._project._check_research_mirror import (
    check_research_mirror,
)


def _seed_research(repo: Path) -> None:
    """Minimal research repo: project-type config + scripts/ tree."""
    (repo / ".scitex/dev").mkdir(parents=True)
    write_config(repo, project_types=["research"])
    (repo / "scripts" / "analysis").mkdir(parents=True)
    (repo / "scripts" / "analysis" / "01_collect.py").write_text("x = 1\n")


def _violations(repo: Path) -> list:
    out: list = []
    check_research_mirror(repo, out)
    return out


def _rules(repo: Path) -> set[str]:
    return {v.rule for v in _violations(repo)}


# check_research_mirror — RP-201 -------------------------------------------


def test_missing_tests_scripts_parent_fires_rp201(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-201" in rules


def test_present_tests_scripts_parent_no_rp201(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-201" not in rules


def test_no_scripts_dir_is_noop(tmp_path):
    # Arrange
    (tmp_path / ".scitex/dev").mkdir(parents=True)
    write_config(tmp_path, project_types=["research"])
    # Act
    out = _violations(tmp_path)
    # Assert
    assert out == []


# check_research_mirror — RP-202 -------------------------------------------


def test_scripts_subdir_without_mirror_fires_rp202(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "scripts" / "utils").mkdir(parents=True)
    (tmp_path / "scripts" / "utils" / "_helpers.py").write_text("y = 2\n")
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-202" in rules


def test_fully_mirrored_scripts_no_rp202(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-202" not in rules


def test_makefile_subdir_skipped_for_rp202(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "scripts" / "makefile").mkdir(parents=True)
    (tmp_path / "scripts" / "makefile" / "_build.py").write_text("z = 3\n")
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-202" not in rules


# check_research_mirror — RP-204 -------------------------------------------


def test_orphan_test_fires_rp204(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "analysis" / "test_orphan.py").write_text(
        "def test_o():\n    assert True\n"
    )
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-204" in rules


def test_matched_test_no_rp204(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "analysis" / "test_01_collect.py").write_text(
        "def test_x():\n    assert True\n"
    )
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-204" not in rules


# check_research_mirror — RP-205 -------------------------------------------


def test_private_script_wrong_prefix_fires_rp205(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "scripts" / "utils").mkdir(parents=True)
    (tmp_path / "scripts" / "utils" / "_helpers.py").write_text("y = 2\n")
    tests_utils = tmp_path / "tests" / "scripts" / "utils"
    tests_utils.mkdir(parents=True)
    # Wrong: single-underscore test for a private source file.
    (tests_utils / "test_helpers.py").write_text("def test_y():\n    assert True\n")
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-205" in rules


def test_private_script_correct_prefix_no_rp205(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "scripts" / "utils").mkdir(parents=True)
    (tmp_path / "scripts" / "utils" / "_helpers.py").write_text("y = 2\n")
    tests_utils = tmp_path / "tests" / "scripts" / "utils"
    tests_utils.mkdir(parents=True)
    (tests_utils / "test__helpers.py").write_text("def test_y():\n    assert True\n")
    # Act
    rules = _rules(tmp_path)
    # Assert
    assert "RP-205" not in rules


# audit_project integration — category-aware skipping ----------------------


def _audit_rules(repo: Path) -> set[str]:
    """Run audit_project(json) and collect the violation rule codes."""
    import io
    import json
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        audit_project("demo-research", repo=repo, json_out=True, severity="warning")
    payload = json.loads(buf.getvalue())
    return {v["rule"] for v in payload["violations"]}


def test_research_audit_keeps_rp_mirror_rules(tmp_path):
    # Arrange
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "analysis" / "test_orphan.py").write_text(
        "def test_o():\n    assert True\n"
    )
    # Act
    rules = _audit_rules(tmp_path)
    # Assert
    assert "RP-204" in rules


def test_research_audit_skips_package_publish_ps_rules(tmp_path):
    # Arrange — research repo with NO README / badges / CHANGELOG / CLA.
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "analysis" / "test_01_collect.py").write_text(
        "def test_x():\n    assert True\n"
    )
    # Act
    rules = _audit_rules(tmp_path)
    # Assert — not a single PS-* package-publish rule fires for research.
    assert not any(r.startswith("PS-") for r in rules)


def test_clean_research_repo_passes(tmp_path):
    # Arrange — fully mirrored research repo.
    _seed_research(tmp_path)
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "analysis" / "test_01_collect.py").write_text(
        "def test_x():\n    assert True\n"
    )
    # Act
    rules = _audit_rules(tmp_path)
    # Assert
    assert rules == set()


def test_pip_repo_does_not_get_rp_rules(tmp_path):
    # Arrange — a pip repo with a scripts/ tree should NOT get RP findings
    # (RP rules route to research only).
    (tmp_path / ".scitex/dev").mkdir(parents=True)
    write_config(tmp_path, project_types=["pip"])
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-research"\n')
    (tmp_path / "src" / "demo_research").mkdir(parents=True)
    (tmp_path / "src" / "demo_research" / "__init__.py").write_text("")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "loose.py").write_text("a = 1\n")
    # Act
    rules = _audit_rules(tmp_path)
    # Assert
    assert not any(r.startswith("RP-") for r in rules)
