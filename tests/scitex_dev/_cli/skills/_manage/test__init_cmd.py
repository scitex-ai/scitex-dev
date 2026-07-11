"""Registration smoke test for `scitex-dev skills init` (`_init_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli import main as cli


def test_skills_init_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "init", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_init_dry_run_reports_planned_files(tmp_path):
    # Arrange
    runner = CliRunner()
    dest = tmp_path / "skills-out"
    # Act
    result = runner.invoke(
        cli,
        [
            "skills",
            "init",
            "--package",
            "my-fake-package",
            "--dest",
            str(dest),
            "--dry-run",
        ],
    )
    # Assert
    assert result.exit_code == 0
