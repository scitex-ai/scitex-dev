# -*- coding: utf-8 -*-
"""Tests for `_check_extras_all_closure.py` (PS-221).

Operator policy: a PUBLIC install extra must be `[all]` or bare ONLY, so
`pip install <pkg>[all]` pulls in EVERYTHING public. Every public
(non-underscore, non-`all`) extra must therefore be a SUBSET of `all`; a
public requirement missing from `all` is a silent under-install. Each test
builds a REAL temp `pyproject.toml` (no mocks) then asserts whether PS-221
fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_extras_all_closure import (
    check_ps221_extras_all_closure,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write(repo: Path, body: str) -> None:
    repo.joinpath("pyproject.toml").write_text(body, encoding="utf-8")


def _codes(out: list) -> list[str]:
    return [v.rule for v in out]


# --- PS-221 fires (positive cases) ------------------------------------------


def test_ps221_fires_once_when_public_extra_req_missing_from_all(tmp_path):
    # Arrange — `viz` requires matplotlib, but `all` omits it.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0", "seaborn>=0.12"]\n'
        'all = ["seaborn>=0.12"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert — exactly one ERROR for the single missing dep.
    assert _codes(out) == ["PS-221"]


def test_ps221_detail_names_the_missing_requirement(tmp_path):
    # Arrange — same shape; assert the detail names the absent dep.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0", "seaborn>=0.12"]\n'
        'all = ["seaborn>=0.12"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert "matplotlib" in out[0].detail


def test_ps221_fires_when_public_extras_but_no_all_group(tmp_path):
    # Arrange — public extras exist but there is no `all` umbrella at all.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert _codes(out) == ["PS-221"]


def test_ps221_no_all_group_detail_explains_missing_umbrella(tmp_path):
    # Arrange — same shape; assert the detail flags the absent `all` group.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert "NO `all`" in out[0].detail


# --- PS-221 silent (negative cases) -----------------------------------------


def test_ps221_silent_when_all_public_extras_are_subset_of_all(tmp_path):
    # Arrange — every public requirement is also present in `all`.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0"]\n'
        'editor = ["scitex-app>=1.0"]\n'
        'all = ["matplotlib>=3.0", "scitex-app>=1.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps221_silent_on_underscore_internal_extra_not_in_all(tmp_path):
    # Arrange — `_ci` starts with an underscore, so the checker skips it
    # DEFENSIVELY (PEP 508/685 forbids leading-underscore extra names, so no
    # buildable package carries one — but the auditor must not crash or
    # false-positive on a broken tree that does). `viz` (public) IS in
    # `all`, so nothing should fire.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0"]\n'
        '_ci = ["pytest>=7.0", "pytest-cov>=4.0"]\n'
        'all = ["matplotlib>=3.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert — internal extra is exempt from closure.
    assert out == []


def test_ps221_silent_on_self_referential_all_idiom(tmp_path):
    # Arrange — the idiomatic `all = ["<pkg>[viz,editor]"]` self-reference.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["matplotlib>=3.0"]\n'
        'editor = ["scitex-app>=1.0"]\n'
        'all = ["scitex-fake[viz,editor]"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert — self-reference expands to the concrete union, so compliant.
    assert out == []


def test_ps221_canonicalizes_names_underscore_equals_dash(tmp_path):
    # Arrange — `Foo_Bar` in the extra vs `foo-bar` in `all` are the SAME
    # distribution under PEP 503 canonicalization; must NOT false-positive.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'viz = ["Foo_Bar>=1.0"]\n'
        'all = ["foo-bar>=1.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps221_silent_when_no_optional_dependencies(tmp_path):
    # Arrange — a package with no extras at all is not a violation.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps221_silent_when_only_internal_extras(tmp_path):
    # Arrange — only underscore extras (defensively skipped; such names are
    # not buildable per PEP 508/685): no public groups to close.
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        '_ci = ["pytest>=7.0"]\n'
        '_docs = ["sphinx>=7.0"]\n',
    )
    out: list = []
    # Act
    check_ps221_extras_all_closure(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
