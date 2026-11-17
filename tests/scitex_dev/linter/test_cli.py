"""Standalone and mounted linter help preserve executable command paths."""

import json

import click
import pytest
from click.testing import CliRunner

from scitex_dev.linter.cli import main, main_group


@pytest.mark.parametrize("args", [[], ["--help"], ["validate-files", "--help"], ["list-rules", "--help"], ["list-rules-all", "--help"]])
def test_standalone_examples_do_not_repeat_linter(args, capsys):
    # Arrange
    # Act
    main(args)
    output = capsys.readouterr().out
    # Assert
    assert "$ scitex-dev linter " in output and "linter linter" not in output


@pytest.mark.parametrize("prefix", ["scitex-dev", "scitex dev"])
def test_mounted_help_preserves_program_prefix(prefix):
    # Arrange
    root = click.Group()
    root.add_command(main_group, "linter")
    # Act
    result = CliRunner().invoke(root, ["linter", "--help"], prog_name=prefix)
    # Assert
    assert f"$ {prefix} linter validate-files src/" in result.output


def test_standalone_list_rules_json_remains_structured(capsys):
    # Arrange
    # Act
    code = main(["list-rules", "--json"])
    output = json.loads(capsys.readouterr().out)
    # Assert
    assert code == 0 and output and all("id" in rule for rule in output)


def test_standalone_unknown_command_still_refuses():
    # Arrange
    # Act
    code = main(["unknown-owned-test-command"])
    # Assert
    assert code == 2
