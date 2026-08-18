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
            done.append(
                self.record(
                    "finished",
                    job=name,
                    exit_code=code,
                    ok=(code == 0),
                    duration_sec=(
                        None if started is None else self._clock() - started
                    ),
                )
            )
        return done

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

        try:
            proc = self._popen(
                argv,
                cwd=job.working_directory or None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
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
