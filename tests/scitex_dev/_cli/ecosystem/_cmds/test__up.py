#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem up``.

Real fakes only (PA-306 / STX-NM). The ``run_up`` function exposes
every external touch (systemctl runner, unit dir, echo) as a kwarg
seam so tests substitute hand-rolled callables / ``tmp_path``
without ``monkeypatch`` and without touching the real
``~/.config/systemd/user``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev.jobs import JobSpec
from scitex_dev._cli.ecosystem._cmds import _up


def _completed(rc: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _ok_systemctl(args, **_):
    return _completed(rc=0)


def _provider_one_service():
    return [
        JobSpec(
            name="mock.dashboard",
            kind="service",
            schedule="",
            command="mock-dashboard serve --port 9999",
            description="mock long-running dashboard",
            on_boot_sec="5s",
            restart_policy="on-failure",
        )
    ]


def _provider_one_timer():
    return [
        JobSpec(
            name="mock.refresh",
            kind="timer",
            schedule="*/15 * * * *",
            command="mock refresh",
            description="mock periodic refresh",
            on_unit_active_sec="15min",
        )
    ]


# --------------------------------------------------------------------- #
# Result type                                                           #
# --------------------------------------------------------------------- #


def test_upresult_default_master_unit_written_is_false():
    # Arrange
    # Act
    result = _up.UpResult()
    # Assert
    assert result.master_unit_written is False


def test_upresult_default_cron_jobs_installed_is_zero():
    # Arrange
    # Act
    result = _up.UpResult()
    # Assert
    assert result.cron_jobs_installed == 0


def test_upresult_default_unit_failures_is_empty():
    # Arrange
    # Act
    result = _up.UpResult()
    # Assert
    assert result.unit_failures == ()


# --------------------------------------------------------------------- #
# _write_master_unit — pure file write, idempotent                      #
# --------------------------------------------------------------------- #


def test_write_master_unit_creates_the_file(tmp_path):
    # Arrange
    # Act
    path = _up._write_master_unit(tmp_path)
    # Assert
    assert path.exists()


def test_write_master_unit_writes_canonical_unit_name(tmp_path):
    # Arrange
    # Act
    path = _up._write_master_unit(tmp_path)
    # Assert
    assert path.name == "scitex-dev-ecosystem-reconcile.service"


def test_write_master_unit_unit_text_contains_execstart_to_ecosystem_up(tmp_path):
    # Arrange
    # Act
    path = _up._write_master_unit(tmp_path)
    # Assert
    assert "scitex-dev ecosystem up --yes" in path.read_text(encoding="utf-8")


def test_write_master_unit_unit_keeps_oneshot_remainafter_yes(tmp_path):
    # Arrange — bug fix from host bring-up (lead msg b7ef3777): the
    # master reconcile MUST be Type=oneshot + RemainAfterExit=yes so
    # `systemctl --user enable --now` returns immediately on a clean
    # reconcile rather than reporting the oneshot as flipped-back-
    # inactive (which surfaces as "failed" under the daemon).
    # Act
    path = _up._write_master_unit(tmp_path)
    # Assert
    assert "RemainAfterExit=yes" in path.read_text(encoding="utf-8")


def test_write_master_unit_unit_is_oneshot(tmp_path):
    # Arrange
    # Act
    path = _up._write_master_unit(tmp_path)
    # Assert
    assert "Type=oneshot" in path.read_text(encoding="utf-8")


def test_write_master_unit_is_idempotent(tmp_path):
    # Arrange
    first = _up._write_master_unit(tmp_path).read_text(encoding="utf-8")
    # Act
    second = _up._write_master_unit(tmp_path).read_text(encoding="utf-8")
    # Assert
    assert first == second


# --------------------------------------------------------------------- #
# _install_systemd_units — writes the right files per kind              #
# --------------------------------------------------------------------- #


def test_install_systemd_units_writes_service_file_for_service_kind(tmp_path):
    # Arrange
    jobs = _provider_one_service()
    # Act
    _up._install_systemd_units(jobs=jobs, unit_dir=tmp_path, echo=lambda _: None)
    # Assert
    assert (tmp_path / "mock.dashboard.service").exists()


def test_install_systemd_units_does_not_write_timer_for_service_kind(tmp_path):
    # Arrange
    jobs = _provider_one_service()
    # Act
    _up._install_systemd_units(jobs=jobs, unit_dir=tmp_path, echo=lambda _: None)
    # Assert
    assert not (tmp_path / "mock.dashboard.timer").exists()


def test_install_systemd_units_writes_service_file_for_timer_kind(tmp_path):
    # Arrange
    jobs = _provider_one_timer()
    # Act
    _up._install_systemd_units(jobs=jobs, unit_dir=tmp_path, echo=lambda _: None)
    # Assert
    assert (tmp_path / "mock.refresh.service").exists()


def test_install_systemd_units_writes_timer_file_for_timer_kind(tmp_path):
    # Arrange
    jobs = _provider_one_timer()
    # Act
    _up._install_systemd_units(jobs=jobs, unit_dir=tmp_path, echo=lambda _: None)
    # Assert
    assert (tmp_path / "mock.refresh.timer").exists()


def test_install_systemd_units_returns_service_count_for_timer_kind(tmp_path):
    # Arrange
    jobs = _provider_one_timer()
    # Act
    services, _ = _up._install_systemd_units(
        jobs=jobs, unit_dir=tmp_path, echo=lambda _: None
    )
    # Assert — a timer kind writes BOTH a .service (oneshot) AND a .timer.
    assert services == 1


def test_install_systemd_units_returns_timer_count_for_timer_kind(tmp_path):
    # Arrange
    jobs = _provider_one_timer()
    # Act
    _, timers = _up._install_systemd_units(
        jobs=jobs, unit_dir=tmp_path, echo=lambda _: None
    )
    # Assert
    assert timers == 1


def test_install_systemd_units_returns_zero_timers_for_service_kind(tmp_path):
    # Arrange
    jobs = _provider_one_service()
    # Act
    _, timers = _up._install_systemd_units(
        jobs=jobs, unit_dir=tmp_path, echo=lambda _: None
    )
    # Assert
    assert timers == 0


# --------------------------------------------------------------------- #
# _systemctl — runner failure isolated                                  #
# --------------------------------------------------------------------- #


def test_systemctl_returns_true_on_rc0():
    # Arrange
    # Act
    ok = _up._systemctl(["daemon-reload"], runner=_ok_systemctl, echo=lambda _: None)
    # Assert
    assert ok is True


def test_systemctl_returns_false_on_non_zero_rc():
    # Arrange
    def runner(args, **_):
        return _completed(rc=1, stderr="boom")

    # Act
    ok = _up._systemctl(["enable", "x.service"], runner=runner, echo=lambda _: None)
    # Assert
    assert ok is False


def test_systemctl_returns_false_when_systemctl_binary_missing():
    # Arrange
    def runner(args, **_):
        raise FileNotFoundError("systemctl")

    # Act
    ok = _up._systemctl(["daemon-reload"], runner=runner, echo=lambda _: None)
    # Assert
    assert ok is False


# --------------------------------------------------------------------- #
# run_up — top-level                                                    #
# --------------------------------------------------------------------- #


def test_run_up_with_no_extra_providers_writes_no_systemd_units(tmp_path):
    # Arrange
    # Act — only built-in cron jobs exist by default; no systemd-kind built-ins.
    result = _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
    )
    # Assert
    assert result.service_units_written == 0


def test_run_up_without_yes_does_not_install_cron(tmp_path):
    # Arrange
    # Act
    result = _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
    )
    # Assert — without --yes we never touch the crontab.
    assert result.cron_jobs_installed == 0


def test_run_up_with_install_master_unit_writes_master(tmp_path):
    # Arrange
    # Act
    result = _up.run_up(
        yes=False,
        install_master_unit=True,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
    )
    # Assert
    assert result.master_unit_written is True


def test_run_up_master_unit_path_exists_after_install(tmp_path):
    # Arrange
    # Act
    _up.run_up(
        yes=False,
        install_master_unit=True,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
    )
    # Assert
    assert (tmp_path / "scitex-dev-ecosystem-reconcile.service").exists()


def test_run_up_without_install_master_unit_does_not_write_master(tmp_path):
    # Arrange
    # Act
    result = _up.run_up(
        yes=False,
        install_master_unit=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
    )
    # Assert
    assert result.master_unit_written is False


# EOF
