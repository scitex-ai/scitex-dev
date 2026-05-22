"""Tests for PS-148 — unresolved git conflict marker detection.

Real fixtures only (NO mocks, per STX-NM): every test writes actual
files under tmp_path and runs the real check function. Conflict
markers are built from `chr()` so this test file's own source never
contains literal marker lines (keeping it PS-148-clean).
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._audit import RULES, Violation
from scitex_dev._cli.audit._project._check_conflict_markers import (
    _conflict_lines,
    check_ps148_conflict_markers,
)

_OPEN_MARK = chr(60) * 7  # seven '<'
_DIV_MARK = chr(61) * 7  # seven '='
_CLOSE_MARK = chr(62) * 7  # seven '>'


def _conflict_block() -> str:
    """A realistic three-marker conflict block."""
    return f"{_OPEN_MARK} HEAD\nx = 1\n{_DIV_MARK}\nx = 2\n{_CLOSE_MARK} their-branch\n"


def _make_repo(tmp_path: Path) -> Path:
    """Minimal repo skeleton with an importable src package."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    pkg = tmp_path / "src" / "x"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    return tmp_path


# --------------------------------------------------------------------- #
# _conflict_lines — line-level detector                                 #
# --------------------------------------------------------------------- #


def test_conflict_lines_detects_open_divider_and_close():
    # Arrange
    text = _conflict_block()
    # Act
    hits = _conflict_lines(text)
    # Assert
    assert hits == [(1, "open"), (3, "divider"), (5, "close")]


def test_conflict_lines_ignores_markdown_horizontal_rules():
    # Arrange
    text = "---\n***\n___\n- - -\n"
    # Act
    hits = _conflict_lines(text)
    # Assert
    assert hits == []


def test_conflict_lines_ignores_long_equals_table_divider():
    # Arrange — eight '=' is a table divider, not the 7-char git form
    text = (_DIV_MARK + "=") + "\n"
    # Act
    hits = _conflict_lines(text)
    # Assert
    assert hits == []


def test_conflict_lines_ignores_equals_heading_with_text():
    # Arrange — `=== section ===` is a docstring heading, not a divider
    text = "=== section ===\n"
    # Act
    hits = _conflict_lines(text)
    # Assert
    assert hits == []


def test_conflict_lines_requires_space_after_open_marker():
    # Arrange — seven '<' with no trailing space is not a conflict open
    text = _OPEN_MARK + "nospace\n"
    # Act
    hits = _conflict_lines(text)
    # Assert
    assert hits == []


# --------------------------------------------------------------------- #
# check_ps148_conflict_markers — repo-level check                       #
# --------------------------------------------------------------------- #


def test_ps148_fires_on_markers_in_python_string(tmp_path):
    # Arrange — markers hidden in a triple-quoted string (ruff-invisible)
    repo = _make_repo(tmp_path)
    (repo / "src" / "x" / "bad.py").write_text(
        'SQL = """\n' + _conflict_block() + '"""\n'
    )
    out: list = []
    # Act
    check_ps148_conflict_markers(repo, Violation, out)
    # Assert
    assert [v.rule for v in out] == ["PS-148"]


def test_ps148_reports_offending_file_path(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    bad = repo / "src" / "x" / "bad.py"
    bad.write_text(_conflict_block())
    out: list = []
    # Act
    check_ps148_conflict_markers(repo, Violation, out)
    # Assert
    assert out[0].where == str(bad)


def test_ps148_fires_on_markers_in_markdown_doc(tmp_path):
    # Arrange — markers inside a fenced code block in docs/
    repo = _make_repo(tmp_path)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("```\n" + _conflict_block() + "```\n")
    out: list = []
    # Act
    check_ps148_conflict_markers(repo, Violation, out)
    # Assert
    assert [v.rule for v in out] == ["PS-148"]


def test_ps148_silent_on_clean_repo(tmp_path):
    # Arrange — a repo with ordinary files and a markdown rule
    repo = _make_repo(tmp_path)
    (repo / "src" / "x" / "ok.py").write_text("x = 1\n")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Title\n\n---\n\nbody\n")
    out: list = []
    # Act
    check_ps148_conflict_markers(repo, Violation, out)
    # Assert
    assert out == []


def test_ps148_skips_sphinx_html_generated_tree(tmp_path):
    # Arrange — generated docs bundle must not be scanned
    repo = _make_repo(tmp_path)
    gen = repo / "src" / "x" / "_sphinx_html"
    gen.mkdir(parents=True)
    (gen / "page.json").write_text(_conflict_block())
    out: list = []
    # Act
    check_ps148_conflict_markers(repo, Violation, out)
    # Assert
    assert out == []


def test_ps148_rule_is_registered_at_error_severity():
    # Arrange
    rule = RULES.get("PS-148")
    # Act
    severity = rule.severity if rule else None
    # Assert
    assert severity == "E"
