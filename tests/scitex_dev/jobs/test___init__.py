#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the canonical federated job contract (``scitex_dev.jobs``)."""

from __future__ import annotations

import dataclasses

import pytest

from scitex_dev.jobs import (
    ALLOWED_KINDS,
    ENTRY_POINT_GROUP,
    JobSpec,
    discover_jobs,
    jobs_of_kind,
)


def _mock_timer_provider():
    return [
        JobSpec(
            name="mockpkg.refresh",
            kind="timer",
            schedule="*/5 * * * *",
            command="mock refresh",
            description="mock timer job",
            on_unit_active_sec="5min",
        )
    ]


def test_entry_point_group_is_scitex_dev_jobs():
    # Arrange
    # Act
    value = ENTRY_POINT_GROUP
    # Assert
    assert value == "scitex_dev.jobs"


def test_allowed_kinds_are_service_timer_cron():
    # Arrange
    expected = frozenset({"service", "timer", "cron"})
    # Act
    actual = ALLOWED_KINDS
    # Assert
    assert actual == expected


def test_jobspec_is_frozen():
    # Arrange
    spec = JobSpec(
        name="a.b", kind="cron", schedule="* * * * *", command="x", description="d"
    )
    # Act
    # Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.__setattr__("name", "other")


def test_jobspec_cron_minimal_fields_roundtrip():
    # Arrange
    spec = JobSpec(
        name="p.t",
        kind="cron",
        schedule="0 * * * *",
        command="x",
        description="d",
    )
    # Act
    # Assert
    assert spec.kind == "cron"


def test_jobspec_systemd_optional_fields_default_to_none():
    # Arrange
    spec = JobSpec(
        name="p.t",
        kind="cron",
        schedule="0 * * * *",
        command="x",
        description="d",
    )
    # Act
    triple = (spec.on_boot_sec, spec.on_unit_active_sec, spec.timeout_sec)
    # Assert
    assert triple == (None, None, None)


def test_jobspec_restart_policy_defaults_to_no():
    # Arrange
    spec = JobSpec(
        name="p.t",
        kind="cron",
        schedule="0 * * * *",
        command="x",
        description="d",
    )
    # Act
    # Assert
    assert spec.restart_policy == "no"


def test_jobspec_timer_full_roundtrip():
    # Arrange
    # Act
    spec = JobSpec(
        name="sac.accounts-refresh",
        kind="timer",
        schedule="0 */4 * * *",
        command="sac accounts refresh --all",
        description="rotate tokens",
        on_boot_sec="15min",
        on_unit_active_sec="4h",
        timeout_sec=120,
    )
    # Assert
    assert (spec.kind, spec.on_boot_sec, spec.on_unit_active_sec, spec.timeout_sec) == (
        "timer",
        "15min",
        "4h",
        120,
    )


def test_jobspec_service_full_roundtrip():
    # Arrange
    # Act
    spec = JobSpec(
        name="scitex-todo.dashboard",
        kind="service",
        schedule="",
        command="scitex-todo serve --port 8051",
        description="dashboard",
        on_boot_sec="15s",
        restart_policy="on-failure",
        timeout_sec=30,
    )
    # Assert
    assert (spec.kind, spec.restart_policy, spec.on_boot_sec) == (
        "service",
        "on-failure",
        "15s",
    )


# --------------------------------------------------------------------- #
# validate() — every invalid combination raises ValueError at construction
# --------------------------------------------------------------------- #


def test_jobspec_raises_on_unknown_kind():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="not in"):
        JobSpec(
            name="x.y",
            kind="bogus",
            schedule="* * * * *",
            command="c",
            description="d",
        )


def test_jobspec_raises_on_empty_name():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="name must be non-empty"):
        JobSpec(
            name="",
            kind="cron",
            schedule="* * * * *",
            command="c",
            description="d",
        )


def test_jobspec_raises_on_empty_command():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="command must be non-empty"):
        JobSpec(
            name="x.y",
            kind="cron",
            schedule="* * * * *",
            command="",
            description="d",
        )


def test_jobspec_service_raises_when_schedule_is_set():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="schedule must be empty"):
        JobSpec(
            name="p.service",
            kind="service",
            schedule="*/5 * * * *",
            command="x",
            description="d",
        )


def test_jobspec_service_raises_when_on_unit_active_sec_is_set():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="on_unit_active_sec must be None"):
        JobSpec(
            name="p.service",
            kind="service",
            schedule="",
            command="x",
            description="d",
            on_unit_active_sec="4h",
        )


def test_jobspec_timer_raises_when_neither_cadence_field_is_set():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="needs either on_unit_active_sec or a schedule"):
        JobSpec(
            name="p.timer",
            kind="timer",
            schedule="",
            command="x",
            description="d",
        )


