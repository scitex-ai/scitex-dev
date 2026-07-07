#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the shared deprecation helper (3-phase ladder, W → E).

Doctrine under test:
``scitex_dev/_skills/general/03_interface/02_cli/11_deprecation.md`` —
warn phase forwards via a hidden alias with a once-per-shell-session
stderr warning (``$PPID`` marker file under ``$XDG_RUNTIME_DIR``);
error phase prints a ``Re-run with:`` redirect and exits 2.

No mocks: the once-per-session mechanism is exercised through the real
marker files, isolated per test by pointing ``XDG_RUNTIME_DIR`` at
``tmp_path``.
"""

from __future__ import annotations

import functools
import os

import click
import pytest
from click.testing import CliRunner

from scitex_dev._ecosystem.click_compat import deprecated_alias


@pytest.fixture(autouse=True)
def isolated_marker_dir(tmp_path):
    """Fresh once-per-shell-session marker dir for every test."""
    previous = os.environ.get("XDG_RUNTIME_DIR")
    os.environ["XDG_RUNTIME_DIR"] = str(tmp_path)
    yield
    if previous is None:
        os.environ.pop("XDG_RUNTIME_DIR", None)
    else:
        os.environ["XDG_RUNTIME_DIR"] = previous


def _build_cli(*, phase: str, remove_in: str = "0.20"):
    """A group with one real command plus a deprecation alias for it."""

    @click.group()
    def cli():
        pass

    @cli.command("new-cmd")
    @click.option("--name", default="anonymous")
    def new_cmd(name):
        click.echo(f"ran:{name}")

    alias = deprecated_alias(
        cli, "old-cmd", target="new-cmd", remove_in=remove_in, phase=phase
    )
    return cli, alias


# ── phase W: warn + forward ─────────────────────────────────────────────────


def test_warn_phase_forwards_and_exits_zero():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert result.exit_code == 0


def test_warn_phase_runs_target_command_body():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert "ran:anonymous" in result.stdout


def test_warn_phase_forwards_options_to_target():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd", "--name", "alice"])
    # Assert
    assert "ran:alice" in result.stdout


def test_warn_phase_stderr_uses_doctrine_warning_format():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert (
        "'old-cmd' is deprecated — use 'new-cmd' (removed in v0.20)"
        in result.stderr
    )


def test_warn_phase_normalizes_v_prefixed_remove_in():
    # Arrange
    cli, _alias = _build_cli(phase="warn", remove_in="v0.20")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert "(removed in v0.20)" in result.stderr


def test_warn_phase_warns_once_per_shell_session():
    # Arrange — same process ⇒ same $PPID ⇒ same session marker
    cli, _alias = _build_cli(phase="warn")
    runner = CliRunner()
    # Act
    runner.invoke(cli, ["old-cmd"])
    second = runner.invoke(cli, ["old-cmd"])
    # Assert
    assert "deprecated" not in second.stderr


def test_warn_phase_second_call_still_forwards():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    runner = CliRunner()
    # Act
    runner.invoke(cli, ["old-cmd"])
    second = runner.invoke(cli, ["old-cmd", "--name", "bob"])
    # Assert
    assert "ran:bob" in second.stdout


def test_warn_phase_forwards_to_command_on_sibling_group():
    # Arrange — target Command object lives on a DIFFERENT group than
    # the alias (the `quality` → `ecosystem` shape in _cli/_root.py)
    @click.group()
    def root():
        pass

    @click.group()
    def canonical():
        pass

    @canonical.command("audit-thing")
    @click.option("--flag", is_flag=True)
    def audit_thing(flag):
        click.echo(f"audited:{flag}")

    root.add_command(canonical, "canonical")
    legacy = click.Group("legacy")
    root.add_command(legacy, "legacy")
    deprecated_alias(
        legacy,
        "audit-thing",
        target=audit_thing,
        target_name="canonical audit-thing",
        remove_in="0.11",
        phase="warn",
    )
    # Act
    result = CliRunner().invoke(root, ["legacy", "audit-thing", "--flag"])
    # Assert
    assert "audited:True" in result.stdout


# ── phase E: error redirect ─────────────────────────────────────────────────


def test_error_phase_exits_with_code_two():
    # Arrange
    cli, _alias = _build_cli(phase="error")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert result.exit_code == 2


def test_error_phase_prints_rerun_redirect_on_stderr():
    # Arrange
    cli, _alias = _build_cli(phase="error")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert "Re-run with: cli new-cmd" in result.stderr


def test_error_phase_names_the_rename_on_stderr():
    # Arrange
    cli, _alias = _build_cli(phase="error")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert "error: `cli old-cmd` was renamed to `cli new-cmd`." in result.stderr


def test_error_phase_does_not_run_target_body():
    # Arrange
    cli, _alias = _build_cli(phase="error")
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert "ran:" not in result.stdout


# ── metadata + registration surface ─────────────────────────────────────────


def test_alias_metadata_records_ladder_state():
    # Arrange
    cli, alias = _build_cli(phase="warn")
    # Act
    metadata = alias._deprecated_alias
    # Assert
    assert metadata == {
        "target": "new-cmd",
        "remove_in": "0.20",
        "phase": "warn",
    }


def test_alias_hidden_from_group_help():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    # Act
    result = CliRunner().invoke(cli, ["--help"])
    # Assert
    assert "old-cmd" not in result.stdout


def test_unknown_phase_raises_value_error():
    # Arrange
    cli, _alias = _build_cli(phase="warn")
    # Act
    register_with_bad_phase = functools.partial(
        deprecated_alias,
        cli,
        "older-cmd",
        target="new-cmd",
        remove_in="0.20",
        phase="removed",
    )
    # Assert
    with pytest.raises(ValueError):
        register_with_bad_phase()


def test_missing_string_target_fails_loud_at_dispatch():
    # Arrange — string target that was never registered on the group
    @click.group()
    def cli():
        pass

    deprecated_alias(
        cli, "old-cmd", target="ghost-cmd", remove_in="0.20", phase="warn"
    )
    # Act
    result = CliRunner().invoke(cli, ["old-cmd"])
    # Assert
    assert result.exit_code == 2


def test_helper_exported_from_public_ecosystem_facade():
    # Arrange
    from scitex_dev import ecosystem
    # Act
    exported = ecosystem.deprecated_alias
    # Assert
    assert exported is deprecated_alias
