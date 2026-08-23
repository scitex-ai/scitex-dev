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

from scitex_dev._supervisor._periodic import STDERR_TAIL_BYTES, PeriodicRunner
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


def _run_once(runner_tuple, jobs, code: int) -> list[str]:
    """Drive one full start -> exit -> reap cycle and return its events.

    The clock is advanced past the cadence so the reaping tick also
    re-starts the job, which is what the real loop does.
    """
    r, clock, spawned = runner_tuple
    r.tick(jobs)
    spawned[-1].finish(code)
    clock["t"] += 601
    return [x["event"] for x in r.tick(jobs)]


def _entry(runner_obj, name: str) -> dict:
    """The health rollup for one job, by name."""
    return next(x for x in runner_obj.health() if x["job"] == name)


class TestItAnnouncesJobsThatKeepFailing:
    """The execution log recorded every failure and nobody read it.

    Measured on compute-04 2026-08-23: six jobs at a 100% failure rate
    for up to five days, unreported. These tests pin the rollup that
    makes that condition visible.
    """

    def test_two_failures_are_not_yet_an_alarm(self, runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        # Act
        _run_once(runner, jobs, 1)
        events = _run_once(runner, jobs, 1)
        # Assert — the threshold is real, not decorative
        assert "job_unhealthy" not in events

    def test_the_third_consecutive_failure_raises_the_alarm(self, runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        _run_once(runner, jobs, 1)
        _run_once(runner, jobs, 1)
        # Act
        events = _run_once(runner, jobs, 1)
        # Assert
        assert "job_unhealthy" in events

    def test_the_alarm_fires_once_not_on_every_later_failure(self, runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        for _ in range(3):
            _run_once(runner, jobs, 1)
        # Act — three MORE failures after the alarm already fired
        later = []
        for _ in range(3):
            later += _run_once(runner, jobs, 1)
        # Assert — a repeat every cycle is how an alarm becomes wallpaper
        assert later.count("job_unhealthy") == 0

    def test_a_job_that_never_succeeded_has_no_successes(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-dev-probe")]
        for _ in range(3):
            _run_once(runner, jobs, 1)
        # Act
        entry = _entry(r, "scitex-dev-probe")
        # Assert — zero successes distinguishes "broken since birth"
        # from "regressed"; both are unhealthy, but different owners
        assert entry["ok_count"] == 0

    def test_a_job_that_never_succeeded_is_unhealthy(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-dev-probe")]
        for _ in range(3):
            _run_once(runner, jobs, 1)
        # Act
        entry = _entry(r, "scitex-dev-probe")
        # Assert
        assert entry["unhealthy"] is True

    def test_a_success_clears_the_streak_and_rearms_the_alarm(self, runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        for _ in range(3):
            _run_once(runner, jobs, 1)
        _run_once(runner, jobs, 0)
        # Act — it breaks again after having recovered
        again = []
        for _ in range(3):
            again += _run_once(runner, jobs, 1)
        # Assert — a flapping job must be announced each time it breaks
        assert again.count("job_unhealthy") == 1

    def test_health_is_empty_before_anything_has_finished(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        # Act
        report = r.health()
        # Assert
        assert report == []

    def test_health_counts_successes_and_failures_per_job(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-dev-probe")]
        for code in (0, 1, 0):
            _run_once(runner, jobs, code)
        # Act
        entry = _entry(r, "scitex-dev-probe")
        # Assert
        assert (entry["ok_count"], entry["fail_count"]) == (2, 1)

    def test_a_success_clears_the_consecutive_failure_count(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-dev-probe")]
        for code in (0, 1, 0):
            _run_once(runner, jobs, code)
        # Act
        entry = _entry(r, "scitex-dev-probe")
        # Assert
        assert entry["consecutive_failures"] == 0

    def test_a_job_that_recovered_is_not_unhealthy(self, runner):
        # Arrange
        r, _clock, _spawned = runner
        jobs = [_job("scitex-dev-probe")]
        for code in (0, 1, 0):
            _run_once(runner, jobs, code)
        # Act
        entry = _entry(r, "scitex-dev-probe")
        # Assert
        assert entry["unhealthy"] is False


class _StderrProc:
    """A Popen stand-in that actually writes to the stderr it is given.

    The plain _FakeProc never touches its stderr handle, so a capture test
    built on it would pass against a supervisor that still discarded the
    stream — it would assert nothing.
    """

    def __init__(self, argv, **kw):
        self.argv = argv
        self.pid = 4243
        self._code = None
        self._stderr = kw.get("stderr")

    def emit(self, text: str) -> None:
        self._stderr.write(text.encode("utf-8"))
        self._stderr.flush()

    def poll(self):
        return self._code

    def finish(self, code: int = 0) -> None:
        self._code = code


@pytest.fixture
def stderr_runner(tmp_path: Path):
    clock = {"t": 1000.0}
    spawned: list[_StderrProc] = []

    def factory(argv, **kw):
        proc = _StderrProc(argv, **kw)
        spawned.append(proc)
        return proc

    r = PeriodicRunner(
        log_path=tmp_path / "exec.jsonl",
        clock=lambda: clock["t"],
        popen_factory=factory,
        host="testhost",
    )
    return r, clock, spawned


def _run_emitting(runner_tuple, jobs, text: str, code: int) -> dict:
    """One cycle where the child writes ``text`` to stderr and exits."""
    r, clock, spawned = runner_tuple
    r.tick(jobs)
    spawned[-1].emit(text)
    spawned[-1].finish(code)
    clock["t"] += 601
    finished = [x for x in r.tick(jobs) if x["event"] == "finished"]
    return finished[0]


class TestItKeepsWhatAFailedJobPrinted:
    """stderr was DEVNULL, so a job could alarm 885 times unheard.

    scitex-hpc's ci-runners watch printed CRITICAL supervisor-unregistered
    plus the exact operator command on every run since 2026-08-20, and the
    supervisor discarded every byte.
    """

    def test_a_failed_job_keeps_its_stderr(self, stderr_runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        # Act
        rec = _run_emitting(stderr_runner, jobs, "CRITICAL supervisor-unregistered", 1)
        # Assert
        assert "CRITICAL supervisor-unregistered" in rec["stderr_tail"]

    def test_a_successful_job_records_no_stderr(self, stderr_runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        # Act
        rec = _run_emitting(stderr_runner, jobs, "chatty but fine", 0)
        # Assert — success chatter is noise in a log read for failures
        assert "stderr_tail" not in rec

    def test_a_silent_failure_adds_no_empty_key(self, stderr_runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        # Act
        rec = _run_emitting(stderr_runner, jobs, "   \n  ", 1)
        # Assert — an empty string would read as "we looked and found none"
        assert "stderr_tail" not in rec

    def test_the_tail_is_capped(self, stderr_runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        # Act
        rec = _run_emitting(stderr_runner, jobs, "x" * (STDERR_TAIL_BYTES * 3), 1)
        # Assert
        assert len(rec["stderr_tail"]) <= STDERR_TAIL_BYTES

    def test_the_tail_is_the_end_not_the_start(self, stderr_runner):
        # Arrange
        jobs = [_job("scitex-dev-probe")]
        noisy = ("filler\n" * 2000) + "THE ACTUAL ERROR"
        # Act
        rec = _run_emitting(stderr_runner, jobs, noisy, 1)
        # Assert — why a process died is at the END of what it printed
        assert "THE ACTUAL ERROR" in rec["stderr_tail"]
