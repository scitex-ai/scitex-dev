# -*- coding: utf-8 -*-
"""Tests for `_check_no_url_deps.py` (PS-216).

A PEP 508 direct reference (`pkg @ git+https://...`, a plain URL, or a
`file://` reference) in `[project].dependencies` or any
`[project.optional-dependencies]` group is rejected by PyPI/twine on
upload, silently blocking a release. Each test builds a REAL temp
`pyproject.toml` (no mocks) then asserts whether PS-216 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_no_url_deps import (
    check_ps216_no_url_deps,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write(repo: Path, body: str) -> None:
    repo.joinpath("pyproject.toml").write_text(body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- PS-216 fires (positive cases) ------------------------------------------


def test_ps216_fires_on_git_url_in_core_dependencies(tmp_path):
    # Arrange — a git+https VCS dep in [project].dependencies
    _write(
        tmp_path,
        '[project]\nname = "scitex-fakepeer"\n'
        'dependencies = ["scitex-peer @ git+https://github.com/x/scitex-peer"]\n',
    )
    out: list = []
    # Act
    check_ps216_no_url_deps(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-216" in _codes(out)


def test_ps216_fires_on_url_dep_in_optional_dependencies(tmp_path):
    # Arrange — a `pkg @ https://...` direct reference inside an extra
    _write(
        tmp_path,
        '[project]\nname = "scitex-fakepeer"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'extra = ["wheelpkg @ https://example.com/wheelpkg-1.0-py3-none-any.whl"]\n',
    )
    out: list = []
    # Act
    check_ps216_no_url_deps(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-216" in _codes(out)


def test_ps216_detail_names_the_offending_dependency(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex-fakepeer"\n'
        'dependencies = ["scitex-peer @ git+https://github.com/x/scitex-peer"]\n',
    )
    out: list = []
    # Act
    check_ps216_no_url_deps(tmp_path, _StubViolation, out)
    # Assert
    assert "scitex-peer" in out[0].detail


# --- PS-216 silent (negative cases) -----------------------------------------


def test_ps216_silent_on_clean_version_specifiers(tmp_path):
    # Arrange — only normal PEP 440 specifiers, no direct references
    _write(
        tmp_path,
        '[project]\nname = "scitex-fakepeer"\n'
        'dependencies = ["numpy>=1.0", "click>=8.0.0", "pyyaml~=6.0"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=7.0.0", "pytest-cov==4.1.0"]\n',
    )
    out: list = []
    # Act
    check_ps216_no_url_deps(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps216_silent_on_extras_and_marker_deps(tmp_path):
    # Arrange — a `pkg[foo]` extra and a `; python_version` marker: no URL
    _write(
        tmp_path,
        '[project]\nname = "scitex-fakepeer"\n'
        'dependencies = ["uvicorn[standard]>=0.20", '
        '"tomli>=2.0; python_version < \\"3.11\\""]\n',
    )
    out: list = []
    # Act
    check_ps216_no_url_deps(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
