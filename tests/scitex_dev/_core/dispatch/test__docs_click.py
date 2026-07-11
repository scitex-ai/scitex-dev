"""Tests for `docs_click_group` (`_docs_click.py`).

No mocks: builds a REAL Click group via `click.testing.CliRunner`. Help
output never touches the doc-resolution path (`_run_docs_command`), so
these are safe to run without a real installed package's docs.

This module had zero test coverage before the `dispatch.py` -> `dispatch/`
package split (2026-07-11, CLI-standardization audit pass) -- these are
the first tests for it.
"""

from __future__ import annotations

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
