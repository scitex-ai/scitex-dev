#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for systemd unit-file builders."""

from __future__ import annotations

from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _systemd as sd


def _job():
    return JobSpec(
        name="sac.accounts-refresh",
        schedule="0 */4 * * *",
        command="sac accounts refresh --all",
        description="rotate tokens",
        kind="systemd",
        on_boot_sec="15min",
        on_unit_active_sec="4h",
        timeout_sec=120,
    )


def test_service_unit_is_oneshot():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "Type=oneshot" in text


def test_service_unit_execstart_includes_command():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "ExecStart=/usr/bin/env sac accounts refresh --all" in text


def test_service_unit_includes_timeout():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "TimeoutStartSec=120s" in text


def test_service_unit_logs_to_journal():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "StandardOutput=journal" in text


def test_timer_unit_uses_declared_on_boot_sec():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "OnBootSec=15min" in text


def test_timer_unit_uses_declared_on_unit_active_sec():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "OnUnitActiveSec=4h" in text


def test_timer_unit_is_persistent():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "Persistent=true" in text


def test_timer_unit_points_at_service():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "Unit=sac.accounts-refresh.service" in text


def test_timer_default_on_boot_when_unset():
    # Arrange
    job = JobSpec(
        name="x.y", schedule="0 * * * *", command="c", description="d", kind="systemd"
    )
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert f"OnBootSec={sd.DEFAULT_ON_BOOT_SEC}" in text


def test_derive_on_unit_active_sec_from_minute_step():
    # Arrange
    # Act
    derived = sd.derive_on_unit_active_sec("*/10 * * * *")
    # Assert
    assert derived == "10min"


def test_derive_on_unit_active_sec_from_hour_step():
    # Arrange
    # Act
    derived = sd.derive_on_unit_active_sec("0 */4 * * *")
    # Assert
    assert derived == "4h"


def test_derive_on_unit_active_sec_fallback_for_unknown():
    # Arrange
    # Act
    derived = sd.derive_on_unit_active_sec("garbage")
    # Assert
    assert derived == sd.DEFAULT_ON_UNIT_ACTIVE_SEC


# EOF
