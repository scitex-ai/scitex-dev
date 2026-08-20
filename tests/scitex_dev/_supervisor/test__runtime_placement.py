#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The supervisor must honour host placement, because it is the executor.

`ecosystem up` has filtered by placement since #716. That was sufficient while
`up` lowered periodic jobs to crontab lines — filtering what it INSTALLED
filtered what RAN. ADR-0012 retired cron and moved execution into the
supervisor, and the placement filter stayed on the surface that no longer
executes anything.

Measured on 2026-08-20: `ci-watch` was declared for one host and running on
four, polling the same five repositories from each against a shared GitHub API
budget that was exhausting at the time. The declaration was present, correct,
honoured by `up`, and had no effect on the running system.

The load-bearing assertion is `test_excluded_job_is_not_armed_off_host` — the
branch that had never executed. Everything else here passed before the fix too.

No `monkeypatch`: the supervisor takes `discover_placement_fn` and
`placement_host` as seams (mirroring the pair `_up.py` already exposes), so
these tests hand it real callables rather than rewriting its internals.
"""

from __future__ import annotations

import logging

from scitex_dev._supervisor._runtime import Supervisor
from scitex_dev.jobs import JobSpec
from scitex_dev.jobs._placement import PlacementRecord, PlacementUnresolvable


def _job(name: str) -> JobSpec:
    return JobSpec(
        name=name,
        kind="timer",
        schedule="*/10 * * * *",
        command="true",
        description="test fixture",
    )


def _ci_watch_on_04() -> list[PlacementRecord]:
    return [PlacementRecord(job="ci-watch", hosts=("scitex-compute-04",))]


def _supervisor(*, host: str, jobs: list[JobSpec], placement=_ci_watch_on_04):
    return Supervisor(
        discover=lambda extra_providers=None: jobs,
        placement_host=host,
        discover_placement_fn=placement,
    )


class TestPlacementIsAppliedByTheExecutor:
    def test_excluded_job_is_not_armed_off_host(self):
        # Arrange -- ci-watch declared for compute-04; supervisor runs on 01
        sup = _supervisor(host="scitex-compute-01", jobs=[_job("ci-watch")])
        # Act
        armed = [j.name for j in sup.discover_periodic_jobs()]
        # Assert
        assert armed == []

    def test_placed_job_is_armed_on_its_declared_host(self):
        # Arrange
        sup = _supervisor(host="scitex-compute-04", jobs=[_job("ci-watch")])
        # Act
        armed = [j.name for j in sup.discover_periodic_jobs()]
        # Assert
        assert armed == ["ci-watch"]

    def test_undeclared_job_is_armed_everywhere(self):
        # Arrange -- UNSTATED means "no opinion yet", which arms
        sup = _supervisor(host="scitex-compute-01", jobs=[_job("some-other-job")])
        # Act
        armed = [j.name for j in sup.discover_periodic_jobs()]
        # Assert
        assert armed == ["some-other-job"]

    def test_service_jobs_stay_out_of_the_periodic_set(self):
        # Arrange -- placement must not disturb the service/periodic split
        service = JobSpec(
            name="a-service",
            kind="service",
            schedule="",
            command="true",
            description="d",
        )
        sup = _supervisor(
            host="scitex-compute-04",
            jobs=[service, _job("periodic")],
            placement=lambda: [],
        )
        # Act
        armed = [j.name for j in sup.discover_periodic_jobs()]
        # Assert
        assert armed == ["periodic"]


def _unresolvable() -> list[PlacementRecord]:
    raise PlacementUnresolvable("ci-watch", ("infra",), "scitex-compute-01")


class TestUnresolvablePlacement:
    def test_it_still_arms_the_job(self):
        # Arrange -- refusing to guess must not take the fleet's work down
        sup = _supervisor(
            host="scitex-compute-01",
            jobs=[_job("ci-watch")],
            placement=_unresolvable,
        )
        # Act
        armed = [j.name for j in sup.discover_periodic_jobs()]
        # Assert
        assert armed == ["ci-watch"]

    def test_it_warns_on_every_call_not_once(self, caplog):
        # Arrange -- a one-shot warning is how this becomes invisible again
        sup = _supervisor(
            host="scitex-compute-01",
            jobs=[_job("ci-watch")],
            placement=_unresolvable,
        )
        # Act
        with caplog.at_level(logging.WARNING):
            sup.discover_periodic_jobs()
            sup.discover_periodic_jobs()
        # Assert
        assert sum("placement unresolvable" in r.message for r in caplog.records) == 2


# EOF
