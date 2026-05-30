#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem systemd``.

The ``list`` command runs against the real built-ins (all cron-kind, so
it legitimately reports no systemd jobs). Unit-file writing is exercised
against a real temp directory through the same builders the install
command uses — no patching of production internals.
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


def _write_units(job, unit_dir):
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / f"{job.name}.service"
    timer = unit_dir / f"{job.name}.timer"
    service.write_text(sd.build_service_unit(job), encoding="utf-8")
    timer.write_text(sd.build_timer_unit(job), encoding="utf-8")
    return service, timer


def test_systemd_list_with_only_builtins_reports_empty(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "list"])
    # Assert
    assert "No systemd-kind jobs discovered." in result.output


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
