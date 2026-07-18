"""Registration smoke test for `scitex-dev skills expand-tags`
(`_expand_tags_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli import main as cli


def test_expand_tags_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "expand-tags", "--help"])
    # Assert
    assert result.exit_code == 0


def test_deprecated_tags_expand_alias_help_exits_zero():
    # Arrange -- the old bare-noun-leading name must still resolve.
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "tags-expand", "--help"])
    # Assert
    assert result.exit_code == 0
