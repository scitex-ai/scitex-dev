#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run periodic (timer/cron-kind) jobs on the supervisor's OWN clock.

WHY THIS EXISTS
---------------
Until now the supervisor ran ``kind="service"`` jobs only, and every
timer/cron-kind job was LOWERED TO A USER-CRONTAB LINE. That is the
arrangement the operator ruled out (2026-08-18): 20+ crontab lines per
host is unreadable and does not scale — 「20行とか書かれていると
ぐちゃぐちゃになる。スケールもしなくなる」 — and the replacement is a
dedicated service that owns the clock, not a bigger crontab.

So a periodic job stops being a line somebody else runs and becomes a
thing THIS process decides to start, records, and can be asked about.

WHAT MAKES IT DIFFERENT FROM A CHILD
------------------------------------
A service child is long-lived and restarted when it dies. A periodic run
is a ONE-SHOT: it is expected to exit, and exiting is success rather
than a fault. Conflating the two is how a cron job acquires a restart
policy and runs continuously, so they are separate types on purpose.

THE EXECUTION LOG IS THE PRODUCT, NOT A SIDE EFFECT
---------------------------------------------------
Operator, same ruling: a periodic job must record WHAT SHOULD RUN, WHEN
IT RAN, and WHAT HAPPENED. All three, because the interesting failure is
not a job that ran and failed — that one is visible — it is a job that
was never started at all, which is indistinguishable from a healthy
quiet system unless something wrote down that it was *supposed* to run.

