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


# EOF
