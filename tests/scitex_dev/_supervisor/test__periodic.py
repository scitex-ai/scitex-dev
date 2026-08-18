#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The supervisor's own clock, and the log that proves it ran.

The interesting assertions here are about the RECORDS, not the
processes. A periodic job that fails loudly is already visible; the
failure this module exists to make impossible is a job that never
started, which looks exactly like a healthy quiet system unless
something wrote down that it was supposed to run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._supervisor._periodic import PeriodicRunner
from scitex_dev.jobs import JobSpec


def _job(name: str, **kw) -> JobSpec:
    base = dict(
        name=name,
        description="probe job",
        command="/bin/true",
        kind="cron",
        schedule="*/10 * * * *",
    )
    base.update(kw)
    return JobSpec(**base)


class _FakeProc:
    """A Popen stand-in whose exit is driven by the test, not by timing."""

    def __init__(self, argv, **kw):
        self.argv = argv
        self.kw = kw
        self.pid = 4242
        self._code = None

    def poll(self):
        return self._code

    def finish(self, code: int = 0) -> None:
        self._code = code


@pytest.fixture
def runner(tmp_path: Path):
    clock = {"t": 1000.0}
    spawned: list[_FakeProc] = []

    def factory(argv, **kw):
        proc = _FakeProc(argv, **kw)
        spawned.append(proc)
        return proc

    r = PeriodicRunner(
        log_path=tmp_path / "exec.jsonl",
        clock=lambda: clock["t"],
        popen_factory=factory,
        host="testhost",
    )
    return r, clock, spawned


