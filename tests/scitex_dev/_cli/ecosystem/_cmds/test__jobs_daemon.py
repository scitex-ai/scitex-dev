#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem daemon``."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_daemon_list_reports_empty_by_default(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "daemon", "list"])
    # Assert
    assert "No daemon-kind jobs discovered." in result.output


def test_daemon_exec_unknown_name_errors(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "daemon", "exec", "no.such.job"])
    # Assert
    assert result.exit_code != 0


# EOF
