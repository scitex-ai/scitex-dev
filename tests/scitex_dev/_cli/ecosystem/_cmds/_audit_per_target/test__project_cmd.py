"""Registration smoke test for `ecosystem audit-project` (`_project_cmd.py`).

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


def test_audit_project_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_group(), ["ecosystem", "audit-project", "--help"])
    # Assert
    assert result.exit_code == 0
