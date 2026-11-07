"""Completion generation must not execute a foreign executable from PATH."""

import shutil
import subprocess

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
    ) == (0, True)


@pytest.mark.skipif(shutil.which("bash") is None, reason="requires real Bash")
def test_installed_completion_can_be_sourced_with_spaces_and_quotes_in_state_path(
    tmp_path,
):
    # Arrange
    home = tmp_path / "owned home"
    home.mkdir()
    state = tmp_path / "state's directory"
    bash = shutil.which("bash")
    # Act
    install = CliRunner().invoke(
        main,
        ["install-shell-completion", "--shell", "bash", "--yes"],
        env={"HOME": str(home), "SCITEX_DIR": str(state)},
    )
    loaded = subprocess.run(
        [
            bash,
            "--noprofile",
            "--norc",
            "-c",
            'source "$1" && declare -F _scitex_dev_completion',
            "owned-check",
            str(home / ".bashrc"),
        ],
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )
    # Assert
    assert (install.exit_code, loaded.returncode, loaded.stdout.strip()) == (
        0,
        0,
        "_scitex_dev_completion",
    )
