#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex-dev's own host-placement declaration.

These pin a FLEET FACT, not a code shape: which of scitex-dev's jobs must run
on exactly one host. Both declared jobs are singletons because running them on
several hosts duplicates work against a shared resource — the released-version
reconciliation for deploy-freshness, and the shared GitHub API budget for
ci-watch.

The ci-watch assertion exists because on 2026-08-20 it was running on all four
hosts during a live exhaustion of that shared account, and nothing in the
JobSpec, the code, or any single host's view revealed that the other three
copies existed. A test is the only place that fact can be stated where a
reader will meet it.
"""

from __future__ import annotations

from scitex_dev._ecosystem_jobs._placement_provider import provide_placement


def _hosts_for(job: str) -> tuple[str, ...]:
    for record in provide_placement():
        if record.job == job:
            return tuple(record.hosts)
    raise AssertionError(f"{job!r} is not declared — it would arm on every host")


class TestCiWatchIsASingleton:
    def test_ci_watch_is_declared_at_all(self):
        # Arrange
        jobs = {r.job for r in provide_placement()}
        # Act
        declared = "ci-watch" in jobs
        # Assert
        assert declared is True

    def test_ci_watch_runs_on_exactly_one_host(self):
        # Arrange
        hosts = _hosts_for("ci-watch")
        # Act
        count = len(hosts)
        # Assert
        assert count == 1

    def test_ci_watch_shares_the_control_plane_host_with_deploy_freshness(self):
        # Arrange -- both are fleet-wide singletons; splitting them across two
        # hosts would mean two machines each believing they hold the control
        # plane, which is the condition this declaration exists to prevent.
        freshness = _hosts_for("scitex-dev-deploy-freshness")
        # Act
        ci_watch = _hosts_for("ci-watch")
        # Assert
        assert ci_watch == freshness


class TestDeployFreshnessStaysASingleton:
    def test_deploy_freshness_runs_on_exactly_one_host(self):
        # Arrange
        hosts = _hosts_for("scitex-dev-deploy-freshness")
        # Act
        count = len(hosts)
        # Assert
        assert count == 1


class TestOnlyGenuineSingletonsAreDeclared:
    """Undeclared already means "arm everywhere", so a wildcard is noise."""

    def test_no_record_declares_a_wildcard_host(self):
        # Arrange
        records = provide_placement()
        # Act
        wildcards = [r.job for r in records if "*" in r.hosts]
        # Assert
        assert wildcards == []

    def test_every_declared_job_names_at_least_one_host(self):
        # Arrange
        records = provide_placement()
        # Act
        empty = [r.job for r in records if not r.hosts]
        # Assert
        assert empty == []


# EOF
