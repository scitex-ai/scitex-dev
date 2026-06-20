#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._cli.ecosystem._cmds._up_timer_lowering.

Pure helpers — no I/O, no monkeypatch. One assertion per test.
"""

from __future__ import annotations

from scitex_dev._cli.ecosystem._cmds._up_timer_lowering import (
    collect_cron_jobs,
    derive_cron_expr,
    timer_to_cron_jobspec,
)
from scitex_dev.jobs import JobSpec


def _timer(name="t", *, schedule="", on_unit_active_sec=None):
    return JobSpec(
        name=name,
        kind="timer",
        schedule=schedule,
        command="/bin/echo " + name,
        description="timer " + name,
        on_unit_active_sec=on_unit_active_sec,
    )


def _cron(name="c", *, schedule="0 * * * *"):
    return JobSpec(
        name=name,
        kind="cron",
        schedule=schedule,
        command="/bin/echo " + name,
        description="cron " + name,
    )


# --------------------------------------------------------------------------- #
# derive_cron_expr — translation table                                         #
# --------------------------------------------------------------------------- #


def test_derive_cron_expr_preserves_explicit_5_field_schedule():
    # Arrange
    job = _timer(schedule="*/3 * * * *")
    # Act
    result = derive_cron_expr(job)
    # Assert
    assert result == "*/3 * * * *"


def test_derive_cron_expr_minutes_cadence():
    # Arrange
    job = _timer(on_unit_active_sec="15min")
    # Act
    result = derive_cron_expr(job)
    # Assert
    assert result == "*/15 * * * *"


def test_derive_cron_expr_hours_cadence():
    # Arrange
    job = _timer(on_unit_active_sec="4h")
    # Act
    result = derive_cron_expr(job)
    # Assert
    assert result == "0 */4 * * *"


def test_derive_cron_expr_days_cadence():
    # Arrange
    job = _timer(on_unit_active_sec="2d")
    # Act
    result = derive_cron_expr(job)
    # Assert
    assert result == "0 0 */2 * *"


def test_derive_cron_expr_falls_back_to_hourly_on_unknown():
    # Arrange
    job = _timer(on_unit_active_sec="weeks-pretty-please")
    # Act
    result = derive_cron_expr(job)
    # Assert
    assert result == "0 * * * *"


def test_derive_cron_expr_rejects_out_of_range_minutes():
    # Arrange — 60min would be ``*/60 * * * *`` which is invalid cron.
    job = _timer(on_unit_active_sec="60min")
    # Act
    result = derive_cron_expr(job)
    # Assert — fallback to hourly.
    assert result == "0 * * * *"


def test_derive_cron_expr_rejects_out_of_range_hours():
    # Arrange — 24h overflows the hour field; fall back.
    job = _timer(on_unit_active_sec="24h")
    # Act
    result = derive_cron_expr(job)
    # Assert
    assert result == "0 * * * *"


# --------------------------------------------------------------------------- #
# timer_to_cron_jobspec — kind flip                                            #
# --------------------------------------------------------------------------- #


def test_timer_to_cron_jobspec_kind_flips_to_cron():
    # Arrange
    job = _timer(on_unit_active_sec="4h")
    # Act
    converted = timer_to_cron_jobspec(job)
    # Assert
    assert converted.kind == "cron"


def test_timer_to_cron_jobspec_preserves_command():
    # Arrange
    job = _timer(name="zzz", on_unit_active_sec="15min")
    # Act
    converted = timer_to_cron_jobspec(job)
    # Assert
    assert converted.command == job.command


def test_timer_to_cron_jobspec_preserves_name():
    # Arrange
    job = _timer(name="sac.accounts-refresh", on_unit_active_sec="4h")
    # Act
    converted = timer_to_cron_jobspec(job)
    # Assert
    assert converted.name == "sac.accounts-refresh"


def test_timer_to_cron_jobspec_writes_derived_schedule():
    # Arrange
    job = _timer(on_unit_active_sec="4h")
    # Act
    converted = timer_to_cron_jobspec(job)
    # Assert
    assert converted.schedule == "0 */4 * * *"


# --------------------------------------------------------------------------- #
# collect_cron_jobs — mixed-kind merge                                         #
# --------------------------------------------------------------------------- #


def test_collect_cron_jobs_preserves_cron_native():
    # Arrange
    jobs = [_cron(name="a"), _timer(name="b", on_unit_active_sec="4h")]
    # Act
    merged, _, _ = collect_cron_jobs(jobs)
    # Assert
    assert merged[0].name == "a"


def test_collect_cron_jobs_appends_lowered_timers():
    # Arrange
    jobs = [_cron(name="a"), _timer(name="b", on_unit_active_sec="4h")]
    # Act
    merged, _, _ = collect_cron_jobs(jobs)
    # Assert
    assert merged[-1].name == "b"


def test_collect_cron_jobs_counts_cron_native():
    # Arrange
    jobs = [_cron(name="a"), _timer(name="b", on_unit_active_sec="4h")]
    # Act
    _, native, _ = collect_cron_jobs(jobs)
    # Assert
    assert native == 1


def test_collect_cron_jobs_counts_lowered_timers():
    # Arrange
    jobs = [_cron(name="a"), _timer(name="b", on_unit_active_sec="4h")]
    # Act
    _, _, lowered = collect_cron_jobs(jobs)
    # Assert
    assert lowered == 1


def test_collect_cron_jobs_drops_service_kind():
    # Arrange — service-kind doesn't belong in the crontab; supervisor takes it.
    svc = JobSpec(
        name="svc",
        kind="service",
        schedule="",
        command="/bin/true",
        description="d",
    )
    jobs = [svc, _cron(name="a")]
    # Act
    merged, _, _ = collect_cron_jobs(jobs)
    # Assert
    assert [j.name for j in merged] == ["a"]


# EOF
