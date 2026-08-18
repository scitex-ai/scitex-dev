#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which auditor measured this tree — asked of the binary, not assumed.

Split into its own module because the question it answers is separable
from running the audit: "DID THE CODE CHANGE OR DID THE RULER CHANGE?"
Any caller that reports on an audit result wants it, not only the
pytest gate.

Requested independently by three packages on 2026-08-18 — scitex-app
("the useful payload was not 'you are red', it was the AUDITOR VERSION
PAIR"), scitex-ui, and sac, who supplied the incident that names the
mechanism: a package declaring a FLOOR (`scitex-dev>=0.49.2`) has CI
resolve the newest at job time, so a rule corpus can move five minor
versions underneath a tree that did not change.
"""

from __future__ import annotations

import subprocess

def auditor_identity(
    launcher: str | list[str], *, timeout: float = 10.0
) -> str:
    """Which auditor answered — asked of THE BINARY, not of this process.

    THE QUESTION THIS EXISTS TO ANSWER, in sac's words (2026-08-18):
    "DID THE CODE CHANGE OR DID THE RULER CHANGE?" It is the first
    question any reader of a red gate has, it decides whether they go
    looking at their own diff or at PyPI, and until now the failure
    output could not answer it.

    sac's develop went red with no commit behind it. They spent real
    time proving their own five-line pyproject change was not the cause.
    It was not: they declare `scitex-dev>=0.49.2`, a FLOOR, CI resolves
    the newest at job time, and five minor releases of the rule corpus
    had arrived in between. Several codes in the failure were ones the
    older auditor cannot emit at all — 0.48.0 answers "not-auditable:
    unknown" where 0.53.0 introspects the CLI and finds §4b, §10w, §13.

    Reported independently by scitex-app ("the useful payload was not
    'you are red' — it was the AUDITOR VERSION PAIR") and hit by
    scitex-ui the same day. Three sources, one missing line.

    ASKED OF THE BINARY ON PURPOSE. `importlib.metadata.version()` in
    THIS process answers for the interpreter running the tests, which is
    not necessarily the `scitex-dev` on PATH that actually graded the
    tree — that gap is its own tracked defect (audit-all resolves
    sub-auditors from PATH). Reporting the wrong one would be worse than
    reporting none, because it would look authoritative.

    FAILURE RETURNS AN EXPLICIT UNKNOWN, never a plausible default: a
    version string invented here would be indistinguishable from a
    measured one, and this line exists precisely to be trusted.
    """
    argv = [launcher] if isinstance(launcher, str) else list(launcher)
    shown = " ".join(argv)
    try:
        proc = subprocess.run(
            [*argv, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"UNKNOWN ({shown}) — could not ask: {type(exc).__name__}"
    reported = (proc.stdout or proc.stderr or "").strip().splitlines()
    if proc.returncode != 0 or not reported:
        return f"UNKNOWN ({shown}) — `--version` exited {proc.returncode}"
    return f"{reported[0].strip()} ({shown})"


__all__ = ["auditor_identity"]

# EOF
