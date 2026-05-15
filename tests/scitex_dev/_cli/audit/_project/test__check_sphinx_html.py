"""Tests for `_check_sphinx_html.py` (PS-122 RTD-workflow detection).

PS-122 historically required ``.github/workflows/docs.yml`` by name.
After the ecosystem-wide workflow-rename (PS-164), the canonical
filename is descriptive (e.g. ``rtd-sphinx-build-on-ubuntu-latest.yml``).
PS-122 now detects the workflow by *content* — any workflow that runs
``sphinx-build`` / ``make html`` / references RTD satisfies the rule.

These tests cover the regression: a renamed workflow that still builds
sphinx HTML must NOT false-fire PS-122.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_sphinx_html import (
    _has_rtd_workflow,
    check_sphinx_html,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== fixtures =====


_SPHINX_CONF = "project = 'demo'\n"


_RENAMED_WORKFLOW = """\
name: docs

on:
  push:
    branches: [main, develop]

jobs:
  sphinx:
    name: rtd-sphinx-build-on-ubuntu-latest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[docs]"
      - name: Build Sphinx HTML
        run: sphinx-build -b html docs/sphinx docs/sphinx/_build/html
"""


_MAKE_HTML_WORKFLOW = """\
name: docs
on: [push]
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - run: make html
"""


_UNRELATED_WORKFLOW = """\
name: tests
on: [push]
jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - run: pytest
"""


def _make_pkg_with_sphinx(tmp_path: Path) -> Path:
    """Set up a repo with docs/sphinx/conf.py + bundled _sphinx_html/
    so PS-121 short-circuits and PS-122 is the only relevant rule."""
    (tmp_path / "docs" / "sphinx").mkdir(parents=True)
    (tmp_path / "docs" / "sphinx" / "conf.py").write_text(_SPHINX_CONF)
    pkg_html = tmp_path / "src" / "demo_pkg" / "_sphinx_html"
    pkg_html.mkdir(parents=True)
    (pkg_html / "index.html").write_text("<html/>")
    return tmp_path


# ===== _has_rtd_workflow =====


class TestHasRtdWorkflow:
    def test_renamed_workflow_with_sphinx_build_detected(self, tmp_path: Path) -> None:
        # Arrange
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "rtd-sphinx-build-on-ubuntu-latest.yml").write_text(_RENAMED_WORKFLOW)
        # Act
        result = _has_rtd_workflow(tmp_path)
        # Assert
        assert result is True

    def test_make_html_workflow_detected(self, tmp_path: Path) -> None:
        # Arrange
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "docs.yml").write_text(_MAKE_HTML_WORKFLOW)
        # Act
        result = _has_rtd_workflow(tmp_path)
        # Assert
        assert result is True

    def test_only_unrelated_workflow_not_detected(self, tmp_path: Path) -> None:
        # Arrange
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "tests.yml").write_text(_UNRELATED_WORKFLOW)
        # Act
        result = _has_rtd_workflow(tmp_path)
        # Assert
        assert result is False

    def test_no_workflows_dir_not_detected(self, tmp_path: Path) -> None:
        # Arrange
        # (empty tmp_path — no .github/workflows/ directory)
        # Act
        result = _has_rtd_workflow(tmp_path)
        # Assert
        assert result is False

    def test_yaml_extension_also_scanned(self, tmp_path: Path) -> None:
        # Arrange
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "docs.yaml").write_text(_RENAMED_WORKFLOW)
        # Act
        result = _has_rtd_workflow(tmp_path)
        # Assert
        assert result is True


# ===== check_sphinx_html (PS-122 integration) =====


class TestPS122RegressionRenamedWorkflow:
    def test_renamed_workflow_does_not_fire_PS122(self, tmp_path: Path) -> None:
        # Arrange: reproduce the SAC false-fire — workflow renamed under
        # PS-164 from docs.yml to rtd-sphinx-build-on-ubuntu-latest.yml
        # still builds sphinx — PS-122 must NOT flag it.
        repo = _make_pkg_with_sphinx(tmp_path)
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "rtd-sphinx-build-on-ubuntu-latest.yml").write_text(_RENAMED_WORKFLOW)
        out: list = []
        # Act
        check_sphinx_html(repo, _StubViolation, out)
        # Assert
        assert not any(v.rule == "PS-122" for v in out)

    def test_no_workflow_at_all_fires_PS122(self, tmp_path: Path) -> None:
        # Arrange: negative control — sphinx source but no workflows at all.
        repo = _make_pkg_with_sphinx(tmp_path)
        out: list = []
        # Act
        check_sphinx_html(repo, _StubViolation, out)
        # Assert
        assert any(v.rule == "PS-122" for v in out)

    def test_only_unrelated_workflow_fires_PS122(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_pkg_with_sphinx(tmp_path)
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "tests.yml").write_text(_UNRELATED_WORKFLOW)
        out: list = []
        # Act
        check_sphinx_html(repo, _StubViolation, out)
        # Assert
        assert any(v.rule == "PS-122" for v in out)

    def test_legacy_docs_yml_still_passes(self, tmp_path: Path) -> None:
        # Arrange: backward-compat — legacy filename ok because of contents.
        repo = _make_pkg_with_sphinx(tmp_path)
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "docs.yml").write_text(_RENAMED_WORKFLOW)
        out: list = []
        # Act
        check_sphinx_html(repo, _StubViolation, out)
        # Assert
        assert not any(v.rule == "PS-122" for v in out)
