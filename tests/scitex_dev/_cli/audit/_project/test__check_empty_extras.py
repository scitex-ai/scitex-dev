# -*- coding: utf-8 -*-
"""Tests for `_check_empty_extras.py` (PS-214).

A `pyproject.toml` extra declared as an empty list (`foo = []`) is a
remedy that installs nothing. Each test builds a REAL temp
`pyproject.toml` (no mocks) then asserts whether PS-214 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_empty_extras import (
    check_ps214_empty_extras,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_pyproject(repo: Path, extras_block: str, *, name: str = "scitex-fakepeer") -> None:
    repo.joinpath("pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        'dependencies = ["numpy"]\n'
        "[project.optional-dependencies]\n"
        f"{extras_block}\n",
        encoding="utf-8",
    )


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- PS-214 fires (positive cases) ------------------------------------------


def test_ps214_fires_on_empty_extra_list(tmp_path):
    # Arrange — the scitex-writer incident shape: editor = []
    _write_pyproject(tmp_path, 'editor = []\nfull = ["scitex-app>=0.1.0"]\n')
    out: list = []
    # Act
    check_ps214_empty_extras(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-214" in _codes(out)


def test_ps214_detail_names_the_offending_extra(tmp_path):
    # Arrange
    _write_pyproject(tmp_path, "editor = []\n")
    out: list = []
    # Act
    check_ps214_empty_extras(tmp_path, _StubViolation, out)
    # Assert
    assert "editor" in out[0].detail


def test_ps214_fires_once_per_empty_extra(tmp_path):
    # Arrange — two independently-empty extras
    _write_pyproject(tmp_path, "editor = []\nviewer = []\n")
    out: list = []
    # Act
    check_ps214_empty_extras(tmp_path, _StubViolation, out)
    # Assert
    assert len(out) == 2


# --- PS-214 silent (negative cases) -----------------------------------------


def test_ps214_silent_when_extra_is_non_empty(tmp_path):
    # Arrange — a valid, populated extras table (the fixed shape)
    _write_pyproject(
        tmp_path,
        'editor = ["scitex-app>=0.1.0"]\nall = ["scitex-app>=0.1.0"]\n',
    )
    out: list = []
    # Act
    check_ps214_empty_extras(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps214_silent_when_no_optional_dependencies_table(tmp_path):
    # Arrange — no [project.optional-dependencies] section at all
    tmp_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "scitex-fakepeer"\ndependencies = ["numpy"]\n',
        encoding="utf-8",
    )
    out: list = []
    # Act
    check_ps214_empty_extras(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps214_silent_when_pyproject_absent(tmp_path):
    # Arrange — empty repo, no pyproject.toml
    out: list = []
    # Act
    check_ps214_empty_extras(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
