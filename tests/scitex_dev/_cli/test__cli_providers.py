"""Actual CLI output delegates to the same public metadata view."""

import json
from dataclasses import asdict

from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev.cli_providers import list_cli_providers


def test_actual_cli_json_is_public_metadata_rows():
    # Arrange
    expected = [asdict(row) for row in list_cli_providers(package="scitex-dev")]
    # Act
    result = CliRunner().invoke(
        main, ["cli", "list", "--package", "scitex-dev", "--json"]
    )
    # Assert
    assert (result.exit_code, json.loads(result.stdout)) == (0, expected)


def test_actual_root_help_exposes_diagnostic_category():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["--help"])
    # Assert
    assert (
        result.exit_code == 0
        and "cli" in result.stdout
        and "Introspection" in result.stdout
    )


def test_actual_cli_rejects_path_as_owner():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["cli", "list", "--package", "../owner", "--json"])
    # Assert
    assert result.exit_code == 1 and "invalid distribution name" in result.output
