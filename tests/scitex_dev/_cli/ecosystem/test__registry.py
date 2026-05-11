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


def test_register_returns_ecosystem_group():
    _, eco = _build_group()
    assert isinstance(eco, click.Group)
    assert "list" in eco.commands
    assert "audit-project" in eco.commands


def test_ecosystem_help_runs():
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "--help"])
    assert result.exit_code == 0
    assert "ecosystem" in result.output.lower()


def test_ecosystem_list_help_runs():
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "list", "--help"])
    assert result.exit_code == 0
    assert "scitex-dev ecosystem list" in result.output


def test_ecosystem_audit_project_help_runs():
    main, _ = _build_group()
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "audit-project", "--help"])
    assert result.exit_code == 0
    assert "audit-project" in result.output or "DISTRIBUTION" in result.output
