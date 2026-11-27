"""Tests for the umbrella pin auditor (PS-170).

PS-170 flags every exact `==`/`===` member pin in the umbrella's
pyproject and accepts minimum (`>=`) declarations. It no longer queries
PyPI: the former drift check pushed the umbrella to re-pin on every member
release. Each test writes a REAL temp pyproject.toml (no mocks, no network).
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from scitex_dev._cli.audit._umbrella_pins import audit_umbrella_pins
from scitex_dev._cli.audit._umbrella_pins import cli as umbrella_pins_cli


def _write_umbrella(tmp_path: Path, *deps: str, extras: str = "") -> Path:
    """Create a minimal pyproject.toml with `name = "scitex"` and `deps`."""
    body = '[project]\nname = "scitex"\nversion = "0.0.0"\ndependencies = [\n'
    for d in deps:
        body += f'    "{d}",\n'
    body += "]\n" + extras
    (tmp_path / "pyproject.toml").write_text(body)
    return tmp_path


def _invoke(*args: str):
    result = CliRunner().invoke(umbrella_pins_cli, list(args))
    return result, (result.output or "") + (result.stderr or "")


# --- silent ------------------------------------------------------------------


def test_non_umbrella_package_returns_empty_silently(tmp_path):
    # Arrange: PS-237 covers other packages; PS-170 is umbrella-scoped
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-io"\nversion = "0.2.0"\n'
        'dependencies = ["scitex-stats==99.0.0"]\n'
    )
    # Act
    violations = audit_umbrella_pins(tmp_path)
    # Assert
    assert violations == []


def test_missing_pyproject_returns_empty_silently(tmp_path):
    # Arrange: no pyproject.toml at all
    # Act
    violations = audit_umbrella_pins(tmp_path)
    # Assert
    assert violations == []


def test_minimum_and_range_declarations_are_not_flagged(tmp_path):
    # Arrange
    repo = _write_umbrella(
        tmp_path,
        "scitex-io>=0.2.0",
        "scitex-stats~=1.0",
        "scitex-dev",
        "scitex-str>=0.1,<1",
        "scitex-pd!=0.1.3",
    )
    # Act
    violations = audit_umbrella_pins(repo)
    # Assert
    assert violations == []


def test_exact_pin_on_non_member_is_left_to_ps237(tmp_path):
    # Arrange: third-party pins are PS-237's concern, not PS-170's
    repo = _write_umbrella(tmp_path, "numpy==2.0.0")
    # Act
    violations = audit_umbrella_pins(repo)
    # Assert
    assert violations == []


# --- flagged -----------------------------------------------------------------


def test_exact_member_pin_is_flagged(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.1.0")
    # Act
    violations = audit_umbrella_pins(repo)
    # Assert
    assert len(violations) == 1 and violations[0].startswith(
        "PS-170: scitex-io==0.1.0 is an exact pin"
    )


def test_exact_member_pin_in_an_extra_is_flagged(tmp_path):
    # Arrange
    repo = _write_umbrella(
        tmp_path,
        "scitex-io>=0.2.0",
        extras='[project.optional-dependencies]\nwriter = ["scitex-writer==2.0.0"]\n',
    )
    # Act
    violations = audit_umbrella_pins(repo)
    # Assert
    assert [v.split(" ")[1] for v in violations] == ["scitex-writer==2.0.0"]


def test_member_extras_and_branded_members_are_recognised(tmp_path):
    # Arrange
    repo = _write_umbrella(
        tmp_path, "scitex-dev[local-store]==0.67.0", "figrecipe==0.45.1"
    )
    # Act
    violations = audit_umbrella_pins(repo)
    # Assert
    assert len(violations) == 2


def test_repeated_identical_pin_is_reported_once(tmp_path):
    # Arrange: the same requirement in core and in an extra
    repo = _write_umbrella(
        tmp_path,
        "scitex-io==0.1.0",
        extras='[project.optional-dependencies]\nio = ["scitex-io==0.1.0"]\n',
    )
    # Act
    violations = audit_umbrella_pins(repo)
    # Assert
    assert len(violations) == 1


# --- CLI exit semantics ------------------------------------------------------


def test_cli_clean_repo_exits_0_with_succ_prefix(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io>=0.2.0")
    # Act
    result, combined = _invoke(str(repo))
    # Assert
    assert result.exit_code == 0 and "SUCC:" in result.output, combined


def test_cli_exact_pin_default_warn_only_exits_0(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.1.0")
    # Act
    result, combined = _invoke(str(repo))
    # Assert
    assert (
        result.exit_code == 0
        and "WARN:" in combined
        and "PS-170: scitex-io==0.1.0" in combined
    ), combined


def test_cli_exact_pin_with_strict_exits_1(tmp_path):
    # Arrange
    repo = _write_umbrella(tmp_path, "scitex-io==0.1.0")
    # Act
    result, combined = _invoke(str(repo), "--strict")
    # Assert
    assert result.exit_code == 1 and "ERRO:" in combined, combined


def test_cli_still_accepts_deprecated_allow_network_error(tmp_path):
    # Arrange: existing CI callers pass the retired flag
    repo = _write_umbrella(tmp_path, "scitex-io>=0.2.0")
    # Act
    result, combined = _invoke(str(repo), "--strict", "--allow-network-error")
    # Assert
    assert result.exit_code == 0, combined


def test_cli_help_advertises_strict_flag():
    # Arrange
    # Act
    result, _ = _invoke("--help")
    # Assert
    assert result.exit_code == 0 and "--strict" in result.output
