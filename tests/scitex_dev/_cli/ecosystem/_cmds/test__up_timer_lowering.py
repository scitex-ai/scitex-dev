#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._cli.ecosystem._cmds._up_timer_lowering.

Pure helpers — no I/O, no monkeypatch. One assertion per test.
"""

from __future__ import annotations

from scitex_dev._cli.ecosystem._cmds._up_timer_lowering import (
    TimerLoweringError,
    accounted_fields,
    blocking_losses,
    collect_cron_jobs,
    degraded_job_names,
    derive_cron_expr,
    jobspec_field_names,
    lowering_losses,
    timer_to_cron_jobspec,
)
from scitex_dev.jobs import JobSpec


def _timer(name="t", *, schedule="", on_unit_active_sec=None, **kwargs):
    return JobSpec(
        name=name,
        kind="timer",
        schedule=schedule,
        command="/bin/echo " + name,
        description="timer " + name,
        on_unit_active_sec=on_unit_active_sec,
        **kwargs,
    )


def _capture(call):
    """Run ``call`` and return the exception it raised (or None).

    Keeps the raise-path tests at exactly one assertion each (STX-TQ007)
    while still letting each one interrogate a DIFFERENT facet of the
    error — the job name, the surface, the property, the opt-in flag.
    """
    try:
        call()
    except Exception as exc:  # noqa: BLE001 — the assertion inspects it
        return exc
    return None


def _capture_lowering_error(job):
    return _capture(lambda: timer_to_cron_jobspec(job))


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


# --------------------------------------------------------------------------- #
# lowering_losses — the pure guarantee-dropping detector                       #
# --------------------------------------------------------------------------- #


def test_lowering_losses_empty_for_lossless_timer():
    # Arrange — cadence only; nothing cron cannot carry.
    job = _timer(on_unit_active_sec="15min")
    # Act
    losses = lowering_losses(job)
    # Assert
    assert losses == ()


def test_lowering_losses_detects_timeout_sec():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    losses = lowering_losses(job)
    # Assert
    assert [loss.field for loss in losses] == ["timeout_sec"]


def test_lowering_losses_reports_declared_timeout_value():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    losses = lowering_losses(job)
    # Assert
    assert losses[0].declared == 300


def test_lowering_losses_detects_on_boot_sec():
    # Arrange
    job = _timer(on_unit_active_sec="4h", on_boot_sec="15min")
    # Act
    losses = lowering_losses(job)
    # Assert
    assert [loss.field for loss in losses] == ["on_boot_sec"]


def test_lowering_losses_detects_venv():
    # Arrange
    job = _timer(on_unit_active_sec="4h", venv="/home/x/proj/.venv")
    # Act
    losses = lowering_losses(job)
    # Assert
    assert [loss.field for loss in losses] == ["venv"]


def test_lowering_losses_detects_all_three_together():
    # Arrange
    job = _timer(
        on_unit_active_sec="4h",
        timeout_sec=120,
        on_boot_sec="15min",
        venv="/v",
    )
    # Act
    losses = lowering_losses(job)
    # Assert
    assert [loss.field for loss in losses] == [
        "timeout_sec",
        "on_boot_sec",
        "venv",
    ]


def test_lowering_losses_empty_for_non_timer_kind():
    # Arrange — cron-native jobs never go through the lowering.
    job = _cron()
    # Act
    losses = lowering_losses(job)
    # Assert
    assert losses == ()


def test_lowering_losses_every_entry_carries_a_remedy():
    # Arrange
    job = _timer(on_unit_active_sec="4h", timeout_sec=1, on_boot_sec="1s", venv="/v")
    # Act
    losses = lowering_losses(job)
    # Assert — a loud failure that says nothing actionable is just noise.
    assert all(loss.remedy for loss in losses)


def test_every_jobspec_field_is_classified_by_the_lowering():
    # Arrange — guard rail: a NEW JobSpec field must be explicitly
    # classified (preserved / translated / inapplicable / loss-detected),
    # otherwise the lowering would silently drop it — the original bug.
    declared = jobspec_field_names()
    # Act
    unclassified = declared - accounted_fields()
    # Assert
    assert unclassified == frozenset()


# --------------------------------------------------------------------------- #
# timer_to_cron_jobspec — fails loud by default                                #
# --------------------------------------------------------------------------- #


def test_timer_to_cron_jobspec_lowers_lossless_timer_cleanly():
    # Arrange
    job = _timer(on_unit_active_sec="15min")
    # Act
    converted = timer_to_cron_jobspec(job)
    # Assert
    assert converted.schedule == "*/15 * * * *"


def test_timer_to_cron_jobspec_raises_on_declared_timeout():
    # Arrange
    job = _timer(name="j", on_unit_active_sec="15min", timeout_sec=300)
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert isinstance(raised, TimerLoweringError)


def test_lowering_error_names_the_job():
    # Arrange
    job = _timer(
        name="sac.fleet-reconcile", on_unit_active_sec="15min", timeout_sec=300
    )
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "sac.fleet-reconcile" in str(raised)


def test_lowering_error_names_the_target_surface():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "crontab" in str(raised)


def test_lowering_error_names_the_property():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "timeout_sec" in str(raised)


def test_lowering_error_names_the_optin_flag():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "--allow-lossy-timer-lowering" in str(raised)


def test_lowering_error_exposes_structured_losses():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert [loss.field for loss in raised.losses] == ["timeout_sec"]


def test_timer_to_cron_jobspec_allow_lossy_lowers_anyway():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    converted = timer_to_cron_jobspec(job, allow_lossy=True)
    # Assert
    assert converted.kind == "cron"


# --------------------------------------------------------------------------- #
# collect_cron_jobs — refuse by default, noisy when opted in                   #
# --------------------------------------------------------------------------- #


def test_collect_cron_jobs_raises_on_lossy_timer():
    # Arrange
    jobs = [_timer(on_unit_active_sec="15min", timeout_sec=300)]
    # Act
    raised = _capture(lambda: collect_cron_jobs(jobs))
    # Assert
    assert isinstance(raised, TimerLoweringError)


def test_collect_cron_jobs_allows_lossless_timers_without_optin():
    # Arrange
    jobs = [_timer(on_unit_active_sec="15min")]
    # Act
    merged, _, _ = collect_cron_jobs(jobs)
    # Assert
    assert len(merged) == 1


def test_collect_cron_jobs_allow_lossy_emits_a_degrade_report():
    # Arrange
    jobs = [_timer(name="j", on_unit_active_sec="15min", timeout_sec=300)]
    seen = []
    # Act
    collect_cron_jobs(jobs, allow_lossy=True, on_degrade=seen.append)
    # Assert
    assert len(seen) == 1


def test_collect_cron_jobs_degrade_report_marks_it_degraded():
    # Arrange
    jobs = [_timer(name="j", on_unit_active_sec="15min", timeout_sec=300)]
    seen = []
    # Act
    collect_cron_jobs(jobs, allow_lossy=True, on_degrade=seen.append)
    # Assert
    assert "DEGRADED" in seen[0]


def test_degrade_report_does_not_claim_to_have_refused():
    # Arrange — the job IS being deployed; "refusing" would be a lie.
    jobs = [_timer(name="j", on_unit_active_sec="15min", timeout_sec=300)]
    seen = []
    # Act
    collect_cron_jobs(jobs, allow_lossy=True, on_degrade=seen.append)
    # Assert
    assert "refusing" not in seen[0]


def test_collect_cron_jobs_allow_lossy_is_silent_for_lossless_timers():
    # Arrange
    jobs = [_timer(on_unit_active_sec="15min")]
    seen = []
    # Act
    collect_cron_jobs(jobs, allow_lossy=True, on_degrade=seen.append)
    # Assert
    assert seen == []


def test_collect_cron_jobs_allow_lossy_still_installs_the_entry():
    # Arrange
    jobs = [_timer(name="j", on_unit_active_sec="15min", timeout_sec=300)]
    # Act
    merged, _, _ = collect_cron_jobs(jobs, allow_lossy=True)
    # Assert
    assert [j.name for j in merged] == ["j"]


# --------------------------------------------------------------------------- #
# degraded_job_names                                                           #
# --------------------------------------------------------------------------- #


def test_on_boot_sec_alone_does_not_refuse_the_lowering():
    # Arrange — a dropped PREFERENCE, not a dropped guarantee.
    job = _timer(on_unit_active_sec="4h", on_boot_sec="5min")
    # Act
    converted = timer_to_cron_jobspec(job)
    # Assert
    assert converted.kind == "cron"


def test_on_boot_sec_is_classified_advisory():
    # Arrange
    job = _timer(on_unit_active_sec="4h", on_boot_sec="5min")
    # Act
    blocking = blocking_losses(job)
    # Assert
    assert blocking == ()


def test_timeout_sec_is_classified_blocking():
    # Arrange
    job = _timer(on_unit_active_sec="4h", timeout_sec=300)
    # Act
    blocking = blocking_losses(job)
    # Assert
    assert [loss.field for loss in blocking] == ["timeout_sec"]


def test_venv_is_classified_blocking():
    # Arrange
    job = _timer(on_unit_active_sec="4h", venv="/v")
    # Act
    blocking = blocking_losses(job)
    # Assert
    assert [loss.field for loss in blocking] == ["venv"]


def test_advisory_loss_is_reported_without_the_optin():
    # Arrange — advisory means non-blocking, NOT unreported.
    jobs = [_timer(name="j", on_unit_active_sec="4h", on_boot_sec="5min")]
    seen = []
    # Act
    collect_cron_jobs(jobs, on_degrade=seen.append)
    # Assert
    assert "NOTICE" in seen[0]


def test_advisory_notice_names_the_dropped_field():
    # Arrange
    jobs = [_timer(name="j", on_unit_active_sec="4h", on_boot_sec="5min")]
    seen = []
    # Act
    collect_cron_jobs(jobs, on_degrade=seen.append)
    # Assert
    assert "on_boot_sec" in seen[0]


def test_degraded_job_names_lists_only_lossy_timers():
    # Arrange
    jobs = [
        _cron(name="c"),
        _timer(name="clean", on_unit_active_sec="15min"),
        _timer(name="lossy", on_unit_active_sec="15min", timeout_sec=300),
    ]
    # Act
    names = degraded_job_names(jobs)
    # Assert
    assert names == ["lossy"]




# --------------------------------------------------------------------------- #
# on_calendar — a crontab line has no timezone                                  #
# --------------------------------------------------------------------------- #


def _calendar_timer():
    """A timer whose schedule is anchored to a wall clock IN A ZONE."""
    return JobSpec(
        name="p-timer",
        kind="timer",
        schedule="",
        command="c",
        description="d",
        on_calendar="*-*-* 04:30:00 Asia/Tokyo",
    )


def test_lowering_reports_on_calendar_as_a_loss():
    """cron carries no timezone, so the zone is dropped on the way down."""
    # Arrange
    job = _calendar_timer()
    # Act
    losses = lowering_losses(job)
    # Assert
    assert any(loss.field == "on_calendar" for loss in losses)


def test_on_calendar_loss_is_blocking():
    """A dropped GUARANTEE, not a preference.

    The same JobSpec would fire at a different wall-clock time on every
    host whose TZ differs, and move twice a year wherever DST applies.
    """
    # Arrange
    job = _calendar_timer()
    # Act
    loss = next(l for l in lowering_losses(job) if l.field == "on_calendar")
    # Assert
    assert loss.blocking


def test_on_calendar_loss_names_the_timezone_consequence():
    """The report has to say WHY, or the operator cannot judge the trade."""
    # Arrange
    job = _calendar_timer()
    # Act
    loss = next(l for l in lowering_losses(job) if l.field == "on_calendar")
    # Assert
    assert "timezone" in loss.consequence


def test_timer_without_on_calendar_reports_no_such_loss():
    """An interval timer loses nothing here — the guard must not cry wolf."""
    # Arrange
    job = JobSpec(
        name="p-timer",
        kind="timer",
        schedule="",
        command="c",
        description="d",
        on_unit_active_sec="15min",
    )
    # Act
    losses = lowering_losses(job)
    # Assert
    assert not any(loss.field == "on_calendar" for loss in losses)


# EOF
