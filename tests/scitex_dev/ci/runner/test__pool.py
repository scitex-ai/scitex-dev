#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ephemeral CI-runner pool dispatcher (_pool) — no mocks.

The GitHub call, active-count, and launcher are injected as plain fakes
(Callables). One assertion per test, AAA markers throughout.
"""

from __future__ import annotations

import io

import pytest

from scitex_dev.ci.runner import _pool
from scitex_dev.ci.runner._pool import QueuedJob


def _jobs(n):
    return [QueuedJob(repo=f"ywatanabe1989/r{i}", run_id=1000 + i) for i in range(n)]


# -- decide_launches (pure load-balancing rule) -----------------------------


def test_decide_launches_fills_free_slots():
    # Arrange
    queued = _jobs(5)
    # Act
    picks = _pool.decide_launches(queued, active=2, max_concurrent=4)
    # Assert — 4-2=2 free slots.
    assert len(picks) == 2


def test_decide_launches_none_when_pool_full():
    # Arrange
    queued = _jobs(5)
    # Act
    picks = _pool.decide_launches(queued, active=4, max_concurrent=4)
    # Assert
    assert picks == []


def test_decide_launches_is_fifo():
    # Arrange
    queued = _jobs(5)
    # Act
    picks = _pool.decide_launches(queued, active=0, max_concurrent=2)
    # Assert — oldest two.
    assert [p.run_id for p in picks] == [1000, 1001]


def test_decide_launches_capped_by_queue_length():
    # Arrange — only 1 queued though 4 slots free.
    queued = _jobs(1)
    # Act
    picks = _pool.decide_launches(queued, active=0, max_concurrent=4)
    # Assert
    assert len(picks) == 1


# -- dispatch_once (orchestration) ------------------------------------------


def _gh_one_queued(args):
    # Fake gh: every repo reports exactly one queued run.
    return 0, '{"workflow_runs": [{"id": 7, "name": "pytest"}]}'


@pytest.fixture
def dry_cycle():
    launched = []
    res = _pool.dispatch_once(
        ["ywatanabe1989/a", "ywatanabe1989/b"],
        max_concurrent=4,
        count_active=lambda: 0,
        launcher=lambda job: launched.append(job) or True,
        gh_caller=_gh_one_queued,
        dry_run=True,
        out=io.StringIO(),
    )
    return {"res": res, "launched": launched}


def test_dry_run_launches_nothing(dry_cycle):
    # Arrange
    launched = dry_cycle["launched"]
    # Act
    # Assert — dry-run must not call the launcher.
    assert launched == []


def test_dry_run_still_reports_queued(dry_cycle):
    # Arrange
    res = dry_cycle["res"]
    # Act
    # Assert — 2 repos × 1 queued each.
    assert len(res.queued) == 2


@pytest.fixture
def live_cycle():
    launched = []
    res = _pool.dispatch_once(
        ["ywatanabe1989/a", "ywatanabe1989/b", "ywatanabe1989/c"],
        max_concurrent=2,
        count_active=lambda: 0,
        launcher=lambda job: launched.append(job) or True,
        gh_caller=_gh_one_queued,
        dry_run=False,
        out=io.StringIO(),
    )
    return {"res": res, "launched": launched}


def test_live_launches_up_to_cap(live_cycle):
    # Arrange
    launched = live_cycle["launched"]
    # Act
    # Assert — 3 queued, cap 2 → 2 launched.
    assert len(launched) == 2


def test_live_records_launched_in_result(live_cycle):
    # Arrange
    res = live_cycle["res"]
    # Act
    # Assert
    assert len(res.launched) == 2


def test_launch_failure_does_not_crash_cycle():
    # Arrange — launcher raises for every job.
    def boom(job):
        raise RuntimeError("srun failed")

    # Act — must not propagate (cron-safe).
    res = _pool.dispatch_once(
        ["ywatanabe1989/a"],
        max_concurrent=4,
        count_active=lambda: 0,
        launcher=boom,
        gh_caller=_gh_one_queued,
        dry_run=False,
        out=io.StringIO(),
    )
    # Assert — nothing recorded as launched, but no exception.
    assert res.launched == []


def test_poll_error_skips_repo_gracefully():
    # Arrange — gh returns non-zero for the repo.
    res = _pool.dispatch_once(
        ["ywatanabe1989/a"],
        max_concurrent=4,
        count_active=lambda: 0,
        launcher=lambda job: True,
        gh_caller=lambda args: (1, ""),
        dry_run=False,
        out=io.StringIO(),
    )
    # Act
    # Assert — no queued found, nothing launched, no crash.
    assert res.queued == []
