"""`scitex-dev ecosystem list --category` filters by ECOSYSTEM category."""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands
from scitex_dev._ecosystem._core import ECOSYSTEM


@pytest.fixture
def cli_main():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return main


def test_list_category_exit_code_zero(cli_main):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli_main, ["ecosystem", "list", "-c", "dataset", "-q"])
    # Assert
    assert result.exit_code == 0


def test_list_category_dataset_includes_openalex_local(cli_main):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli_main, ["ecosystem", "list", "-c", "dataset", "-q"])
    # Assert
    assert "openalex-local" in result.output.split()


def test_list_category_dataset_excludes_library_packages(cli_main):
    # Arrange
    runner = CliRunner()
    library_pkgs = {
        n
        for n, info in ECOSYSTEM.items()
        if info.get("category") == "library" and not info.get("archived")
    }
    # Act
    result = runner.invoke(cli_main, ["ecosystem", "list", "-c", "dataset", "-q"])
    listed = set(result.output.split())
    # Assert: none of the library packages should appear
    assert listed.isdisjoint(library_pkgs)


def test_list_category_unknown_returns_empty(cli_main):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        cli_main,
        ["ecosystem", "list", "-c", "this-category-does-not-exist", "-q"],
    )
    # Assert
    assert result.output.strip() == ""


def test_list_category_and_package_intersected(cli_main):
    # Arrange
    runner = CliRunner()
    # Act: intersection of -p scitex-io (library) and -c dataset (no overlap) → empty
    result = runner.invoke(
        cli_main,
        [
            "ecosystem",
            "list",
            "-p",
            "scitex-io",
            "-c",
            "dataset",
            "-q",
        ],
    )
    # Assert
    assert result.output.strip() == ""
