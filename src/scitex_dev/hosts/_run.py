#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The one subprocess seam every connectivity check runs through.

:func:`run_command` is the default; every checker takes a ``runner=``
parameter with this signature. That is an INJECTED COLLABORATOR, not a mock
seam: a test passes a runner that executes REAL local processes (``sh -c
'exit 0'``, a real ``ssh -G -F <tmp>``), so what the test exercises is the
same argv-building, exit-code reading and output parsing the fleet runs. The
only thing the seam replaces is WHICH machine answers.

WHY `timed_out` IS A FIELD AND NOT AN EXIT CODE
------------------------------------------------
"Did not answer within N seconds" and "answered, refusing" are different
facts that lead to different actions, and a caller that folds both into
``returncode != 0`` reports the fleet as broken when it is merely slow.
:class:`CommandResult` keeps them apart so a probe result can say which
happened.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

__all__ = ["CommandResult", "Runner", "run_command", "ssh_base_argv"]

#: ssh's own reserved exit status: the connection itself failed (unreachable,
#: auth refused, host key mismatch). A remote command that RAN and exited
#: non-zero returns its own status instead, so this value distinguishes "could
#: not get there" from "got there, the command failed" — a distinction the
#: matrix report would otherwise lose.
SSH_TRANSPORT_FAILURE = 255


@dataclass(frozen=True)
class CommandResult:
    """Outcome of one command. Never raises; the caller decides severity."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def transport_failed(self) -> bool:
        """True when ssh could not establish the connection at all."""
        return self.returncode == SSH_TRANSPORT_FAILURE

    def first_error_line(self) -> str:
        """The most informative single line for a report.

        Prefers stderr (where ssh puts its diagnosis), falls back to stdout,
        and says so explicitly when both are empty — an empty string rendered
        into a report reads as "no problem", which is exactly wrong for a
        command that failed silently.
        """
        if self.timed_out:
            return "timed out"
        for stream in (self.stderr, self.stdout):
            for line in stream.splitlines():
                if line.strip():
                    return line.strip()
        return f"exit {self.returncode}, no output"


#: What every checker's ``runner=`` parameter accepts:
#: ``(argv: Sequence[str], *, timeout: float) -> CommandResult``. Spelled
#: with ``...`` because the keyword-only ``timeout`` has no ``Callable``
#: spelling short of a Protocol, and a wrong-but-precise signature would be
#: worse than an honest loose one.
Runner = Callable[..., CommandResult]


def run_command(argv: Sequence[str], *, timeout: float = 10.0) -> CommandResult:
    """Run ``argv`` and capture it. Never raises for a failing command.

    ``FileNotFoundError`` (the binary is not installed — ``ip`` and ``arp``
    are genuinely absent inside the agent containers) is turned into a
    result, not an exception, so a missing tool degrades one SIGNAL to
    unavailable instead of aborting the whole check. A check that dies
    because one of its three probes is missing cannot report "insufficient
    evidence", which is the answer it owes the caller.
    """
    args = [str(a) for a in argv]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(tuple(args), 124, "", "", timed_out=True)
    except FileNotFoundError as exc:
        return CommandResult(tuple(args), 127, "", str(exc))
    except OSError as exc:  # pragma: no cover - platform dependent
        return CommandResult(tuple(args), 126, "", str(exc))
    return CommandResult(tuple(args), proc.returncode, proc.stdout, proc.stderr)


def ssh_base_argv(*, connect_timeout: int = 5) -> list[str]:
    """The non-interactive ssh prefix every probe shares.

    ``BatchMode=yes`` is the important one: without it a probe against an
    unreachable host BLOCKS on a password prompt, and a matrix sweep of
    N*(N-1) pairs turns into an interactive session nobody is watching.
    ``StrictHostKeyChecking=accept-new`` avoids the same trap for a host
    whose key is not yet known, while still refusing a key that CHANGED —
    a changed key is the one case that must stop and be looked at.
    """
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


# EOF
