"""Project CLI outputs and selection state through real command registration."""

import json
import os

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli._project import register
from scitex_dev.project import active_project_file, set_active_project


@pytest.fixture
def project_cli(tmp_path):
    """Use owned configuration and real project/Click implementations."""
    keys = ("SCITEX_DIR", "XDG_RUNTIME_DIR", "SCITEX_PROJECT")
    saved = {key: os.environ.get(key) for key in keys}
    os.environ["SCITEX_DIR"] = str(tmp_path)
    os.environ["XDG_RUNTIME_DIR"] = str(tmp_path)
    os.environ.pop("SCITEX_PROJECT", None)

    @click.group()
    def cli():
        """Synthetic root, with the actual project group."""

    register(cli)
    try:
        yield cli
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_get_reports_an_absent_selection(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "get"])
    # Assert
    assert result.stdout == "(none)\n"


def test_get_succeeds_without_a_selection(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "get", "--json"])
    # Assert
    assert result.exit_code == 0


def test_get_json_has_the_existing_machine_contract(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "get", "--json"])
    # Assert
    assert json.loads(result.stdout) == {"project": None, "env": None}


def test_canonical_get_emits_no_deprecation_diagnostics(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "get", "--json"])
    # Assert
    assert result.stderr == ""


def test_get_reads_the_persisted_selection(project_cli):
    # Arrange
    set_active_project("synthetic/alpha")
    # Act
    result = CliRunner().invoke(project_cli, ["project", "get"])
    # Assert
    assert result.stdout == "synthetic/alpha\n"


def test_get_honors_environment_precedence(project_cli):
    # Arrange
    set_active_project("synthetic/alpha")
    os.environ["SCITEX_PROJECT"] = "synthetic/beta"
    # Act
    result = CliRunner().invoke(project_cli, ["project", "get", "--json"])
    # Assert
    assert json.loads(result.stdout) == {
        "project": "synthetic/beta",
        "env": "synthetic/beta",
    }


def test_get_does_not_persist_an_environment_override(project_cli):
    # Arrange
    set_active_project("synthetic/alpha")
    os.environ["SCITEX_PROJECT"] = "synthetic/beta"
    # Act
    CliRunner().invoke(project_cli, ["project", "get"])
    # Assert
    assert active_project_file().read_text() == "synthetic/alpha\n"


def test_legacy_current_still_returns_the_machine_contract(project_cli):
    # Arrange
    set_active_project("synthetic/alpha")
    # Act
    result = CliRunner().invoke(project_cli, ["project", "current", "--json"])
    # Assert
    assert json.loads(result.stdout) == {"project": "synthetic/alpha", "env": None}


def test_legacy_current_preserves_success_status(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "current", "--json"])
    # Assert
    assert result.exit_code == 0


def test_legacy_warning_names_the_canonical_command_and_removal(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "current"])
    # Assert
    assert result.stderr == (
        "'current' is deprecated — use 'project get' (removed in v0.64)\n"
    )


def test_legacy_warning_is_once_per_shell_session(project_cli):
    # Arrange
    runner = CliRunner()
    runner.invoke(project_cli, ["project", "current"])
    # Act
    result = runner.invoke(project_cli, ["project", "current", "--json"])
    # Assert
    assert result.stderr == ""


def test_legacy_read_does_not_change_the_selection(project_cli):
    # Arrange
    set_active_project("synthetic/alpha")
    # Act
    CliRunner().invoke(project_cli, ["project", "current", "--json"])
    # Assert
    assert active_project_file().read_text() == "synthetic/alpha\n"


def test_legacy_options_are_validated_by_the_canonical_command(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "current", "--unknown"])
    # Assert
    assert result.exit_code == 2


def test_project_help_advertises_the_canonical_command(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "--help"])
    # Assert
    assert "get" in result.stdout


def test_project_help_omits_the_deprecated_spelling(project_cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(project_cli, ["project", "--help"])
    # Assert
    assert "current" not in result.stdout
