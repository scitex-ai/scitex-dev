"""Registration smoke test for `scitex-dev skills list` (`_list_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`.
This module (along with its siblings) had zero dedicated unit-test
coverage before the `_manage.py` -> `_manage/` package split (2026-07-11,
CLI-standardization audit pass); the pre-existing `test__manage.py`
(now `test__install_cmd.py`) only covered `skills collect`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli import main as cli


def test_skills_list_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "list", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_list_runs_against_the_real_registry():
    # Arrange -- scitex-dev itself always has skills installed (it ships
    # its own `_skills/` tree), so this is real, non-flaky coverage.
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "list", "--package", "scitex-dev"])
    # Assert
    assert result.exit_code == 0
