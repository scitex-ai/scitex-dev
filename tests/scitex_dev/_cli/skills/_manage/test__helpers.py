"""Tests for `_print_export_result` (`_helpers.py`)."""

from __future__ import annotations

import click
from click.testing import CliRunner

from scitex_dev._cli.skills._manage._helpers import _print_export_result


def test_print_export_result_empty_says_no_skills_found():
    # Arrange
    @click.command()
    def _cmd():
        _print_export_result({}, "/tmp/dest")

    runner = CliRunner()
    # Act
    result = runner.invoke(_cmd, [])
    # Assert
    assert "No skills found" in result.output


def test_print_export_result_json_mode_emits_parseable_json():
    # Arrange
    import json

    exported = {"scitex-dev": ["/tmp/dest/scitex-dev/a.md"]}

    @click.command()
    def _cmd():
        _print_export_result(exported, "/tmp/dest", as_json=True)

    runner = CliRunner()
    # Act
    result = runner.invoke(_cmd, [])
    # Assert
    assert json.loads(result.output) == {"scitex-dev": ["/tmp/dest/scitex-dev/a.md"]}
