#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: scitex_dev/trace_env/trace.py

"""MODE 2 — dynamic trace: pinpoint the exec stage that injects a var.

Runs a command under ``strace -f -e trace=execve -s <large> -v``,
parses every ``execve()`` call's environment array, and reports — per
traced variable — the FIRST exec stage (spawned binary + argv) whose
child environment contains it. This localizes the exact process layer
that injects a stale var in a multi-stage launch (shell → tmux →
apptainer → claude).

If ``strace`` is unavailable the engine returns a clear, actionable
:class:`TraceEnvResult` (``error`` set) rather than crashing.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import (
    ExecStageHit,
    TraceEnvResult,
    VarReport,
    assignment_regex,
    is_secret_shaped,
    redact,
)

_STRACE_MISSING = (
    "strace is required for --trace mode but was not found on PATH.\n"
    "Install it (e.g. `apt-get install strace`) or use the static scan "
    "(drop --trace) to find assignment sites instead."
)


def _read_string(s: str, i: int) -> tuple[str | None, int]:
    """Read a C-style double-quoted string starting at/after ``s[i]``."""
    while i < len(s) and s[i] in " \t":
        i += 1
    if i >= len(s) or s[i] != '"':
        return None, i
    i += 1
    out: list[str] = []
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append(s[i : i + 2])
            i += 2
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    return None, i


def _read_array(s: str, i: int) -> tuple[list[str] | None, int]:
    """Read a ``[...]`` array of strings starting at/after ``s[i]``.

    Leading whitespace and the comma separating this array from the
    preceding argument are skipped.
    """
    while i < len(s) and s[i] in " \t,":
        i += 1
    if i >= len(s) or s[i] != "[":
        return None, i
    i += 1
    items: list[str] = []
    while i < len(s):
        while i < len(s) and s[i] in " \t,":
            i += 1
        if i < len(s) and s[i] == "]":
            return items, i + 1
        if s.startswith("...", i):  # truncation marker
            i += 3
            continue
        if i < len(s) and s[i] == '"':
            val, i = _read_string(s, i)
            if val is None:
                return items, i
            items.append(val)
        else:
            i += 1
    return items, i


def _parse_execve(line: str) -> tuple[str, list[str], list[str]] | None:
    """Extract ``(binary, argv, envp)`` from one strace execve line.

    Skips ``<unfinished ...>`` / ``resumed`` fragments and any line
    without a complete envp array.
    """
    start = line.find("execve(")
    if start < 0:
        return None
    i = start + len("execve(")
    binary, i = _read_string(line, i)
    if binary is None:
        return None
    argv, i = _read_array(line, i)
    envp, i = _read_array(line, i)
    if envp is None:
        return None
    return binary, argv or [], envp


def _first_hit(
    name: str, stages: list[tuple[str, list[str], list[str]]]
) -> ExecStageHit | None:
    """First exec stage whose envp assigns ``name`` (word-boundary)."""
    rx = assignment_regex(name)
    for idx, (binary, argv, envp) in enumerate(stages):
        for entry in envp:
            if rx.search(entry):
                _, _, raw_val = entry.partition("=")
                return ExecStageHit(
                    var=name,
                    stage_index=idx,
                    binary=binary,
                    argv=argv,
                    value=redact(name, raw_val),
                )
    return None


def trace_env_vars(
    names: list[str],
    command: list[str],
    strace_string_size: int = 65_536,
    timeout: float | None = 300.0,
) -> TraceEnvResult:
    """Run ``command`` under strace; report first exec stage per var.

    Returns a :class:`TraceEnvResult` in ``mode="trace"``. When strace
    is missing, ``error`` carries an actionable message and no command
    is run.
    """
    if not shutil.which("strace"):
        return TraceEnvResult(
            variables=[
                VarReport(n, False, None, is_secret_shaped(n)) for n in names
            ],
            mode="trace",
            error=_STRACE_MISSING,
        )
    if not command:
        return TraceEnvResult(
            variables=[
                VarReport(n, False, None, is_secret_shaped(n)) for n in names
            ],
            mode="trace",
            error="no command given to --trace (expected: ... --trace -- CMD ARGS)",
        )

    with tempfile.NamedTemporaryFile(
        "r", suffix=".strace", delete=False
    ) as tf:
        out_path = Path(tf.name)
    try:
        argv = [
            "strace",
            "-f",
            "-e",
            "trace=execve",
            "-s",
            str(strace_string_size),
            "-v",
            "-o",
            str(out_path),
            *command,
        ]
        try:
            subprocess.run(argv, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            pass  # partial trace is still useful
        raw = out_path.read_text(encoding="utf-8", errors="replace")
    finally:
        try:
            out_path.unlink()
        except OSError:
            pass

    stages: list[tuple[str, list[str], list[str]]] = []
    for line in raw.splitlines():
        parsed = _parse_execve(line)
        if parsed is not None:
            stages.append(parsed)

    hits: list[ExecStageHit] = []
    variables: list[VarReport] = []
    for name in names:
        hit = _first_hit(name, stages)
        if hit is not None:
            hits.append(hit)
        variables.append(
            VarReport(
                name=name,
                currently_set=hit is not None,
                current_value=hit.value if hit else None,
                secret_shaped=is_secret_shaped(name),
            )
        )

    return TraceEnvResult(
        variables=variables,
        mode="trace",
        exec_stages=len(stages),
        trace_hits=hits,
    )


# EOF
