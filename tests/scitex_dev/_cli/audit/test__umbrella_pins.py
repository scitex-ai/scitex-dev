"""Tests for the umbrella pin auditor (PS-170).

Uses the ``_pypi_query`` DI seam on ``audit_umbrella_pins`` with hand-
rolled stub callables -- no ``unittest.mock``, no ``monkeypatch``, no
real network. PA-306 (no mocks) satisfied by dependency injection.

The 2026-05-28 relaxation (operator msg 6793): PS-170 no longer flags
``>=`` / ``~=`` / unversioned peer declarations; it only drift-checks
explicit ``==`` pins. The first test (``test_ge_pin_for_peer_is_not_flagged``)
documents that change of intent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._umbrella_pins import audit_umbrella_pins

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_umbrella(tmp_path: Path, *deps: str) -> Path:
    """Create a minimal pyproject.toml with `name = "scitex"` and `deps`."""
    body = '[project]\nname = "scitex"\nversion = "0.0.0"\ndependencies = [\n'
    for d in deps:
        body += f'    "{d}",\n'
    body += "]\n"
    (tmp_path / "pyproject.toml").write_text(body)
    return tmp_path


def _no_pypi(pkg: str):
    raise AssertionError(f"PyPI must not be queried for {pkg!r}")


def _pypi_returns(mapping: dict):
    """Stub _pypi_query that returns `mapping[pkg]` or None for unknown."""
    return lambda pkg: mapping.get(pkg)


# ---------------------------------------------------------------------------
# Non-umbrella package: silent pass
# ---------------------------------------------------------------------------


def test_non_umbrella_package_returns_empty_silently(tmp_path):
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-io"\nversion = "0.2.0"\n'
        'dependencies = ["scitex-stats==99.0.0"]\n'
    )

    # Act
    violations = audit_umbrella_pins(tmp_path, _pypi_query=_no_pypi)

    # Assert
    assert violations == []


def test_missing_pyproject_returns_empty_silently(tmp_path):
    # Arrange
    # No pyproject.toml at all.

    # Act
    violations = audit_umbrella_pins(tmp_path, _pypi_query=_no_pypi)

    # Assert
    assert violations == []


# ---------------------------------------------------------------------------
# Relaxed: non-`==` declarations are accepted (the 2026-05-28 change)
# ---------------------------------------------------------------------------


def test_ge_pin_for_peer_is_not_flagged(tmp_path):
    """PS-170 (post-2026-05-28) accepts `>=` declarations.

    Documents the intentional behaviour change: umbrella peers may use
    PEP 508 minimum-compatible declarations. Reproducibility belongs in
    the lockfile, not in pyproject.toml's compatibility-range field.
    """
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io>=0.2.0", "scitex-stats>=0.2.0")

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=_no_pypi)

    # Assert
    assert violations == []


def test_tilde_pin_for_peer_is_not_flagged(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io~=0.2.0")

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=_no_pypi)

    # Assert
    assert violations == []


def test_unversioned_peer_dep_is_not_flagged(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io")

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=_no_pypi)

    # Assert
    assert violations == []


def test_inequality_operators_are_not_flagged(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io!=0.1.0", "scitex-stats<5.0.0")

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=_no_pypi)

    # Assert
    assert violations == []


# ---------------------------------------------------------------------------
# Drift detection on explicit `==` pins (the preserved invariant)
# ---------------------------------------------------------------------------


def test_eq_pin_at_pypi_latest_returns_empty(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.2.0")
    pypi = _pypi_returns({"scitex-io": "0.2.0"})

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=pypi)

    # Assert
    assert violations == []


def test_eq_pin_behind_pypi_latest_returns_drift_violation(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.1.0")
    pypi = _pypi_returns({"scitex-io": "0.5.0"})

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=pypi)

    # Assert
    assert (
        len(violations) == 1
        and "PS-170: scitex-io==0.1.0 but PyPI latest is 0.5.0" in violations[0]
    )


def test_eq_pin_with_pypi_unreachable_returns_w_warning(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.2.0")
    pypi = _pypi_returns({})  # always returns None

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=pypi)

    # Assert
    assert len(violations) == 1 and violations[0].startswith(
        "PS-170W: could not resolve PyPI latest"
    )


# ---------------------------------------------------------------------------
# Mixed scenarios
# ---------------------------------------------------------------------------


def test_mixed_ge_and_eq_only_checks_eq_pins(tmp_path):
    """A real umbrella can mix `>=` (compatibility) and `==` (snapshot).

    Only the `==` pins should reach PyPI. Verified by counting calls.
    """
    # Arrange
    repo = _write_umbrella(
        tmp_path,
        "scitex-io>=0.2.0",
        "scitex-stats==0.5.0",
        "scitex-dev>=0.11.7",
    )
    calls: list[str] = []

    def _pypi(pkg: str):
        calls.append(pkg)
        return "0.5.0"

    # Act
    audit_umbrella_pins(repo, _pypi_query=_pypi)

    # Assert
    assert calls == ["scitex-stats"]


def test_repeated_identical_pin_is_only_audited_once(tmp_path):
    """Dedup key is (package, extras-spec) — the same dep declared twice
    in different extras groups only fires once."""
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.1.0", "scitex-io==0.1.0")
    pypi = _pypi_returns({"scitex-io": "0.5.0"})

    # Act
    violations = audit_umbrella_pins(repo, _pypi_query=pypi)

    # Assert
    assert len(violations) == 1
