"""Verify `scitex-dev ecosystem --help` renders categorised sections."""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


@pytest.fixture
def help_output():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "--help"])
    assert result.exit_code == 0, result.output
    return result.output


def test_ecosystem_help_renders_audit_section(help_output):
    # Arrange
    text = help_output
    # Act
    found = "Audit:" in text
    # Assert
    assert found


def test_ecosystem_help_renders_bulk_section(help_output):
    # Arrange
    text = help_output
    # Act
    found = "Bulk:" in text
    # Assert
    assert found


def test_ecosystem_help_renders_discovery_section(help_output):
    # Arrange
    text = help_output
    # Act
    found = "Discovery:" in text
    # Assert
    assert found


def test_ecosystem_help_renders_quality_section(help_output):
    # Arrange
    text = help_output
    # Act
    found = "Quality:" in text
    # Assert
    assert found


def test_ecosystem_help_renders_maintenance_section(help_output):
    # Arrange
    text = help_output
    # Act
    found = "Maintenance:" in text
    # Assert
    assert found


def test_ecosystem_help_lists_under_discovery(help_output):
    # Arrange
    text = help_output
    discovery_idx = text.find("Discovery:")
    list_idx = text.find("\n  list ")
    # Act
    list_is_under_discovery = (
        discovery_idx != -1 and list_idx != -1 and list_idx > discovery_idx
    )
    # Assert
    assert list_is_under_discovery
