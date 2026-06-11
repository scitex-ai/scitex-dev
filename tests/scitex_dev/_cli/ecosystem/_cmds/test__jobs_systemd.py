#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem systemd``.

The ``list`` command runs against the real built-ins (all cron-kind, so
it legitimately reports no systemd jobs). Unit-file writing is exercised
against a real temp directory through the same builders the install
command uses — no patching of production internals.
"""

from __future__ import annotations

import os

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _systemd as sd


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_home(tmp_path):
    """Point ``$HOME`` at a temp dir for the duration of the test.

    ``Path.home()`` reads ``$HOME`` on POSIX, so the systemd CLI writes
    its unit files under the temp tree — real filesystem, no patching.
    """
    prev = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        yield tmp_path / ".config" / "systemd" / "user"
    finally:
        if prev is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = prev


def _systemd_job():
    return JobSpec(
        name="mockpkg.refresh",
        schedule="0 */4 * * *",
        command="mockpkg refresh --all",
        description="mock systemd job",
        kind="timer",
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


# ----------------------------------------------------------------------
# End-to-end CLI: a REAL entry-point provider (installed_job_provider) +
# a REAL temp $HOME exercise the actual install/uninstall command paths.
# ----------------------------------------------------------------------


def test_cli_systemd_list_shows_provider_job(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "list"])
    # Assert
    assert "testpkg.sysjob" in result.output


def test_cli_systemd_install_dry_run_emits_unit(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "install", "--dry-run"])
    # Assert
    assert "Type=oneshot" in result.output


def test_cli_systemd_install_without_yes_refuses(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "install"])
    # Assert
    assert result.exit_code == 2


def test_cli_systemd_install_writes_service(runner, installed_job_provider, temp_home):
    # Arrange
    # Act
    runner.invoke(main, ["ecosystem", "systemd", "install", "--yes"])
    # Assert
    assert (temp_home / "testpkg.sysjob.service").exists()


def test_cli_systemd_install_prints_enable_hint(
    runner, installed_job_provider, temp_home
):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "install", "--yes"])
    # Assert
    assert "systemctl --user enable --now testpkg.sysjob.timer" in result.output


def test_cli_systemd_uninstall_removes_units(runner, installed_job_provider, temp_home):
    # Arrange
    runner.invoke(main, ["ecosystem", "systemd", "install", "--yes"])
    # Act
    runner.invoke(main, ["ecosystem", "systemd", "uninstall", "--yes"])
    # Assert
    assert not (temp_home / "testpkg.sysjob.service").exists()


def test_cli_systemd_uninstall_without_yes_refuses(
    runner, installed_job_provider, temp_home
):
    # Arrange
    runner.invoke(main, ["ecosystem", "systemd", "install", "--yes"])
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "uninstall"])
    # Assert
    assert result.exit_code == 2


def test_cli_systemd_uninstall_dry_run_reports_target(
    runner, installed_job_provider, temp_home
):
    # Arrange
    runner.invoke(main, ["ecosystem", "systemd", "install", "--yes"])
    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "uninstall", "--dry-run"])
    # Assert
    assert "would remove" in result.output


def test_cli_systemd_list_json_includes_provider_job(runner, installed_job_provider):
    # Arrange
    import json

    # Act
    result = runner.invoke(main, ["ecosystem", "systemd", "list", "--json"])
    # Assert
    assert any(j["name"] == "testpkg.sysjob" for j in json.loads(result.output))


def test_cli_systemd_install_named_unknown_errors(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "systemd", "install", "--name", "no.such", "--dry-run"]
    )
    # Assert
    assert result.exit_code != 0


def test_cli_systemd_install_named_filters_to_one(
    runner, installed_job_provider, temp_home
):
    # Arrange
    # Act
    runner.invoke(
        main,
        ["ecosystem", "systemd", "install", "--name", "testpkg.sysjob", "--yes"],
    )
    # Assert
    assert (temp_home / "testpkg.sysjob.timer").exists()


# EOF