def test_jobspec_timer_accepts_cron_schedule_without_explicit_cadence():
    # Arrange
    # Act
    spec = JobSpec(
        name="p.timer",
        kind="timer",
        schedule="*/10 * * * *",
        command="x",
        description="d",
    )
    # Assert
    assert spec.on_unit_active_sec is None


def test_jobspec_timer_raises_on_restart_policy_other_than_no():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="restart_policy"):
        JobSpec(
            name="p.timer",
            kind="timer",
            schedule="*/5 * * * *",
            command="x",
            description="d",
            restart_policy="on-failure",
        )


def test_jobspec_cron_raises_on_empty_schedule():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="schedule must be a 5-field cron"):
        JobSpec(
            name="p.cron",
            kind="cron",
            schedule="",
            command="x",
            description="d",
        )


def test_jobspec_cron_raises_on_non_five_field_schedule():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="exactly 5 cron fields"):
        JobSpec(
            name="p.cron",
            kind="cron",
            schedule="0 0 * *",  # only 4 fields
            command="x",
            description="d",
        )


def test_jobspec_cron_raises_when_on_boot_sec_is_set():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="on_boot_sec must be None"):
        JobSpec(
            name="p.cron",
            kind="cron",
            schedule="0 * * * *",
            command="x",
            description="d",
            on_boot_sec="15s",
        )


def test_jobspec_cron_raises_when_on_unit_active_sec_is_set():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="on_unit_active_sec must be None"):
        JobSpec(
            name="p.cron",
            kind="cron",
            schedule="0 * * * *",
            command="x",
            description="d",
            on_unit_active_sec="4h",
        )


def test_jobspec_raises_on_unknown_restart_policy():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="restart_policy"):
        JobSpec(
            name="p.service",
            kind="service",
            schedule="",
            command="x",
            description="d",
            restart_policy="bogus",
        )


# --------------------------------------------------------------------- #
# discover_jobs — federation + dedup + provider isolation
# --------------------------------------------------------------------- #


def test_discover_jobs_includes_builtin_ci_watch():
    # Arrange
    # Act
    names = {j.name for j in discover_jobs()}
    # Assert
    assert "ci-watch" in names


def test_discover_jobs_includes_builtin_quota_keepalive():
    # Arrange
    # Act
    names = {j.name for j in discover_jobs()}
    # Assert
    assert "quota-keepalive" in names


def test_discover_jobs_builtin_ci_watch_is_cron_kind():
    # Arrange
    # Act
    spec = next(j for j in discover_jobs() if j.name == "ci-watch")
    # Assert
    assert spec.kind == "cron"


def test_discover_jobs_merges_mock_provider():
    # Arrange
    # Act
    names = {j.name for j in discover_jobs(extra_providers=[_mock_timer_provider])}
    # Assert
    assert "mockpkg.refresh" in names


def test_discover_jobs_keeps_builtins_alongside_mock_provider():
    # Arrange
    # Act
    names = {j.name for j in discover_jobs(extra_providers=[_mock_timer_provider])}
    # Assert
    assert "ci-watch" in names


def test_discover_jobs_tolerates_failing_provider():
    # Arrange
    def bad_provider():
        raise RuntimeError("boom")

    # Act
    names = {j.name for j in discover_jobs(extra_providers=[bad_provider])}
    # Assert
    assert "ci-watch" in names


def test_discover_jobs_dedupes_first_provider_wins():
    # Arrange
    def dup_provider():
        return [
            JobSpec(
                name="ci-watch",
                kind="cron",
                schedule="0 0 * * *",
                command="OVERRIDDEN",
                description="should not win",
            )
        ]

    # Act
    spec = next(
        j for j in discover_jobs(extra_providers=[dup_provider]) if j.name == "ci-watch"
    )
    # Assert
    assert "OVERRIDDEN" not in spec.command


def test_discover_jobs_skips_non_jobspec_objects():
    # Arrange
    def junk_provider():
        return ["not a jobspec"]

    # Act
    names = {j.name for j in discover_jobs(extra_providers=[junk_provider])}
    # Assert
    assert "ci-watch" in names


def test_discover_jobs_loads_real_entry_point_provider(installed_job_provider):
    # Arrange
    # Act
    names = {j.name for j in discover_jobs()}
    # Assert
    assert "testpkg.sysjob" in names


def test_jobs_of_kind_timer_finds_real_entry_point_job(installed_job_provider):
    # Arrange
    # Act
    names = {j.name for j in jobs_of_kind("timer")}
    # Assert
    assert "testpkg.sysjob" in names


def test_jobs_of_kind_service_finds_real_entry_point_job(installed_job_provider):
    # Arrange
    # Act
    names = {j.name for j in jobs_of_kind("service")}
    # Assert
    assert "testpkg.svc" in names


def test_jobs_of_kind_cron_includes_builtin_ci_watch():
    # Arrange
    # Act
    names = {j.name for j in jobs_of_kind("cron")}
    # Assert
    assert "ci-watch" in names


# EOF
