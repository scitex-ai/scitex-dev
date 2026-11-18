"""Tests for `docs_click_group` (`_docs_click.py`).

No mocks: builds a REAL Click group via `click.testing.CliRunner`. Help
output never touches the doc-resolution path (`_run_docs_command`), so
these are safe to run without a real installed package's docs.

This module had zero test coverage before the `dispatch.py` -> `dispatch/`
package split (2026-07-11, CLI-standardization audit pass) -- these are
the first tests for it.
"""

from __future__ import annotations

import shlex

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._core.dispatch import docs_click_group


def _make_root(package: str = "scitex-fake-pkg"):
    @click.group()
    def root():
        pass

    root.add_command(docs_click_group(package=package))
    return root


def test_docs_group_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["docs", "--help"])
    # Assert
    assert result.exit_code == 0


def test_docs_list_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["docs", "list", "--help"])
    # Assert
    assert result.exit_code == 0


def test_docs_get_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["docs", "get", "--help"])
    # Assert
    assert result.exit_code == 0


def test_bare_docs_group_prints_help_instead_of_erroring():
    # Arrange -- invoked with no subcommand.
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["docs"])
    # Assert
    assert result.exit_code == 0 and "Usage" in result.output


@pytest.mark.parametrize("name", ["docs", "manual"])
def test_every_factory_example_targets_a_registered_command(name):
    """An advertised example must resolve in the adapter's actual group."""
    # Arrange
    group = docs_click_group(package="scitex-fake-pkg", name=name)
    root = click.Group("owned")
    root.add_command(group)
    runner = CliRunner()
    # Act
    results = []
    for command in [group, *group.commands.values()]:
        for example in command._help_spec.examples:
            arguments = shlex.split(example.cmd.replace("{prog}", "owned"))[1:]
            result = runner.invoke(root, [*arguments, "--help"])
            results.append((example.cmd, result.exit_code, result.output))
    # Assert
    assert results and all(code == 0 for _, code, _ in results), results


def test_package_factory_does_not_advertise_global_search():
    # Arrange
    group = docs_click_group(package="scitex-fake-pkg")
    # Act
    result = CliRunner().invoke(group, ["--help"])
    # Assert
    assert result.exit_code == 0 and "search" not in result.output.lower()
