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
    command_is_wrappable,
    cron_command_for,
    degraded_job_names,
    derive_cron_expr,
    jobspec_field_names,
    lowering_losses,
    timer_to_cron_jobspec,
)
from scitex_dev.jobs import JobSpec


def _timer(
    name="t", *, schedule="", on_unit_active_sec=None, command=None, **kwargs
):
    return JobSpec(
        name=name,
        kind="timer",
        schedule=schedule,
        command=command if command is not None else "/bin/echo " + name,
        description="timer " + name,
        on_unit_active_sec=on_unit_active_sec,
        **kwargs,
    )


def _lossy_timer(name="t", **kwargs):
    """A timer carrying a loss that cron genuinely cannot honour.

    Uses ``venv`` rather than ``timeout_sec``. Since 2026-08-19 the
    lowering CARRIES ``timeout_sec`` as a ``timeout <N> `` prefix, so it
    is no longer blocking for an ordinary command — but the tests below
    are about how a refusal is REPORTED, not about which field triggers
    it. Pinning them to a specific blocking field is what made 22 of
    them fail on a change that altered neither the report nor the
    refusal machinery.
    """
    return _timer(name, on_unit_active_sec="15min", venv="/opt/leaf-venv", **kwargs)


def _compound_timer(name="t", **kwargs):
    """A timer whose command cron cannot bound with a ``timeout`` prefix.

    ``timeout N a && b`` bounds only ``a``, so this is the one shape for
    which ``timeout_sec`` is still a blocking loss.
    """
    return _timer(
        name,
        on_unit_active_sec="15min",
        command="/bin/echo a && /bin/echo b",
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


def test_lowering_losses_detects_timeout_sec_on_a_compound_command():
    # Arrange
    job = _compound_timer(timeout_sec=300)
    # Act
    losses = lowering_losses(job)
    # Assert
    assert [loss.field for loss in losses] == ["timeout_sec"]


def test_lowering_losses_reports_declared_timeout_value():
    # Arrange
    job = _compound_timer(timeout_sec=300)
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
    # Arrange — compound command, so timeout_sec is still among the losses.
    job = _compound_timer(
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
    job = _lossy_timer("j")
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert isinstance(raised, TimerLoweringError)


def test_lowering_error_names_the_job():
    # Arrange
    job = _lossy_timer("sac.fleet-reconcile")
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "sac.fleet-reconcile" in str(raised)


def test_lowering_error_names_the_target_surface():
    # Arrange
    job = _lossy_timer()
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "crontab" in str(raised)


def test_lowering_error_names_the_property():
    # Arrange
    job = _lossy_timer()
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "venv" in str(raised)


def test_lowering_error_names_the_optin_flag():
    # Arrange
    job = _lossy_timer()
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert "--allow-lossy-timer-lowering" in str(raised)


def test_lowering_error_exposes_structured_losses():
    # Arrange
    job = _lossy_timer()
    # Act
    raised = _capture_lowering_error(job)
    # Assert
    assert [loss.field for loss in raised.losses] == ["venv"]


def test_timer_to_cron_jobspec_allow_lossy_lowers_anyway():
    # Arrange
    job = _lossy_timer()
    # Act
    converted = timer_to_cron_jobspec(job, allow_lossy=True)
    # Assert
    assert converted.kind == "cron"


# --------------------------------------------------------------------------- #
# collect_cron_jobs — refuse by default, noisy when opted in                   #
# --------------------------------------------------------------------------- #


def test_collect_cron_jobs_raises_on_lossy_timer():
    # Arrange
    jobs = [_lossy_timer()]
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
    jobs = [_lossy_timer("j")]
    seen = []
    # Act
    collect_cron_jobs(jobs, allow_lossy=True, on_degrade=seen.append)
    # Assert
    assert len(seen) == 1


def test_collect_cron_jobs_degrade_report_marks_it_degraded():
    # Arrange
    jobs = [_lossy_timer("j")]
    seen = []
    # Act
    collect_cron_jobs(jobs, allow_lossy=True, on_degrade=seen.append)
    # Assert
    assert "DEGRADED" in seen[0]


def test_degrade_report_does_not_claim_to_have_refused():
    # Arrange — the job IS being deployed; "refusing" would be a lie.
    jobs = [_lossy_timer("j")]
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
    jobs = [_lossy_timer("j")]
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


def test_timeout_sec_is_classified_blocking_when_uncarryable():
    # Arrange — only a compound command can no longer carry the bound.
    job = _compound_timer(timeout_sec=300)
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
        _lossy_timer("lossy"),
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


# --------------------------------------------------------------------------- #
# collect_cron_jobs — on_refuse makes the refusal PER-JOB, not per-run         #
#                                                                              #
# Measured fleet-wide 2026-08-19: one unlowerable JobSpec left three hosts     #
# with zero cron entries and froze a fourth on stale lines, because the        #
# refusal aborted the whole reconcile. These pin the narrowed blast radius.    #
# --------------------------------------------------------------------------- #


def test_on_refuse_suppresses_the_raise():
    # Arrange
    jobs = [_lossy_timer()]
    # Act
    raised = _capture(lambda: collect_cron_jobs(jobs, on_refuse=lambda _e: None))
    # Assert
    assert raised is None


def test_on_refuse_receives_the_lowering_error():
    # Arrange
    seen: list[TimerLoweringError] = []
    jobs = [_lossy_timer()]
    # Act
    collect_cron_jobs(jobs, on_refuse=seen.append)
    # Assert
    assert isinstance(seen[0], TimerLoweringError)


def test_on_refuse_names_the_offending_job():
    # Arrange
    seen: list[TimerLoweringError] = []
    jobs = [_lossy_timer("bad")]
    # Act
    collect_cron_jobs(jobs, on_refuse=seen.append)
    # Assert
    assert seen[0].job_name == "bad"


def test_refused_job_is_left_out_of_the_merged_block():
    # Arrange
    jobs = [_lossy_timer("bad")]
    # Act
    merged, _, _ = collect_cron_jobs(jobs, on_refuse=lambda _e: None)
    # Assert
    assert merged == []


def test_innocent_timer_survives_a_sibling_refusal():
    # Arrange
    jobs = [
        _lossy_timer("bad"),
        _timer("good", on_unit_active_sec="15min"),
    ]
    # Act
    merged, _, _ = collect_cron_jobs(jobs, on_refuse=lambda _e: None)
    # Assert
    assert [j.name for j in merged] == ["good"]


def test_cron_native_job_survives_a_timer_refusal():
    # Arrange
    native = JobSpec(
        name="native",
        kind="cron",
        schedule="*/5 * * * *",
        command="/bin/echo native",
        description="cron native",
    )
    jobs = [_lossy_timer("bad"), native]
    # Act
    merged, _, _ = collect_cron_jobs(jobs, on_refuse=lambda _e: None)
    # Assert
    assert [j.name for j in merged] == ["native"]


def test_refused_job_is_not_counted_as_lowered():
    # Arrange
    jobs = [
        _lossy_timer("bad"),
        _timer("good", on_unit_active_sec="15min"),
    ]
    # Act
    _, _, lowered = collect_cron_jobs(jobs, on_refuse=lambda _e: None)
    # Assert
    assert lowered == 1


def test_every_refusal_is_reported_not_just_the_first():
    # Arrange
    seen: list[TimerLoweringError] = []
    jobs = [
        _lossy_timer("bad1"),
        _lossy_timer("bad2"),
    ]
    # Act
    collect_cron_jobs(jobs, on_refuse=seen.append)
    # Assert
    assert [e.job_name for e in seen] == ["bad1", "bad2"]


# --------------------------------------------------------------------------- #
# timeout_sec is CARRIED onto the cron line, not dropped and not refused       #
#                                                                              #
# Design agreed with sac 2026-08-19. The bound is declared once on the         #
# JobSpec; each rail materialises it natively. Putting `timeout N ` in         #
# JobSpec.command instead would break the SYSTEMD rail silently, because       #
# resolve_execstart absolutises only the head token.                           #
# --------------------------------------------------------------------------- #


def test_timeout_sec_no_longer_refuses_a_plain_command():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    losses = blocking_losses(job)
    # Assert
    assert losses == ()


def test_timeout_sec_becomes_a_timeout_prefix():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=300)
    # Act
    lowered = timer_to_cron_jobspec(job)
    # Assert
    assert lowered.command == "timeout 300 /bin/echo t"


def test_a_job_without_timeout_sec_is_left_alone():
    # Arrange
    job = _timer(on_unit_active_sec="15min")
    # Act
    lowered = timer_to_cron_jobspec(job)
    # Assert
    assert lowered.command == "/bin/echo t"


def test_the_declared_seconds_reach_the_prefix():
    # Arrange
    job = _timer(on_unit_active_sec="15min", timeout_sec=14400)
    # Act
    lowered = timer_to_cron_jobspec(job)
    # Assert
    assert lowered.command.startswith("timeout 14400 ")


def test_a_compound_command_is_not_wrappable():
    # Arrange
    command = "/bin/echo a && /bin/echo b"
    # Act
    wrappable = command_is_wrappable(command)
    # Assert
    assert wrappable is False


def test_a_plain_command_is_wrappable():
    # Arrange
    command = "sac accounts refresh --all --include-active"
    # Act
    wrappable = command_is_wrappable(command)
    # Assert
    assert wrappable is True


def test_a_compound_command_still_refuses_rather_than_lying():
    # Arrange — `timeout N a && b` would bound only `a`, so a wrap here
    # would deploy a job that LOOKS bounded and is not.
    job = JobSpec(
        name="compound",
        kind="timer",
        schedule="",
        command="/bin/echo a && /bin/echo b",
        description="compound timer",
        on_unit_active_sec="15min",
        timeout_sec=300,
    )
    # Act
    fields = [loss.field for loss in blocking_losses(job)]
    # Assert
    assert fields == ["timeout_sec"]


def test_a_compound_command_is_never_silently_wrapped():
    # Arrange
    job = JobSpec(
        name="compound",
        kind="timer",
        schedule="",
        command="/bin/echo a && /bin/echo b",
        description="compound timer",
        on_unit_active_sec="15min",
        timeout_sec=300,
    )
    # Act
    rendered = cron_command_for(job)
    # Assert
    assert rendered == "/bin/echo a && /bin/echo b"


def test_the_fleet_case_now_lowers_cleanly():
    # Arrange — the exact JobSpec shape that left three hosts with zero
    # cron entries on 2026-08-19 (sac accounts-refresh, timeout_sec=120).
    job = JobSpec(
        name="scitex-agent-container-accounts-refresh",
        kind="timer",
        schedule="",
        command="sac accounts refresh --all --include-active",
        description="refresh accounts",
        on_unit_active_sec="15min",
        timeout_sec=120,
    )
    # Act
    merged, _, _ = collect_cron_jobs([job])
    # Assert
    assert merged[0].command == "timeout 120 sac accounts refresh --all --include-active"
