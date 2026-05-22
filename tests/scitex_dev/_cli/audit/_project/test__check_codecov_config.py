"""Tests for `_check_codecov_config.py` (PS-171).

A package whose CI uploads coverage to Codecov must ship a repo-root
`codecov.yml` pinned to `branch: develop`. No mocks — real files under
`tmp_path` and a real `_StubViolation` collector.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_codecov_config import (
    check_ps171_codecov_config,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


_WORKFLOW_WITH_CODECOV = """\
name: pytest
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: codecov/codecov-action@v5
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
"""

_WORKFLOW_NO_CODECOV = """\
name: pytest
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest
"""

_CANONICAL_CODECOV_YML = """\
codecov:
  require_ci_to_pass: false
  branch: develop
coverage:
  status:
    project:
      default:
        target: auto
"""

_CODECOV_YML_NO_BRANCH = """\
codecov:
  require_ci_to_pass: false
coverage:
  status:
    project:
      default:
        target: auto
"""


def _make_repo(tmp_path: Path, *, workflow: str, codecov_yml: str | None) -> Path:
    """Build a real repo skeleton under tmp_path."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "pytest.yml").write_text(workflow)
    if codecov_yml is not None:
        (tmp_path / "codecov.yml").write_text(codecov_yml)
    return tmp_path


def test_uploading_repo_without_codecov_yml_flags_missing(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, workflow=_WORKFLOW_WITH_CODECOV, codecov_yml=None)
    out: list[_StubViolation] = []
    # Act
    check_ps171_codecov_config(repo, _StubViolation, out)
    # Assert
    assert [v.rule for v in out] == ["PS-171"]


def test_non_uploading_repo_is_not_required_to_have_codecov_yml(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, workflow=_WORKFLOW_NO_CODECOV, codecov_yml=None)
    out: list[_StubViolation] = []
    # Act
    check_ps171_codecov_config(repo, _StubViolation, out)
    # Assert
    assert out == []


def test_canonical_codecov_yml_is_clean(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path, workflow=_WORKFLOW_WITH_CODECOV, codecov_yml=_CANONICAL_CODECOV_YML
    )
    out: list[_StubViolation] = []
    # Act
    check_ps171_codecov_config(repo, _StubViolation, out)
    # Assert
    assert out == []


def test_codecov_yml_without_develop_branch_pin_flags_shape(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path, workflow=_WORKFLOW_WITH_CODECOV, codecov_yml=_CODECOV_YML_NO_BRANCH
    )
    out: list[_StubViolation] = []
    # Act
    check_ps171_codecov_config(repo, _StubViolation, out)
    # Assert
    assert "branch: develop" in out[0].detail


def test_repo_without_workflows_dir_is_clean(tmp_path):
    # Arrange
    repo = tmp_path  # no .github/workflows at all
    out: list[_StubViolation] = []
    # Act
    check_ps171_codecov_config(repo, _StubViolation, out)
    # Assert
    assert out == []
