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


def test_daemon_list_shows_provider_job(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "daemon", "list"])
    # Assert
    assert "testpkg.dmn" in result.output


def test_daemon_list_json_includes_provider_job(runner, installed_job_provider):
    # Arrange
    import json

    # Act
    result = runner.invoke(main, ["ecosystem", "daemon", "list", "--json"])
    # Assert
    assert any(j["name"] == "testpkg.dmn" for j in json.loads(result.output))


def test_daemon_exec_runs_provider_command(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "daemon", "exec", "testpkg.dmn"])
    # Assert
    assert "testpkg-daemon" in result.output


# EOF
