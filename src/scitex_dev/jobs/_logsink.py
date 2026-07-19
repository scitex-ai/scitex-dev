#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The log sink a scheduled job owns: mkdir + rotate + redirect.

WHY THIS EXISTS
---------------
Historically every managed crontab line carried its own shell plumbing::

    */30 * * * * mkdir -p $(dirname $HOME/.scitex/dev/logs/x.log); \
        [ -f ... ] && [ "$(stat -c%s ...)" -gt 1048576 ] && mv ... ; \
        scitex-dev cron exec x >> $HOME/.scitex/dev/logs/x.log 2>&1 # ...

Three problems, all operator-reported (2026-07-19):

1. The plumbing belongs to the VERB, not to the crontab. A crontab line
   should carry a schedule and a command — nothing else.
2. It duplicates per job, so the 1-MiB rotation guard existed on some
   lines and not others (creds-rotate had it; ci-watch did not).
3. ``~`` is only expanded by an interactive shell in command position;
   cron's ``/bin/sh -c`` context and ``$(dirname ~/...)`` do NOT
   reliably expand it, so generated shell text must use ``$HOME``.

This module is the ONE place that behaviour lives. It is deliberately
package-generic (``package`` is an argument, not a constant) and takes
no ``JobSpec`` of either class, so it is callable unchanged from:

* ``scitex_dev._cli.cron`` — today's hardcoded registry, and
* ``scitex_dev.jobs`` — the federated entry-point ``JobSpec`` those 11
  jobs are being migrated onto (card
  ``dev-two-jobspec-classes-ssot-violation-20260719``).

PATHS
-----
Log paths resolve through :func:`scitex_dev.jobs._respawn.runtime_dir_for_package`,
so everything lands under the documented regenerable-state layer::

    ~/.scitex/<package>/runtime/logs/<slug>.log

never ``~/.scitex/<package>/logs/``. ``runtime/`` is redirectable off
GPFS for inode safety, and job logs are exactly the high-cardinality
regenerable writes that layer exists for.

FAIL LOUD
---------
:func:`open_log_sink` and :func:`redirect_to_log` RAISE
:class:`LogSinkError` when the directory cannot be created or the log
cannot be opened. They never fall back to unlogged execution: a cron job
whose logging silently stopped is indistinguishable from one that ran
fine, which is the exact failure class this module was written to kill.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import IO, Iterator

from ._respawn import runtime_dir_for_package

#: Size at which a job log is rotated to ``<log>.1`` before the job runs.
#: 1 MiB — inherited from the ad-hoc ``creds-rotate`` crontab line this
#: module subsumes, so the federated behaviour matches what the host had.
LOG_ROTATE_BYTES = 1_048_576


class LogSinkError(RuntimeError):
    """Raised when the log dir/file cannot be prepared. Never swallowed."""


def log_dir(package: str, *, home: Path | None = None) -> Path:
    """Return ``~/.scitex/<package>/runtime/logs`` (pure; no mkdir)."""
    return runtime_dir_for_package(package, home=home) / "logs"


def log_path(package: str, slug: str, *, home: Path | None = None) -> Path:
    """Return the log path for ``slug`` under ``package``'s runtime logs.

    Pure path arithmetic — nothing is created. ``slug`` is the job's log
    basename WITHOUT the ``.log`` suffix (e.g. ``"cron-ci-watch"``).
    """
    if not slug or "/" in slug or "\\" in slug:
        raise ValueError(f"invalid log slug: {slug!r}")
    return log_dir(package, home=home) / f"{slug}.log"


def rotate_if_large(log: Path, *, max_bytes: int = LOG_ROTATE_BYTES) -> bool:
    """Move ``log`` aside to ``<log>.1`` when it exceeds ``max_bytes``.

    Returns ``True`` when a rotation happened. A missing log is not an
    error (nothing to rotate). Replaces the inline shell guard
    ``[ -f X ] && [ "$(stat -c%s X)" -gt N ] && mv X X.1``, and unlike
    that guard it now applies to EVERY job rather than the two lines
    that happened to carry it.
    """
    try:
        if not log.is_file() or log.stat().st_size <= max_bytes:
            return False
        log.replace(log.with_suffix(log.suffix + ".1"))
        return True
    except OSError as exc:
        raise LogSinkError(f"could not rotate log {log}: {exc}") from exc


def open_log_sink(
    log: Path,
    *,
    rotate: bool = True,
    max_bytes: int = LOG_ROTATE_BYTES,
) -> IO[str]:
    """Create the log dir, rotate if oversized, and open ``log`` append.

    This is the ``mkdir -p`` + ``>>`` that used to live in the crontab.
    FAILS LOUD (:class:`LogSinkError`) rather than degrading to unlogged
    execution — see the module docstring.
    """
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LogSinkError(
            f"could not create log directory {log.parent}: {exc}"
        ) from exc

    if rotate:
        rotate_if_large(log, max_bytes=max_bytes)

    try:
        return open(log, "a", encoding="utf-8", buffering=1)
    except OSError as exc:
        raise LogSinkError(f"could not open log {log}: {exc}") from exc


@contextlib.contextmanager
def redirect_to_log(
    log: Path,
    *,
    rotate: bool = True,
    max_bytes: int = LOG_ROTATE_BYTES,
) -> Iterator[Path]:
    """Redirect this process's stdout+stderr into ``log`` for the block.

    The ``>> <log> 2>&1`` that used to live in the crontab. Redirection
    is done at the FILE-DESCRIPTOR level (``os.dup2`` on fds 1 and 2),
    not merely by rebinding ``sys.stdout``, because job bodies spawn
    child processes (``ssh``, ``rsync``, ``sac``, ``gh``) that inherit
    fds — a Python-level-only redirect would silently lose exactly the
    subprocess output an operator greps for.

    ``sys.stdout`` / ``sys.stderr`` are rebound to the sink as well. In
    production those already point at fds 1/2 so the rebinding is
    redundant — but under any harness that has replaced them with its own
    objects (pytest's capture, a supervisor that wraps the stream), the
    fd-level dup2 alone would miss Python-level writes. Doing both means
    "everything this job prints ends up in its log" holds unconditionally.

    Yields the resolved log path. The original fds and stream objects are
    always restored, including on exception.
    """
    sink = open_log_sink(log, rotate=rotate, max_bytes=max_bytes)
    saved_out, saved_err = None, None
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    try:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        saved_out = os.dup(1)
        saved_err = os.dup(2)
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        sys.stdout = sink
        sys.stderr = sink
        yield log
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        sys.stdout, sys.stderr = saved_stdout, saved_stderr
        if saved_out is not None:
            with contextlib.suppress(OSError):
                os.dup2(saved_out, 1)
                os.close(saved_out)
        if saved_err is not None:
            with contextlib.suppress(OSError):
                os.dup2(saved_err, 2)
                os.close(saved_err)
        with contextlib.suppress(Exception):
            sink.close()


__all__ = [
    "LOG_ROTATE_BYTES",
    "LogSinkError",
    "log_dir",
    "log_path",
    "open_log_sink",
    "redirect_to_log",
    "rotate_if_large",
]


# EOF
