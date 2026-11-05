"""Completion generation must not execute a foreign executable from PATH."""

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_uses_current_click_without_running_path_executable(tmp_path, shell):
    # Arrange
    marker = tmp_path / "foreign-executable-ran"
    foreign = tmp_path / "scitex-dev"
    foreign.write_text(
        f"#!/bin/sh\nprintf foreign > '{marker}'\nprintf FOREIGN_SCRIPT\n"
    )
    foreign.chmod(0o700)
    # Act
    result = CliRunner().invoke(
        main, ["print-shell-completion", "--shell", shell], env={"PATH": str(tmp_path)}
    )
    # Assert
    assert (
        result.exit_code,
        "_SCITEX_DEV_COMPLETE" in result.stdout,
        "FOREIGN_SCRIPT" in result.stdout,
        marker.exists(),
    ) == (0, True, False, False)


def test_completion_is_available_without_installed_executables_on_path(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["print-shell-completion", "--shell", "bash"], env={"PATH": str(tmp_path)}
    )
    # Assert
    assert (
        result.exit_code,
        "_SCITEX_DEV_COMPLETE=bash_complete" in result.stdout,
    ) == (
        0,
        True,
    )
