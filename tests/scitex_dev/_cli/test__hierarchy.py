"""The real Click hierarchy view shares the inert Python catalog."""

import json
from dataclasses import asdict

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev.hierarchy_providers import list_hierarchy_providers
from tests.scitex_dev.hierarchy_providers._fixtures import distribution


def test_cli_json_matches_public_metadata_rows(tmp_path):
    # Arrange
    distribution(tmp_path)
    expected = [asdict(r) for r in list_hierarchy_providers(path=[tmp_path])]
    # Act
    result = CliRunner().invoke(
        main, ["hierarchy", "list", "--path", str(tmp_path), "--json"]
    )
    # Assert
    assert (result.exit_code, json.loads(result.stdout)) == (0, expected)


def test_cli_honors_the_root_json_option(tmp_path):
    # Arrange
    distribution(tmp_path)
    # Act
    result = CliRunner().invoke(
        main, ["--json", "hierarchy", "list", "--path", str(tmp_path)]
    )
    # Assert
    assert (result.exit_code, json.loads(result.stdout)[0]["distribution"]) == (
        0,
        "owned-example",
    )


def test_cli_reports_empty_catalog_scope_in_text(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["hierarchy", "list", "--path", str(tmp_path)])
    # Assert
    assert (result.exit_code, result.stdout.strip()) == (
        0,
        "0 hierarchy provider declarations (metadata only).",
    )


def test_cli_filters_using_normalized_owner(tmp_path):
    # Arrange
    distribution(tmp_path)
    distribution(tmp_path, owner="other-owner", slot="two")
    # Act
    result = CliRunner().invoke(
        main,
        [
            "hierarchy",
            "list",
            "--path",
            str(tmp_path),
            "--package",
            "Owned_Example",
            "--json",
        ],
    )
    # Assert
    assert (result.exit_code, [r["name"] for r in json.loads(result.stdout)]) == (
        0,
        ["owned-example"],
    )


@pytest.mark.parametrize("target", ["module_only", "module:get_nodes [extra]"])
def test_cli_fails_loudly_for_invalid_metadata(tmp_path, target):
    # Arrange
    distribution(tmp_path, target=target)
    # Act
    result = CliRunner().invoke(
        main, ["hierarchy", "list", "--path", str(tmp_path), "--json"]
    )
    # Assert
    assert (result.exit_code, "needs module:attribute" in result.output) == (1, True)


def test_cli_rejects_a_missing_search_directory(tmp_path):
    # Arrange
    missing = tmp_path / "missing"
    # Act
    result = CliRunner().invoke(main, ["hierarchy", "list", "--path", str(missing)])
    # Assert
    assert (result.exit_code, "does not exist" in result.output) == (2, True)


def test_root_help_places_hierarchy_under_introspection():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["--help"])
    # Assert
    assert (
        result.exit_code == 0
        and "hierarchy" in result.stdout.split("Introspection:", 1)[1]
    )