class TestItStartsWhatIsDue:
    def test_a_never_run_job_starts_on_the_first_tick(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        # Act
        records = r.tick([_job("scitex-dev-probe")])
        # Assert
        assert [x["event"] for x in records] == ["started"]

    def test_a_job_that_just_ran_is_not_started_again(self, runner):
        # Arrange
        r, clock, _spawned = runner
        jobs = [_job("scitex-dev-probe")]
        r.tick(jobs)
        # Act
        clock["t"] += 60  # cadence is 600s
        records = r.tick(jobs)
        # Assert
        assert [x["event"] for x in records] == []

    def test_the_cadence_elapsing_makes_it_due_again(self, runner):
        # Arrange
        r, clock, spawned = runner
        jobs = [_job("scitex-dev-probe")]
        r.tick(jobs)
        spawned[0].finish(0)
        # Act
        clock["t"] += 601
        events = [x["event"] for x in r.tick(jobs)]
        # Assert
        assert events == ["finished", "started"]

    def test_a_service_job_is_never_started_here(self, runner):
        """Services are children with a restart policy, not one-shots."""
        # Arrange
        r, _clock, _spawned = runner
        svc = _job("scitex-dev-daemon", kind="service", schedule="")
        # Act
        records = r.tick([svc])
        # Assert
        assert records == []


class TestTheLogIsTheProduct:
    def test_a_job_that_cannot_be_scheduled_is_named(self, runner):
        """The one failure with no other witness.

        A job whose cadence cannot be determined never runs. Without a
        record, "it never ran" is indistinguishable from "it is not due
        yet" — forever.
        """
        # Arrange
        r, _clock, _spawned = runner
        broken = _job("scitex-dev-broken", schedule="0 9 * * 1-5")
        # Act
        records = r.tick([broken])
        # Assert
        assert [x["event"] for x in records] == ["unschedulable"]

    def test_an_unschedulable_job_is_reported_once_not_every_tick(self, runner):
        """Once, because a per-tick repeat buries the log it belongs in."""
        # Arrange
        r, clock, _spawned = runner
        jobs = [_job("scitex-dev-broken", schedule="0 9 * * 1-5")]
        r.tick(jobs)
        # Act
        clock["t"] += 5000
        records = r.tick(jobs)
        # Assert
        assert records == []

    def test_a_spawn_failure_still_leaves_a_record(self, tmp_path: Path):
        """A missing binary must not vanish into an absence."""
        # Arrange
        def explode(argv, **kw):
            raise FileNotFoundError(argv[0])

        r = PeriodicRunner(
            log_path=tmp_path / "exec.jsonl",
            clock=lambda: 1000.0,
            popen_factory=explode,
            host="testhost",
        )
        # Act
        records = r.tick([_job("scitex-dev-probe")])
        # Assert
        assert records[0]["event"] == "start_failed"

    def test_the_exit_code_is_recorded_on_completion(self, runner):
        # Arrange
        r, clock, spawned = runner
        r.tick([_job("scitex-dev-probe")])
        spawned[0].finish(3)
        # Act
        clock["t"] += 1
        finished = r.tick([_job("scitex-dev-probe")])[0]
        # Assert
        assert finished["exit_code"] == 3 and finished["ok"] is False

    def test_every_record_names_the_host(self, runner):
        """Cross-host ordering is unreadable if a line cannot say where."""
        # Arrange
        r, _clock, _spawned = runner
        # Act
        records = r.tick([_job("scitex-dev-probe")])
        # Assert
        assert all(x["host"] == "testhost" for x in records)

    def test_the_log_survives_as_one_line_per_event(self, runner, tmp_path):
        # Arrange
        r, clock, spawned = runner
        jobs = [_job("scitex-dev-probe")]
        r.tick(jobs)
        spawned[0].finish(0)
        clock["t"] += 601
        r.tick(jobs)
        # Act
        lines = (tmp_path / "exec.jsonl").read_text().strip().splitlines()
        # Assert
        assert len(lines) == 3


class TestTheStagger:
    def test_dot_separated_names_get_different_offsets(self, runner):
        """The delta-T that stops every job firing in the same instant.

        DOT-separated, because that is the only form `package_of` can
        read. See the sibling test for why that matters more than it
        looks.
        """
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-cards.snapshot"), _job("scitex-dev.report-drift")]
        # Act
        offsets = {
            x["job"]: x["offset_sec"] for x in r.tick(jobs) if x["event"] == "started"
        }
        # Assert
        assert offsets["scitex-cards.snapshot"] != offsets["scitex-dev.report-drift"]

    def test_hyphenated_names_all_collapse_to_one_offset(self, runner):
        """MEASURED ON THE LIVE FLEET, and it makes the stagger inert.

        `package_of` splits on ".", so it reads `<package>.<verb>-<noun>`
        and nothing else. On scitex-compute-04, 33 of 34 discovered jobs
        have NO DOT — 21 are hyphenated (`scitex-dev-drift-report`) and
        13 are bare (`branch-gc`) — so every one of them answers package
        "" and receives offset 0. Exactly one job in the fleet
        (`sac.accounts-refresh`) is staggered at all.

        HYPHEN-SPLITTING CANNOT FIX THIS, which is the part worth
        keeping: package names contain hyphens themselves, so
        `scitex-agent-container-accounts-keepalive` cannot be split into
        package and verb without already knowing the package list. The
        dot is not decoration — it is the only unambiguous boundary.

        Pinned as a FAILING WITNESS for the naming sweep rather than
        left as an argument, and because the degradation is silent:
        offset 0 is a perfectly valid-looking answer.
        """
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-cards-snapshot"), _job("branch-gc")]
        # Act
        offsets = {
            x["job"]: x["offset_sec"] for x in r.tick(jobs) if x["event"] == "started"
        }
        # Assert
        assert offsets == {"scitex-cards-snapshot": 0.0, "branch-gc": 0.0}

    def test_a_bare_name_cannot_be_staggered(self, runner):
        """MEASURED ON THE LIVE FLEET, and the reason naming is a blocker.

        `package_of` derives the package from the name prefix. On
        scitex-compute-04, 13 of 34 discovered jobs carry NO package
        prefix (`branch-gc`, `ci-watch`, `cred-distribute`, ...), so they
        all resolve to the same empty package and receive offset 0 —
        every one of them firing in the same instant, which is the exact
        pile-up the stagger exists to remove.

        It degrades SILENTLY: offset 0 is a perfectly valid-looking
        answer. This test pins the behaviour so the naming sweep has a
        failing witness rather than an argument.
        """
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("branch-gc"), _job("ci-watch")]
        # Act
        offsets = {
            x["job"]: x["offset_sec"] for x in r.tick(jobs) if x["event"] == "started"
        }
        # Assert
        assert offsets == {"branch-gc": 0.0, "ci-watch": 0.0}


# EOF
