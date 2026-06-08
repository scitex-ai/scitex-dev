"""Wiring-smoke tests for ``scitex_dev.ci.runner`` click commands.

No mocks (PA-306). Each test invokes the click CLI in-process via
``CliRunner`` and asserts the ``--help`` invocation exits cleanly.
This catches import-time / decorator-time regressions across the
runner subcommand surface without simulating the shell-out side
effects (those are end-to-end-tested by the canary rollout).
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scitex_dev.ci.runner import register_ci_runner_commands

RUNNER_SUBCOMMANDS = ["status", "use", "up", "down", "renew", "register"]


def _build_root_cli():
    """Hand-rolled root click.Group with the ci/runner tree wired up."""
    import click

    root = click.Group()
    register_ci_runner_commands(root)
    return root


@pytest.mark.parametrize("subcommand", RUNNER_SUBCOMMANDS)
def test_runner_subcommand_help_exits_zero(subcommand):
    # Arrange
    runner = CliRunner()
    cli = _build_root_cli()
    # Act
    result = runner.invoke(cli, ["ci", "runner", subcommand, "--help"])
    # Assert
    assert result.exit_code == 0


def test_runner_root_help_lists_runner_group_section():
    # Arrange
    runner = CliRunner()
    cli = _build_root_cli()
    # Act
    result = runner.invoke(cli, ["ci", "runner", "--help"])
    # Assert
    assert "runner" in result.output.lower()


def test_runner_register_help_documents_yes_flag():
    # Arrange
    runner = CliRunner()
    cli = _build_root_cli()
    # Act
    result = runner.invoke(cli, ["ci", "runner", "register", "--help"])
    # Assert
    assert "--yes" in result.output


def test_runner_register_help_documents_dry_run_flag():
    # Arrange
    runner = CliRunner()
    cli = _build_root_cli()
    # Act
    result = runner.invoke(cli, ["ci", "runner", "register", "--help"])
    # Assert
    assert "--dry-run" in result.output
