#!/usr/bin/env python3
"""Tests for the periodic-job scheduler's decision logic.

Every test passes `now` and the last-run table explicitly — the module
under test owns no clock, so nothing here sleeps and nothing is timing
dependent.
"""

from __future__ import annotations

import pytest

from scitex_dev._supervisor._schedule import (
    cadence_sec,
    due_jobs,
    is_due,
    offsets_for,
    package_of,
    parse_duration,
    unschedulable,
)
from scitex_dev.jobs import JobSpec


def _timer(name: str = "pkg.do-thing", **overrides) -> JobSpec:
    base = dict(
        name=name,
        kind="timer",
        schedule="",
        command="true",
        description="d",
        on_unit_active_sec="5min",
    )
    base.update(overrides)
    return JobSpec(**base)


def _service(name: str = "pkg.serve-thing") -> JobSpec:
    return JobSpec(
        name=name,
        kind="service",
        schedule="",
        command="true",
        description="d",
        restart_policy="always",
    )


# --- parse_duration: refuses rather than defaults ---------------------------


def test_parse_duration_reads_minutes():
    # Arrange
    text = "15min"
    # Act
    result = parse_duration(text)
    # Assert
    assert result == 900.0


def test_parse_duration_reads_hours():
    # Arrange
    text = "2h"
    # Act
    result = parse_duration(text)
    # Assert
    assert result == 7200.0


def test_parse_duration_refuses_an_unknown_unit():
    """A silently-defaulted cadence is a job running wrong forever."""
    # Arrange
    text = "5fortnights"
    # Act
    parse = lambda: parse_duration(text)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="unknown unit"):
        parse()


def test_parse_duration_refuses_a_bare_unit():
    # Arrange
    text = "min"
    # Act
    parse = lambda: parse_duration(text)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="no leading number"):
        parse()


# --- package_of -------------------------------------------------------------


def test_package_of_reads_the_prefix():
    # Arrange
    name = "scitex-cards.watch-ci"
    # Act
    result = package_of(name)
    # Assert
    assert result == "scitex-cards"


def test_package_of_groups_legacy_bare_slugs():
    """A bare slug has no package; inventing one per job would spread them."""
    # Arrange
    name = "ci-watch"
    # Act
    result = package_of(name)
    # Assert
    assert result == ""


# --- cadence ----------------------------------------------------------------


def test_cadence_prefers_the_declared_interval():
    # Arrange
    job = _timer(on_unit_active_sec="10min")
    # Act
    result = cadence_sec(job)
    # Assert
    assert result == 600.0


def test_cadence_of_a_service_is_none():
    """A service runs continuously — it is not periodic."""
    # Arrange
    job = _service()
    # Act
    result = cadence_sec(job)
    # Assert
    assert result is None


def test_cadence_derives_from_a_step_cron_expression():
    # Arrange
    job = JobSpec(
        name="pkg.sweep-x", kind="cron", schedule="*/30 * * * *",
        command="true", description="d",
    )
    # Act
    result = cadence_sec(job)
    # Assert
    assert result == 1800.0


def test_cadence_is_none_for_an_unrecognised_cron_shape():
    """UNKNOWN, not a guessed default — the caller reports it by name."""
    # Arrange
    job = JobSpec(
        name="pkg.sweep-y", kind="cron", schedule="0 9 * * 1-5",
        command="true", description="d",
    )
    # Act
    result = cadence_sec(job)
    # Assert
    assert result is None


# --- offsets: alphabetical, recomputable by hand ----------------------------


def test_offsets_are_assigned_by_alphabetical_position():
    # Arrange
    packages = ["scitex-hpc", "scitex-cards", "sac"]
    # Act
    result = offsets_for(packages, spacing=20.0)
    # Assert — sac(0) < scitex-cards(1) < scitex-hpc(2)
    assert result == {"sac": 0.0, "scitex-cards": 20.0, "scitex-hpc": 40.0}


def test_offsets_are_stable_across_input_order():
    """Same packages, different order in, identical offsets out."""
    # Arrange
    forward = offsets_for(["a", "b", "c"])
    # Act
    backward = offsets_for(["c", "b", "a"])
    # Assert
    assert forward == backward


# --- is_due -----------------------------------------------------------------


def test_a_job_run_recently_is_not_due():
    # Arrange
    job = _timer(on_unit_active_sec="5min")
    # Act
    result = is_due(job, now=1000.0, last_run=900.0, offset=0.0)
    # Assert — 100s elapsed against a 300s cadence
    assert result is False


def test_a_job_past_its_cadence_is_due():
    # Arrange
    job = _timer(on_unit_active_sec="5min")
    # Act
    result = is_due(job, now=1300.0, last_run=900.0, offset=0.0)
    # Assert
    assert result is True


def test_a_never_run_job_waits_for_its_offset():
    """Cold start must not fire every job in the same instant."""
    # Arrange
    job = _timer()
    # Act
    result = is_due(job, now=10.0, last_run=None, offset=40.0)
    # Assert
    assert result is False


def test_a_never_run_job_fires_once_past_its_offset():
    # Arrange
    job = _timer()
    # Act
    result = is_due(job, now=41.0, last_run=None, offset=40.0)
    # Assert
    assert result is True


def test_a_service_is_never_due():
    # Arrange
    job = _service()
    # Act
    result = is_due(job, now=10_000.0, last_run=None, offset=0.0)
    # Assert
    assert result is False


# --- due_jobs ---------------------------------------------------------------


def test_due_jobs_returns_only_the_due_ones():
    # Arrange
    ready = _timer("a.do-x", on_unit_active_sec="1min")
    waiting = _timer("a.do-y", on_unit_active_sec="1h")
    # Act
    result = due_jobs(
        [ready, waiting], now=1000.0,
        last_runs={"a.do-x": 900.0, "a.do-y": 900.0},
        offsets={"a": 0.0},
    )
    # Assert
    assert [j.name for j in result] == ["a.do-x"]


def test_due_jobs_is_ordered_by_name():
    """Identical inputs must give identical output, or the logs wobble."""
    # Arrange
    jobs = [_timer("b.do-x"), _timer("a.do-x")]
    # Act
    result = due_jobs(jobs, now=10_000.0, last_runs={}, offsets={"a": 0.0, "b": 0.0})
    # Assert
    assert [j.name for j in result] == ["a.do-x", "b.do-x"]


# --- unschedulable: named, not silently dropped -----------------------------


def test_unschedulable_names_a_job_with_no_cadence():
    """"It never ran" and "it was never scheduled" must not look alike."""
    # Arrange
    job = JobSpec(
        name="pkg.sweep-z", kind="cron", schedule="0 9 * * 1-5",
        command="true", description="d",
    )
    # Act
    result = unschedulable([job])
    # Assert
    assert result[0][0] == "pkg.sweep-z"


def test_unschedulable_ignores_services():
    # Arrange
    job = _service()
    # Act
    result = unschedulable([job])
    # Assert
    assert result == []


# EOF
