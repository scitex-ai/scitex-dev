"""Smoke test for scitex_dev._cli.ecosystem._registry — register and probe --help."""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem._registry import register_ecosystem_commands


def _build_group():
    @click.group()
    def main():
        pass

    eco = register_ecosystem_commands(main)
    return main, eco


def test_register_returns_ecosystem_group_isinstance_eco_click_group():
    # Arrange
    # Act
    # Assert
    _, eco = _build_group()
    assert isinstance(eco, click.Group)


def test_register_returns_ecosystem_group_list_in_eco_commands():
    # Arrange
    # Act
    # Assert
    _, eco = _build_group()
    assert "list" in eco.commands


def test_register_returns_ecosystem_group_audit_project_in_eco_commands():
    # Arrange
    # Act
    # Assert
    _, eco = _build_group()
    assert "audit-project" in eco.commands


def test_ecosystem_help_runs_result_exit_code_0():
    # Arrange
    # Act
    # Assert
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "--help"])
    assert result.exit_code == 0


def test_ecosystem_help_runs_ecosystem_in_result_output_lower():
    # Arrange
    # Act
    # Assert
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "--help"])
    assert "ecosystem" in result.output.lower()


def test_ecosystem_list_help_runs_result_exit_code_0():
    # Arrange
    # Act
    # Assert
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "list", "--help"])
    assert result.exit_code == 0


def test_ecosystem_list_help_runs_scitex_dev_ecosystem_list_in_result_outp():
    # Arrange
    # Act
    # Assert
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "list", "--help"])
    assert "scitex-dev ecosystem list" in result.output


def test_ecosystem_audit_project_help_runs_result_exit_code_0():
    # Arrange
    # Act
    # Assert
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "audit-project", "--help"])
    assert result.exit_code == 0


def test_ecosystem_audit_project_help_runs_audit_project_in_result_output_or_distri():
    # Arrange
    # Act
    # Assert
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "audit-project", "--help"])
    assert "audit-project" in result.output or "DISTRIBUTION" in result.output
