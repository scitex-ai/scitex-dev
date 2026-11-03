"""Actual CLI catalog is parseable metadata, not a live capability assertion."""

import json

import click
from click.testing import CliRunner

from scitex_dev._cli._docs_cmds import register_docs_commands


def test_provider_catalog_is_structured_and_explicitly_not_live():
    # Arrange
    @click.group()
    def command():
        pass

    register_docs_commands(command)
    # Act
    result = CliRunner().invoke(command, ["docs", "providers", "--json"])
    payload = json.loads(result.stdout)
    observed = (result.exit_code, payload["schema_version"],
                isinstance(payload["providers"], list),
                isinstance(payload["ambiguous_names"], list),
                payload["declarations_only"], payload["live_verified"])
    # Assert
    assert observed == (0, "scitex-doc-providers/1", True, True, True, False)
