#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the canonical federated job contract (``scitex_dev.jobs``)."""

from __future__ import annotations

import dataclasses

import pytest

from scitex_dev.jobs import (
    ENTRY_POINT_GROUP,
    JobSpec,
    discover_jobs,
    jobs_of_kind,
)


def _mock_systemd_provider():
    return [
        JobSpec(
            name="mockpkg.refresh",
            schedule="*/5 * * * *",
            command="mock refresh",
            description="mock job",
            kind="systemd",
            on_unit_active_sec="5min",
        )
    ]


def test_entry_point_group_is_scitex_dev_jobs():
    # Arrange
    # Act
    value = ENTRY_POINT_GROUP
    # Assert
    assert value == "scitex_dev.jobs"


def test_jobspec_kind_defaults_to_cron():
    # Arrange
    # Act
    spec = JobSpec(name="p.t", schedule="0 * * * *", command="x", description="d")
    # Assert
    assert spec.kind == "cron"


def test_jobspec_systemd_fields_default_to_none():
    # Arrange
    # Act
    spec = JobSpec(name="p.t", schedule="0 * * * *", command="x", description="d")
    # Assert
    assert (spec.on_boot_sec, spec.on_unit_active_sec, spec.timeout_sec) == (
        None,
        None,
        None,
    )


def test_jobspec_is_frozen():
    # Arrange
    spec = JobSpec(name="a.b", schedule="* * * * *", command="x", description="d")
    # Act
    # Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.__setattr__("name", "other")


def test_jobspec_full_systemd_fields_roundtrip():
    # Arrange
    expected = ("systemd", "15min", "4h", 120)
    # Act
    spec = JobSpec(
        name="sac.accounts-refresh",
        schedule="0 */4 * * *",
        command="sac accounts refresh --all",
        description="rotate tokens",
        kind="systemd",
        on_boot_sec="15min",
        on_unit_active_sec="4h",
        timeout_sec=120,
    )
    # Assert
    assert (
        spec.kind,
        spec.on_boot_sec,
        spec.on_unit_active_sec,
        spec.timeout_sec,
    ) == expected


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
    names = {j.name for j in discover_jobs(extra_providers=[_mock_systemd_provider])}
    # Assert
    assert "mockpkg.refresh" in names


def test_discover_jobs_keeps_builtins_alongside_mock_provider():
    # Arrange
    # Act
    names = {j.name for j in discover_jobs(extra_providers=[_mock_systemd_provider])}
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


def test_jobs_of_kind_finds_real_entry_point_systemd_job(installed_job_provider):
    # Arrange
    # Act
    names = {j.name for j in jobs_of_kind("systemd")}
    # Assert
    assert "testpkg.sysjob" in names


def test_jobs_of_kind_filters_to_requested_kind():
    # Arrange
    def daemon_provider():
        return [
            JobSpec(
                name="mockpkg.daemon",
                schedule="* * * * *",
                command="run",
                description="d",
                kind="daemon",
            )
        ]

    # Act
    names = [j.name for j in jobs_of_kind("daemon", extra_providers=[daemon_provider])]
    # Assert
    assert names == ["mockpkg.daemon"]


# EOF
