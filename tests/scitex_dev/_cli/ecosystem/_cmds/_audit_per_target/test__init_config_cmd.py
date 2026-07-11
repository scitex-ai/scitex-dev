"""Registration smoke test for `ecosystem init-config` (`_init_config_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`.
See `test__cli_cmd.py` for why this file exists (per-module registration
guard for the `_audit_per_target/` package split).
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _make_group():
    @click.group()
    def root():
        pass

    register_ecosystem_commands(root)
    return root


def test_init_config_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_group(), ["ecosystem", "init-config", "--help"])
    # Assert
    assert result.exit_code == 0
