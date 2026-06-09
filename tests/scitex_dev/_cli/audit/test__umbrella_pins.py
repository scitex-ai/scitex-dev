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


# ---------------------------------------------------------------------------
# CLI exit semantics (2026-06-09 — scitex-dev 0.17.8): drift is warn-only
# by default; `--strict` re-enables the old fail-on-drift behaviour.
#
# 0.17.7 shipped with PS-170 severity=error which cascaded into ~12 ecosystem
# CI reds the first time a leaf published a newer wheel ahead of the umbrella's
# `==` pin. Default must now be exit 0 (with WARN: prefix) so an upstream
# patch release does not break consumer CI; --strict restores the hard fail
# for the release-pipeline pre-publish gate.
# ---------------------------------------------------------------------------


from click.testing import CliRunner  # noqa: E402

from scitex_dev._cli.audit import _umbrella_pins as _ump_module  # noqa: E402
from scitex_dev._cli.audit._umbrella_pins import cli as _umbrella_pins_cli  # noqa: E402


def _swap_pypi(stub):
    """Replace the module-level `_default_pypi_latest` with `stub`.

    Returns a (apply, restore) pair. Avoids `unittest.mock` and the
    `monkeypatch` fixture per the PA-306 no-mocks rule — the function
    `audit_umbrella_pins` already resolves the PyPI callable from the
    module-global at call time (the 0.17.8 refactor), so plain attribute
    assignment is enough.
    """
    orig = _ump_module._default_pypi_latest

    def apply() -> None:
        _ump_module._default_pypi_latest = stub

    def restore() -> None:
        _ump_module._default_pypi_latest = orig

    return apply, restore


def _make_runner_repo(tmp_path: Path, *deps: str) -> Path:
    """Same as _write_umbrella but suitable for invoking the CLI against."""
    return _write_umbrella(tmp_path, *deps)


def test_cli_clean_repo_exits_0_with_succ_prefix(tmp_path):
    """No `==` pins → no PyPI lookup → exit 0 with SUCC: prefix.

    One-assert convention (PA-307 §3 STX-TQ007): the SUCC path is a
    single observable invariant — exit_code 0 AND SUCC: printed —
    asserted as a single boolean.
    """
    # Arrange
    repo = _make_runner_repo(tmp_path, "scitex-io>=0.2.0")
    runner = CliRunner()

    # Act
    result = runner.invoke(_umbrella_pins_cli, [str(repo)])
    combined = (result.output or "") + (result.stderr or "")

    # Assert
    assert result.exit_code == 0 and "SUCC:" in result.output, combined


def test_cli_drift_default_warn_only_exits_0(tmp_path):
    """Default (no --strict): PS-170 drift prints WARN: and exits 0.

    The whole point of the 0.17.8 emergency change is that an upstream
    leaf release MUST NOT cascade red CI across the ecosystem. Real
    drift (pin behind PyPI latest) is simulated via a stub
    `_default_pypi_latest` so no real network is needed. The observable
    invariant is a single 3-part conjunction (exit 0 AND drift line
    printed AND WARN: prefix used) collapsed into one assert.
    """
    # Arrange — umbrella pins scitex-io==0.1.0, PyPI says 0.5.0 → drift.
    repo = _make_runner_repo(tmp_path, "scitex-io==0.1.0")
    apply, restore = _swap_pypi(lambda pkg: "0.5.0" if pkg == "scitex-io" else None)
    runner = CliRunner()

    # Act
    apply()
    try:
        result = runner.invoke(_umbrella_pins_cli, [str(repo)])
    finally:
        restore()
    combined = (result.output or "") + (result.stderr or "")

    # Assert
    assert (
        result.exit_code == 0
        and "PS-170: scitex-io==0.1.0 but PyPI latest is 0.5.0" in combined
        and "WARN:" in combined
        and "ERRO:" not in combined
    ), combined


def test_cli_drift_with_strict_exits_1(tmp_path):
    """`--strict` restores the pre-0.17.8 hard-fail-on-drift behaviour."""
    # Arrange — same drift fixture as above.
    repo = _make_runner_repo(tmp_path, "scitex-io==0.1.0")
    apply, restore = _swap_pypi(lambda pkg: "0.5.0" if pkg == "scitex-io" else None)
    runner = CliRunner()

    # Act
    apply()
    try:
        result = runner.invoke(_umbrella_pins_cli, [str(repo), "--strict"])
    finally:
        restore()
    combined = (result.output or "") + (result.stderr or "")

    # Assert
    assert (
        result.exit_code == 1
        and "PS-170: scitex-io==0.1.0 but PyPI latest is 0.5.0" in combined
        and "ERRO:" in combined
        and "WARN:" not in combined
    ), combined


def test_cli_strict_network_failure_without_allow_exits_1(tmp_path):
    """`--strict` alone treats a PyPI lookup failure (PS-170W) as fatal —
    a release pipeline that cannot reach PyPI should not publish a tag.
    """
    # Arrange — `==` pin + PyPI lookup returns None → PS-170W warning.
    repo = _make_runner_repo(tmp_path, "scitex-io==0.2.0")
    apply, restore = _swap_pypi(lambda pkg: None)
    runner = CliRunner()

    # Act
    apply()
    try:
        result = runner.invoke(_umbrella_pins_cli, [str(repo), "--strict"])
    finally:
        restore()
    combined = (result.output or "") + (result.stderr or "")

    # Assert
    assert result.exit_code == 1 and "PS-170W:" in combined, combined


def test_cli_strict_plus_allow_network_error_exits_0(tmp_path):
    """`--strict --allow-network-error` downgrades the network-flake case
    (PS-170W only, no hard PS-170 drift) to exit 0 — the release-pipeline
    path that runs on the umbrella's tag-push CI relies on this. The
    warning still surfaces so operators see the network flake."""
    # Arrange — PyPI unreachable, but pin is otherwise fine.
    repo = _make_runner_repo(tmp_path, "scitex-io==0.2.0")
    apply, restore = _swap_pypi(lambda pkg: None)
    runner = CliRunner()

    # Act
    apply()
    try:
        result = runner.invoke(
            _umbrella_pins_cli,
            [str(repo), "--strict", "--allow-network-error"],
        )
    finally:
        restore()
    combined = (result.output or "") + (result.stderr or "")

    # Assert
    assert result.exit_code == 0 and "PS-170W:" in combined, combined


def test_cli_help_advertises_strict_flag(tmp_path):
    """The `--strict` flag must be discoverable via --help (it's the
    operator's escape hatch when they want fail-on-drift back)."""
    # Arrange
    runner = CliRunner()

    # Act
    result = runner.invoke(_umbrella_pins_cli, ["--help"])
    haystack = result.output.lower()

    # Assert
    assert (
        result.exit_code == 0
        and "--strict" in result.output
        and "warn" in haystack
    ), result.output
