"""Tests for `_print_export_result` (`_helpers.py`)."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli.skills._manage._helpers import (
    _default_skills_destination,
    _ensure_symlink,
    _print_export_result,
    _report_symlink,
    _require_external_destination,
)


def test_print_export_result_empty_says_no_skills_found():
    # Arrange
    @click.command()
    def _cmd():
        _print_export_result({}, "/tmp/dest")

    runner = CliRunner()
    # Act
    result = runner.invoke(_cmd, [])
    # Assert
    assert "No skills found" in result.output


def test_print_export_result_json_mode_emits_parseable_json():
    # Arrange
    import json

    exported = {"scitex-dev": ["/tmp/dest/scitex-dev/a.md"]}

    @click.command()
    def _cmd():
        _print_export_result(exported, "/tmp/dest", as_json=True)

    runner = CliRunner()
    # Act
    result = runner.invoke(_cmd, [])
    # Assert
    assert json.loads(result.output) == {"scitex-dev": ["/tmp/dest/scitex-dev/a.md"]}


def test_print_export_result_empty_json_is_one_object():
    # Arrange
    @click.command()
    def _cmd():
        _print_export_result({}, "/tmp/dest", as_json=True)

    # Act
    result = CliRunner().invoke(_cmd, [])

    # Assert
    assert (result.exit_code, result.output) == (0, "{}\n")


def test_ensure_symlink_atomically_replaces_wrong_and_broken_link(tmp_path):
    # Arrange
    desired = tmp_path / "desired"
    desired.mkdir()
    link = tmp_path / "skills"
    link.symlink_to(tmp_path / "missing", target_is_directory=True)

    # Act
    _ensure_symlink(link, desired)

    # Assert
    assert (link.is_symlink(), link.resolve(strict=True)) == (
        True,
        desired.resolve(),
    )


def test_ensure_symlink_fails_loud_for_real_directory(tmp_path):
    # Arrange
    desired = tmp_path / "desired"
    desired.mkdir()
    link = tmp_path / "skills"
    link.mkdir()

    # Act
    # Assert
    with pytest.raises(click.ClickException, match="is not a symlink"):
        _ensure_symlink(link, desired)


def test_default_destination_uses_scitex_config_user_scope(tmp_path):
    # Arrange
    state_root = tmp_path / "state"
    resolver = lambda package, name: state_root / package / name

    # Act
    result = _default_skills_destination(_user_path_fn=resolver)

    # Assert
    assert result == state_root / "dev" / "skills"


def test_destination_realpath_inside_git_authority_fails_loud(tmp_path):
    # Arrange
    authority = tmp_path / "dotfiles"
    (authority / ".git").mkdir(parents=True)
    state = authority / "src" / ".scitex"
    state.mkdir(parents=True)
    apparent = tmp_path / "home" / ".scitex"
    apparent.parent.mkdir()
    apparent.symlink_to(state, target_is_directory=True)
    destination = apparent / "dev" / "skills"

    # Act
    # Assert
    with pytest.raises(click.ClickException, match="inside Git authority"):
        _require_external_destination(destination)


def test_destination_outside_git_authority_is_accepted(tmp_path):
    # Arrange
    destination = tmp_path / "state" / "dev" / "skills"

    # Act
    result = _require_external_destination(destination)

    # Assert
    assert result == destination


def test_json_stdout_is_one_object_and_projection_diagnostic_is_stderr(tmp_path):
    # Arrange
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"

    @click.command()
    def _cmd():
        _report_symlink(link, target)
        _print_export_result({"example": [target / "SKILL.md"]}, target, True)

    # Act
    result = CliRunner().invoke(_cmd, [])

    # Assert
    assert (
        result.exit_code,
        result.stdout.count("{") == 1,
        "linked:" in result.stderr,
        "linked:" in result.stdout,
    ) == (0, True, True, False)
