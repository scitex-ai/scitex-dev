#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI surface tests for `scitex-dev skills sync`.

No mocks: every check drives the real Click command in-process via
``CliRunner`` (so the worktree command code is exercised even though the
installed console script may predate it) and writes into a real
``tmp_path`` destination against the real installed ecosystem.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def cli_group():
    """Minimal click group with the skills commands registered."""
    # Arrange
    import click

    from scitex_dev._cli.skills._manage import register_skills_commands

    # Act
    @click.group()
    def cli():
        pass

    register_skills_commands(cli)
    # Assert
    return cli


class TestSyncHelp:
    def test_sync_help_exit_code_0(self, cli_group):
        # Arrange
        from click.testing import CliRunner

        runner = CliRunner()
        # Act
        result = runner.invoke(cli_group, ["skills", "sync", "--help"])
        # Assert
        assert result.exit_code == 0

    def test_sync_help_shows_dry_run(self, cli_group):
        # Arrange
        from click.testing import CliRunner

        runner = CliRunner()
        # Act
        result = runner.invoke(cli_group, ["skills", "sync", "--help"])
        # Assert
        assert "--dry-run" in result.output

    def test_sync_help_shows_dest(self, cli_group):
        # Arrange
        from click.testing import CliRunner

        runner = CliRunner()
        # Act
        result = runner.invoke(cli_group, ["skills", "sync", "--help"])
        # Assert
        assert "--dest" in result.output

    def test_sync_help_shows_package(self, cli_group):
        # Arrange
        from click.testing import CliRunner

        runner = CliRunner()
        # Act
        result = runner.invoke(cli_group, ["skills", "sync", "--help"])
        # Assert
        assert "--package" in result.output

    def test_sync_is_listed_in_group_help(self, cli_group):
        # Arrange
        from click.testing import CliRunner

        runner = CliRunner()
        # Act
        result = runner.invoke(cli_group, ["skills", "--help"])
        # Assert
        assert "sync" in result.output


class TestSyncDryRun:
    """`--dry-run` previews against the real installed ecosystem without
    touching the destination. Driven in-process via ``CliRunner`` so the
    command code under test is the worktree copy (the installed console
    script may predate this command)."""

    def test_dry_run_exit_code_0(self, cli_group, tmp_path):
        # Arrange
        from click.testing import CliRunner

        dest = tmp_path / "skills-out"
        runner = CliRunner()
        # Act
        result = runner.invoke(
            cli_group, ["skills", "sync", "--dest", str(dest), "--dry-run"]
        )
        # Assert
        assert result.exit_code == 0

    def test_dry_run_mentions_dest(self, cli_group, tmp_path):
        # Arrange
        from click.testing import CliRunner

        dest = tmp_path / "skills-out"
        runner = CliRunner()
        # Act
        result = runner.invoke(
            cli_group, ["skills", "sync", "--dest", str(dest), "--dry-run"]
        )
        # Assert
        assert str(dest) in result.output

    def test_dry_run_does_not_create_dest(self, cli_group, tmp_path):
        # Arrange
        from click.testing import CliRunner

        dest = tmp_path / "skills-out"
        runner = CliRunner()
        # Act
        runner.invoke(cli_group, ["skills", "sync", "--dest", str(dest), "--dry-run"])
        # Assert
        assert not dest.exists()


@pytest.fixture()
def twice_synced(cli_group, tmp_path):
    """Sync the real ecosystem twice into the same dest; return both results.

    In-process via ``CliRunner`` (exercises the worktree command). Setup is
    shared and non-trivial (two full installs), so it lives in a fixture and
    each assertion gets its own one-assert test (STX-TQ007).
    """
    # Arrange
    import json

    from click.testing import CliRunner

    dest = tmp_path / "skills-out"
    runner = CliRunner()
    # Act
    first = runner.invoke(cli_group, ["skills", "sync", "--dest", str(dest)])
    second = runner.invoke(cli_group, ["skills", "sync", "--dest", str(dest), "--json"])
    second_payload = json.loads(second.output) if second.exit_code == 0 else {}
    # Assert
    return first, second, second_payload


class TestSyncIdempotentCLI:
    """A second sync into the same dest reports no changes."""

    def test_first_sync_exit_code_0(self, twice_synced):
        # Arrange
        first, _second, _payload = twice_synced
        # Act
        code = first.exit_code
        # Assert
        assert code == 0

    def test_second_sync_exit_code_0(self, twice_synced):
        # Arrange
        _first, second, _payload = twice_synced
        # Act
        code = second.exit_code
        # Assert
        assert code == 0

    def test_second_sync_json_changed_false(self, twice_synced):
        # Arrange
        _first, _second, payload = twice_synced
        # Act
        changed = payload.get("changed")
        # Assert
        assert changed is False


# EOF
