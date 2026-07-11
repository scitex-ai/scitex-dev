"""Registration smoke test for `scitex-dev skills explain-self`
(`_explain_self_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`.
Help-only -- the command itself spends real Anthropic API credits per
invocation (see its own help text), so behavioural coverage of the
underlying engine lives in `test__self_explain.py`, not here.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli import main as cli


def test_explain_self_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "explain-self", "--help"])
    # Assert
    assert result.exit_code == 0


def test_deprecated_self_explain_alias_help_exits_zero():
    # Arrange -- the old (deprecated) hyphenation must still resolve.
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "self-explain", "--help"])
    # Assert
    assert result.exit_code == 0
