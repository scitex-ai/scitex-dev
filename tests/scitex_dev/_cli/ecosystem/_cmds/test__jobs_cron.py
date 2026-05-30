#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem cron``.

The ``list`` command runs against the real built-in jobs (no patching),
and ``install`` is exercised in ``--dry-run`` mode so no real crontab is
touched.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_cron_list_shows_builtin_ci_watch(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "list"])
    # Assert
    assert "ci-watch" in result.output


def test_cron_install_dry_run_emits_managed_block(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "install", "--dry-run"])
    # Assert
    assert "scitex-dev-ecosystem" in result.output


def test_cron_install_without_yes_refuses(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "install"])
    # Assert
    assert result.exit_code == 2


def test_cron_install_unknown_name_errors(runner):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "cron", "install", "--name", "no.such.job", "--dry-run"]
    )
    # Assert
    assert result.exit_code != 0


def test_cron_install_named_dry_run_filters_to_one_job(runner):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "cron", "install", "--name", "ci-watch", "--dry-run"]
    )
    # Assert
    assert "quota-keepalive" not in result.output


def test_cron_list_json_emits_array(runner):
    # Arrange
    import json

    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "list", "--json"])
    # Assert
    assert isinstance(json.loads(result.output), list)


def test_cron_group_help_lists_install_verb(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "--help"])
    # Assert
    assert "install" in result.output


def test_cron_uninstall_dry_run_does_not_require_yes(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "uninstall", "--dry-run"])
    # Assert
    assert result.exit_code == 0


def test_cron_uninstall_named_dry_run_does_not_require_yes(runner):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "cron", "uninstall", "--name", "ci-watch", "--dry-run"]
    )
    # Assert
    assert result.exit_code == 0


def test_cron_uninstall_without_yes_refuses(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "uninstall"])
    # Assert
    assert result.exit_code == 2


def test_cron_list_shows_provider_source_label(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "list", "--json"])
    # Assert
    assert "scitex-dev" in result.output


# EOF
