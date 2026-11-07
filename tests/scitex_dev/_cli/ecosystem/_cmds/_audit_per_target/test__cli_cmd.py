"""Registration smoke test for `ecosystem audit-cli` (`_cli_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`.
Guards against the class of bug this split (2026-07-10, PR #320 follow-up)
could introduce silently -- a command defined in its own file but never
wired into `_audit_per_target/__init__.py::register`, which would only
surface as a runtime "no such command" far from the module that broke.
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


def test_audit_cli_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_group(), ["ecosystem", "audit-cli", "--help"])
    # Assert
    assert result.exit_code == 0


def test_audit_cli_help_describes_the_base_installation():
    # Arrange -- the auditor ships in core, not a retired optional extra.
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_group(), ["ecosystem", "audit-cli", "--help"])
    # Assert
    assert "base installation" in " ".join(result.output.split())
