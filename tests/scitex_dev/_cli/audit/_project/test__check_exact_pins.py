"""Tests for `_check_exact_pins.py` (PS-237).

An exact `==`/`===` pin in `[project].dependencies` or any
`[project.optional-dependencies]` group downgrades newer installs and forces
a release for every dependency release. Each test builds a REAL temp
`pyproject.toml` (no mocks); the temp dirs carry no `.git`, so no baseline
resolves and every finding keeps the registered default severity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_exact_pins import (
    EXACT_PIN_RULES,
    check_ps237_exact_pins,
    exact_pin,
)
from scitex_dev._cli.audit._project._rules import RULES


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str
    severity_override: str | None = None


def _write(repo: Path, body: str) -> None:
    repo.joinpath("pyproject.toml").write_text(body, encoding="utf-8")


def _run(repo: Path) -> list:
    out: list = []
    check_ps237_exact_pins(repo, _StubViolation, out)
    return out


# --- PS-237 fires (positive cases) ------------------------------------------


def test_ps237_fires_on_exact_pin_in_core_dependencies(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex"\ndependencies = ["scitex-io==0.7.0"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert [v.rule for v in out] == ["PS-237"]


def test_ps237_fires_on_exact_pin_inside_an_extra(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'gui = ["scitex-sdk[gui]==0.3.25"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert "[project.optional-dependencies.gui]" in out[0].detail


def test_ps237_fires_on_arbitrary_equality(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["pkg===1.2"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert len(out) == 1


def test_ps237_detail_names_requirement_and_minimum_fix(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex"\ndependencies = ["scitex-dev==0.28.0"]\n',
    )
    # Act
    detail = _run(tmp_path)[0].detail
    # Assert
    assert "scitex-dev==0.28.0" in detail and "scitex-dev>=X.Y" in detail


def test_ps237_flags_every_pinned_requirement(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex"\n'
        'dependencies = ["scitex-io==0.7.0", "scitex-dev==0.67.0", "numpy"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert len(out) == 2


# --- PS-237 silent (negative cases) -----------------------------------------


def test_ps237_silent_on_minimum_floors_and_ranges(tmp_path):
    # Arrange
    _write(
        tmp_path,
        '[project]\nname = "scitex"\n'
        'dependencies = ["scitex-io>=0.4.0", "numpy>=1.24,<3", "pyyaml~=6.0", '
        '"click!=8.1.4", "pandas"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps237_silent_on_wildcard_equality(tmp_path):
    # Arrange: `==1.2.*` is a range of releases, not a pin
    _write(
        tmp_path,
        '[project]\nname = "scitex-fake"\ndependencies = ["pkg==1.2.*"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps237_ignores_build_system_requires(tmp_path):
    # Arrange: build backends are pinned in [build-system], not published
    _write(
        tmp_path,
        '[build-system]\nrequires = ["hatchling==1.30.1"]\n'
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps237_silent_without_pyproject(tmp_path):
    # Arrange: no pyproject.toml at all
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


# --- helper + registration --------------------------------------------------


def test_exact_pin_ignores_environment_marker_text():
    # Arrange: the marker compares with ==, the requirement itself is a floor
    requirement = 'tomli>=2.0; python_version == "3.10"'
    # Act
    clause = exact_pin(requirement)
    # Assert
    assert clause is None


def test_ps237_baseline_ref_matches_the_shared_default():
    # Arrange: the check keeps its own copy to avoid a circular import
    from scitex_dev._cli.audit._project import _check_exact_pins
    from scitex_dev._cli.audit._project._new_vs_baseline import (
        DEFAULT_BASELINE_REF,
    )

    # Act
    local = _check_exact_pins._BASELINE_REF
    # Assert
    assert local == DEFAULT_BASELINE_REF


def test_ps237_is_registered_with_warn_default():
    # Arrange
    code, _section, _message, severity, _slug = EXACT_PIN_RULES[0]
    # Act
    registered = RULES[code]
    # Assert
    assert (code, severity, registered.severity) == ("PS-237", "W", "W")


# EOF
