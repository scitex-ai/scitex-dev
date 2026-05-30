#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI + behaviour tests for ecosystem cron/systemd/daemon job aggregation.

These tests avoid the forbidden ``monkeypatch`` fixture: the CLI ``list``
commands run against the real built-in jobs, and systemd unit-file
writing is exercised against a real temp directory through the same code
path the CLI uses (builders + filesystem write).
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _systemd as sd


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


def test_systemd_list_with_only_builtins_reports_empty(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "list"])
    # Assert
    assert "No systemd-kind jobs discovered." in result.output


def test_daemon_list_reports_empty_by_default(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "daemon", "list"])
    # Assert
    assert "No daemon-kind jobs discovered." in result.output


# ----------------------------------------------------------------------
# systemd unit-file writing against a REAL temp directory (no patching):
# exercises the exact builders + write path the CLI install command uses.
# ----------------------------------------------------------------------


def _write_units(job: JobSpec, unit_dir):
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / f"{job.name}.service"
    timer = unit_dir / f"{job.name}.timer"
    service.write_text(sd.build_service_unit(job), encoding="utf-8")
    timer.write_text(sd.build_timer_unit(job), encoding="utf-8")
    return service, timer


def _systemd_job():
    return JobSpec(
        name="mockpkg.refresh",
        schedule="0 */4 * * *",
        command="mockpkg refresh --all",
        description="mock systemd job",
        kind="systemd",
        on_boot_sec="15min",
        on_unit_active_sec="4h",
        timeout_sec=120,
    )


def test_systemd_write_creates_service_file(tmp_path):
    # Arrange
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    # Act
    service, _ = _write_units(_systemd_job(), unit_dir)
    # Assert
    assert service.exists()


def test_systemd_write_creates_timer_file(tmp_path):
    # Arrange
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    # Act
    _, timer = _write_units(_systemd_job(), unit_dir)
    # Assert
    assert timer.exists()


def test_systemd_written_timer_is_persistent(tmp_path):
    # Arrange
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    # Act
    _, timer = _write_units(_systemd_job(), unit_dir)
    # Assert
    assert "Persistent=true" in timer.read_text()


def test_systemd_written_service_is_oneshot(tmp_path):
    # Arrange
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    # Act
    service, _ = _write_units(_systemd_job(), unit_dir)
    # Assert
    assert "Type=oneshot" in service.read_text()


# EOF
