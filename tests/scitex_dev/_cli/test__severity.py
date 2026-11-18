"""Both warning spellings reach existing audit contracts through real Click types."""

import json

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli._root import main

AUDITS = [
    ("audit-all", "warn"),
    ("audit-cli", "warn"),
    ("audit-mcp-tools", "warn"),
    ("audit-project", "warning"),
    ("audit-django", "warning"),
    ("audit-local-state", "warning"),
    ("audit-registry-layout", "warning"),
]


def severity_option(name):
    context = click.Context(main)
    ecosystem = main.get_command(context, "ecosystem")
    context = click.Context(ecosystem, parent=context)
    command = ecosystem.get_command(context, name)
    return next(option for option in command.params if "--severity" in option.opts)


@pytest.mark.parametrize("name,expected", AUDITS)
@pytest.mark.parametrize("spelling", ["warn", "warning"])
def test_registered_auditor_accepts_both_warning_spellings(name, expected, spelling):
    # Arrange
    option = severity_option(name)
    # Act
    actual = option.type.convert(spelling, option, None)
    # Assert
    assert actual == expected


@pytest.mark.parametrize("name,unused", AUDITS)
@pytest.mark.parametrize("spelling", ["info", "error"])
def test_other_severity_values_are_preserved(name, unused, spelling):
    # Arrange
    option = severity_option(name)
    # Act
    actual = option.type.convert(spelling, option, None)
    # Assert
    assert actual == spelling


@pytest.mark.parametrize("name,unused", AUDITS)
def test_invalid_severity_remains_a_parser_error(name, unused):
    # Arrange
    option = severity_option(name)
    # Act
    # Assert
    with pytest.raises(click.BadParameter):
        option.type.convert("ignore-errors", option, None)


@pytest.fixture
def actual_project_audits(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="scitex-owned"\nversion="0.1.0"\n'
    )
    (tmp_path / "README.md").write_text(
        "# Owned\n\n## Installation\n\nInstall.\n\n## Quick Start\n\nUse.\n"
    )
    runner = CliRunner()
    return {
        spelling: runner.invoke(
            main,
            [
                "ecosystem",
                "audit-project",
                "scitex-owned",
                "--path",
                str(tmp_path),
                "--severity",
                spelling,
                "--json",
            ],
        )
        for spelling in ("warn", "warning")
    }


def test_actual_project_alias_preserves_exit_status(actual_project_audits):
    # Arrange
    results = actual_project_audits
    # Act
    actual = results["warn"].exit_code
    # Assert
    assert actual == results["warning"].exit_code


def test_actual_project_alias_preserves_full_report(actual_project_audits):
    # Arrange
    results = actual_project_audits
    # Act
    actual = results["warn"].output
    # Assert
    assert actual == results["warning"].output


def test_actual_project_alias_retains_real_findings(actual_project_audits):
    # Arrange
    result = actual_project_audits["warn"]
    # Act
    payload = json.loads(result.output)
    # Assert
    assert any(row["severity"] == "W" for row in payload["violations"])