Hence :meth:`PeriodicRunner.tick` emits a record for every job it
starts, for every job it finishes, AND for every job it could not
schedule. The last of those is the one that has no other witness.
"""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from ..jobs import JobSpec
from ..jobs._systemd import resolve_execstart
from ._schedule import due_jobs, offsets_for, package_of, unschedulable

#: One line per event, newline-delimited JSON. Chosen over a single
#: growing document so a crash mid-write costs the last line rather than
#: the file, and so `tail -f` is a usable live view.
DEFAULT_LOG_NAME = "periodic-executions.jsonl"


def default_execution_log() -> Path:
    """Where the execution log lives when the caller does not say."""
    base = os.environ.get("SCITEX_DEV_RUNTIME_DIR")
    root = Path(base) if base else Path.home() / ".scitex" / "dev" / "runtime"
    return root / DEFAULT_LOG_NAME


def _build_argv(job: JobSpec) -> list[str]:
    """Absolutised argv for ``job.command`` — same resolution as children.

    Shares ``resolve_execstart`` with :mod:`._child` deliberately: a
    periodic job and a service job that name the same command must
    resolve to the same binary, or "works as a service, fails as a
    timer" becomes a real and very confusing report.
    """
    return shlex.split(resolve_execstart(job.command, venv=job.venv))


#: Consecutive failures before a job is called unhealthy. Three rather
#: than one: a single failure is noise on jobs that touch the network,
#: and an alarm that fires on noise is one people learn to ignore.
UNHEALTHY_AFTER = 3

#: How much of a failed job's stderr to keep in its record. Enough for a
#: traceback's last frames or an alarm block; small enough that a job
#: failing every 5 minutes cannot bloat the log. The TAIL, not the head:
#: the reason a process died is at the end of what it printed.
STDERR_TAIL_BYTES = 4000


def is_unhealthy(outcome: Mapping[str, Any]) -> bool:
    """Does this job's tally warrant an alarm?

    Two predicates, not one, because they catch different failures:

    * ``consecutive_failures >= UNHEALTHY_AFTER`` — a job that WAS
      working and has stopped.
    * never succeeded at all — a job that has been broken since it was
      first seen. Measured 2026-08-23 on compute-04: six jobs had
      100% failure rates spanning three to five days (ci-watch 615/0,
      scitex-hpc-ci-supervisor-watch 885/0, ...). A consecutive-failure
      rule alone would have flagged them, but stating "never succeeded"
      separately is what makes the report actionable — it distinguishes
      a regression from something that never worked, and those have
      different owners.
    """
    if outcome.get("ok_count", 0) == 0:
        return outcome.get("fail_count", 0) >= UNHEALTHY_AFTER
    return outcome.get("consecutive_failures", 0) >= UNHEALTHY_AFTER


class PeriodicRunner:
    """Owns the clock for timer/cron-kind jobs.

    Deliberately holds NO reference to the supervisor: it is handed the
    job list on each tick. That keeps it testable against a plain list
    and means a scheduling bug cannot reach into child management.
    """

    def __init__(
        self,
        *,
        log_path: Optional[Path] = None,
        clock: Callable[[], float] = time.time,
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        host: Optional[str] = None,
    ) -> None:
        self._log_path = log_path or default_execution_log()
        self._clock = clock
        self._popen = popen_factory
        self._host = host or socket.gethostname()
        self._last_runs: dict[str, float] = {}
        self._running: dict[str, subprocess.Popen] = {}
        self._started_at: dict[str, float] = {}
        self._reported_unschedulable: set[str] = set()
        #: Per-job outcome tally, keyed by job name. The execution log
        #: already holds every record; this is the ROLLUP, because the
        #: log answers "what happened" only to someone who reads 131k
        #: lines. Measured 2026-08-23: six jobs had a 100% failure rate
        #: for up to five days and nothing reported it.
        self._outcomes: dict[str, dict[str, Any]] = {}
        #: Jobs already announced as unhealthy, so the alarm fires on the
        #: TRANSITION rather than on every reap.
        self._reported_unhealthy: set[str] = set()
        #: Open stderr capture files for in-flight one-shots, by job name.
        #: value is (path, handle) — the handle is ours to close on reap.
        self._stderr_capture: dict[str, tuple[Path, Any]] = {}

    # -------------------------------------------------------------- #

    @property
    def last_runs(self) -> Mapping[str, float]:
        """When each job last STARTED, by name. Empty on a cold start."""
        return dict(self._last_runs)

    @property
    def running(self) -> Mapping[str, subprocess.Popen]:
        """Currently in-flight one-shots, by job name."""
        return dict(self._running)

    # -------------------------------------------------------------- #

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        """Append one execution record and return it.

        Returns the record so callers (and tests) can assert on exactly
        what was written rather than re-reading and re-parsing the file.
        """
        rec: dict[str, Any] = {
            "ts": self._clock(),
            "host": self._host,
            "event": event,
            **fields,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    # -------------------------------------------------------------- #

    def reap(self) -> list[dict[str, Any]]:
        """Record completion for every one-shot that has exited.

        A one-shot that exits is DONE, not dead — no restart policy is
        consulted. The exit status is recorded either way, because
        "ran and failed" and "ran and succeeded" are both answers and
        only the absence of a record is a mystery.
        """
        done: list[dict[str, Any]] = []
        for name in list(self._running):
            proc = self._running[name]
            code = proc.poll()
            if code is None:
                continue
            del self._running[name]
            started = self._started_at.pop(name, None)
            tail = self._take_stderr_tail(name)
            fields: dict[str, Any] = {
                "job": name,
                "exit_code": code,
                "ok": (code == 0),
                "duration_sec": (
                    None if started is None else self._clock() - started
                ),
            }
            # Only on failure: a successful job's chatter is noise, and
            # this log is read by someone asking "what went wrong".
            if code != 0 and tail:
                fields["stderr_tail"] = tail
            done.append(self.record("finished", **fields))
            done.extend(self._tally(name, code))
        return done

    def _tally(self, name: str, code: int) -> list[dict[str, Any]]:
        """Fold one exit into the job's rollup; announce a new failure.

        Returns any alarm record written, so ``reap``'s return value stays
        the complete list of what this cycle recorded.
        """
        out = self._outcomes.setdefault(
            name,
            {
                "ok_count": 0,
                "fail_count": 0,
                "consecutive_failures": 0,
                "last_exit_code": None,
                "last_ok_at": None,
                "last_finished_at": None,
            },
        )
        out["last_exit_code"] = code
        out["last_finished_at"] = self._clock()
        if code == 0:
            out["ok_count"] += 1
            out["consecutive_failures"] = 0
            out["last_ok_at"] = out["last_finished_at"]
            # Recovery re-arms the alarm: the NEXT failure run is news
            # again, otherwise a flapping job is announced once and then
            # never again.
            self._reported_unhealthy.discard(name)
            return []
        out["fail_count"] += 1
        out["consecutive_failures"] += 1
        if not is_unhealthy(out) or name in self._reported_unhealthy:
            return []
        self._reported_unhealthy.add(name)
        return [
            self.record(
                "job_unhealthy",
                job=name,
                consecutive_failures=out["consecutive_failures"],
                ok_count=out["ok_count"],
                fail_count=out["fail_count"],
                never_succeeded=(out["ok_count"] == 0),
                last_exit_code=code,
            )
        ]

    def health(self) -> list[dict[str, Any]]:
        """Per-job outcome rollup, newest tallies, sorted by name.

        Written into ``state.json`` so a reader can answer "is anything
        failing?" without parsing the execution log.
        """
        return [
            {"job": name, "unhealthy": is_unhealthy(out), **out}
            for name, out in sorted(self._outcomes.items())
        ]

    # -------------------------------------------------------------- #

    def tick(self, jobs: Sequence[JobSpec]) -> list[dict[str, Any]]:
        """One scheduling cycle. Returns every record written.

        Order matters: reap FIRST so a job that finished this instant is
        eligible again, then report anything unschedulable, then start
        what is due.
        """
        records = self.reap()
        records.extend(self._report_unschedulable(jobs))

        periodic = [j for j in jobs if j.kind != "service"]
        now = self._clock()
        offsets = offsets_for(package_of(j.name) for j in periodic)
        for job in due_jobs(
            periodic, now=now, last_runs=self._last_runs, offsets=offsets
        ):
            records.append(self._start(job, offset=offsets.get(package_of(job.name), 0.0)))
        return records

    # -------------------------------------------------------------- #

    def _report_unschedulable(
        self, jobs: Sequence[JobSpec]
    ) -> list[dict[str, Any]]:
        """Name jobs that CANNOT be placed — once each, not every tick.

        Once-each because a per-tick repeat would bury the log; but at
        least once, because a job nobody can schedule is otherwise
        indistinguishable from a job that simply is not due yet, forever.
        """
        out: list[dict[str, Any]] = []
        for name, why in unschedulable(jobs):
            if name in self._reported_unschedulable:
                continue
            self._reported_unschedulable.add(name)
            out.append(self.record("unschedulable", job=name, reason=why))
        return out

    def _open_stderr_capture(self, name: str) -> tuple[Optional[Path], Any]:
        """Open a throwaway file to catch this run's stderr.

        Returns (path, handle), or (None, None) if the file cannot be
        opened — in which case the caller falls back to DEVNULL. Losing
        the diagnostic is bad; refusing to run the job because we could
        not open a scratch file would be worse.
        """
        try:
            directory = self._log_path.parent / "stderr"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{name}.stderr"
            handle = path.open("wb")
        except OSError:
            return None, None
        self._stderr_capture[name] = (path, handle)
        return path, handle

    def _discard_stderr_capture(self, name: str) -> None:
        """Close and remove a capture whose child never started."""
        entry = self._stderr_capture.pop(name, None)
        if entry is None:
            return
        path, handle = entry
        try:
            handle.close()
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass

    def _take_stderr_tail(self, name: str) -> Optional[str]:
        """Close this job's capture and return the tail of what it wrote.

        Returns None when nothing was captured, so a quiet success adds no
        key at all rather than an empty string that reads like evidence of
        having looked.
        """
        entry = self._stderr_capture.pop(name, None)
        if entry is None:
            return None
        path, handle = entry
        try:
            handle.close()
        except OSError:
            pass
        try:
            raw = path.read_bytes()[-STDERR_TAIL_BYTES:]
        except OSError:
            raw = b""
        try:
            path.unlink()
        except OSError:
            pass
        if not raw.strip():
            return None
        return raw.decode("utf-8", "replace")

    def _start(self, job: JobSpec, *, offset: float) -> dict[str, Any]:
        """Launch one one-shot and record the attempt.

        The record is written whether or not the spawn succeeds. A job
        whose binary is missing must leave a trace — otherwise the only
        evidence is an absence, and absence is what this log exists to
        make impossible.
        """
        if job.name in self._running:
            return self.record("skipped_still_running", job=job.name)

        started = self._clock()
        try:
            argv = _build_argv(job)
        except Exception as exc:  # resolution failed — still a record
            self._last_runs[job.name] = started
            return self.record(
                "start_failed",
                job=job.name,
                error=f"{type(exc).__name__}: {exc}",
                phase="resolve",
            )

        # stderr was DEVNULL here until 2026-08-23, and that is why a job
        # could alarm 885 times without anyone hearing it: scitex-hpc's
        # ci-runners watch printed "CRITICAL supervisor-unregistered" plus
        # the exact operator command to stderr on every run since 08-20,
        # and every byte went to /dev/null. Jobs that write their own log
        # survived that; jobs that just print did not.
        #
        # A FILE, not PIPE: this loop polls without reading, so a PIPE
        # would fill its buffer and wedge the child — turning a diagnostic
        # into an outage.
        stderr_path, stderr_handle = self._open_stderr_capture(job.name)
        try:
            proc = self._popen(
                argv,
                cwd=job.working_directory or None,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle or subprocess.DEVNULL,
            )
        except Exception as exc:
            self._discard_stderr_capture(job.name)
            self._last_runs[job.name] = started
            return self.record(
                "start_failed",
                job=job.name,
                argv=argv,
                error=f"{type(exc).__name__}: {exc}",
                phase="spawn",
            )

        self._running[job.name] = proc
        self._started_at[job.name] = started
        self._last_runs[job.name] = started
        return self.record(
            "started",
            job=job.name,
            argv=argv,
            package=package_of(job.name),
            offset_sec=offset,
            pid=getattr(proc, "pid", None),
        )


__all__ = [
    "DEFAULT_LOG_NAME",
    "PeriodicRunner",
    "default_execution_log",
]

# EOF
