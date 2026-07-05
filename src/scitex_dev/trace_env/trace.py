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

import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
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


def _redact_raw_log(raw: str) -> str:
    """Redact secret-shaped ``NAME=VALUE`` strings before a raw strace log
    is left on disk at a persistent, discoverable path.

    ``--trace`` logs the FULL environment (and argv) of every exec stage,
    not just the one traced variable — the structured report already
    redacts that single variable's reported value, but the raw file
    behind it previously kept every other var in plaintext. Now that the
    log survives the run at a well-known path instead of vanishing with
    the old tempfile, that plaintext is a real exposure. Walks every
    double-quoted string token in the raw text (this is how strace
    renders both argv and envp entries) and redacts the value half
    whenever the name half is secret-shaped, reusing the exact heuristic
    already applied to the traced variable's own reported value — this
    also catches an inline ``NAME=VALUE`` assignment token in argv (e.g.
    ``env API_TOKEN=x cmd``), though NOT a hyphenated CLI flag like
    ``--api-token=x`` (the shared ``is_secret_shaped`` heuristic matches
    ``_``-delimited name components, not ``-``-delimited ones).
    """
    out: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        if raw[i] != '"':
            out.append(raw[i])
            i += 1
            continue
        start = i
        token, j = _read_string(raw, i)
        if token is None:
            out.append(raw[i])
            i += 1
            continue
        name, sep, value = token.partition("=")
        if sep and is_secret_shaped(name):
            out.append(f'"{name}={redact(name, value)}"')
        else:
            out.append(raw[start:j])
        i = j
    return "".join(out)


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


def _unset_report(names: list[str]) -> list[VarReport]:
    """A ``VarReport`` list with every var marked unset (error paths)."""
    return [VarReport(n, False, None, is_secret_shaped(n)) for n in names]


def _permission_hint(stderr_text: str) -> str:
    """Surface strace's own diagnostic line for a no-data trace, if any."""
    low = stderr_text.lower()
    if any(k in low for k in ("ptrace", "not permitted", "seccomp", "operation not")):
        last = stderr_text.strip().splitlines()[-1] if stderr_text.strip() else ""
        return f" strace said: {last}" if last else ""
    return ""


def _result_from_trace(
    names: list[str], raw: str, stderr_text: str = ""
) -> TraceEnvResult:
    """Classify parsed strace output into a :class:`TraceEnvResult`.

    Pure (no subprocess) so the empty/failed-strace path is unit-testable.
    A trace that yields ZERO execve records is reported DISTINCTLY as
    *inconclusive* — a normal trace always records at least the initial
    execve of the command itself, so zero records means strace could not
    trace at all (typically missing ``CAP_SYS_PTRACE`` / ptrace denied in
    a container). That is NOT the same as "the var never appeared".
    """
    stages: list[tuple[str, list[str], list[str]]] = []
    for line in raw.splitlines():
        parsed = _parse_execve(line)
        if parsed is not None:
            stages.append(parsed)

    if not stages:
        return TraceEnvResult(
            variables=_unset_report(names),
            mode="trace",
            exec_stages=0,
            error=(
                "strace produced no execve data — trace inconclusive "
                "(missing CAP_SYS_PTRACE? ptrace not permitted in this "
                "container/sandbox?). This is NOT a 'var not found' result."
                + _permission_hint(stderr_text)
            ),
        )

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


def _sanitize_command(command: list[str]) -> str:
    """Turn a command argv into a single hyphen-separated log-filename slug.

    A single delimiter (``-``) keeps the name scannable by eye and
    globbable by tooling — no mix of ``_`` (arg join) and ``-``
    (char substitution) that made earlier names read as a word-mash.
    Bare ``--`` flags are dropped as noise; everything else is kept.
    """
    words = [w for w in command if w not in ("--",)]
    joined = re.sub(r"[^A-Za-z0-9.]+", "-", "-".join(words))
    return joined.strip("-")[:80] or "cmd"


def _new_log_path(command: list[str]) -> Path:
    """Allocate a discoverable, timestamped strace log at a FIXED location.

    Always ``~/.scitex/dev/runtime/trace-env-vars/`` (user scope, never
    project scope) — this is a cross-repo diagnostic tool invoked from
    wherever the operator happens to be standing, so a per-cwd project
    dir would scatter logs unpredictably instead of one place a human
    (or a script) can always find. Per
    ``01_arch_06_local-state-directories.md`` §1: logs go under
    ``runtime/``, never a bare ``/tmp`` tempfile — so a long-running
    ``--trace`` invocation can be watched live with ``tail -f`` and
    inspected afterwards instead of vanishing on exit.
    """
    from scitex_config._ecosystem import local_state

    log_dir = local_state.user_path("dev") / "runtime" / "trace-env-vars"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return log_dir / f"{ts}-{_sanitize_command(command)}.log"


def trace_env_vars(
    names: list[str],
    command: list[str],
    strace_string_size: int = 65_536,
    timeout: float | None = 300.0,
    announce: bool = True,
) -> TraceEnvResult:
    """Run ``command`` under strace; report first exec stage per var.

    Returns a :class:`TraceEnvResult` in ``mode="trace"``. When strace is
    missing, ``error`` carries an actionable message and no command is
    run. When strace runs but produces no execve data (e.g. ptrace is
    denied in the container — the primary in-container use case this tool
    is for), the result is reported as *inconclusive* rather than as a
    false "var never injected".

    ``announce=False`` suppresses the "watch live" stderr hint — set by
    callers emitting machine-readable output (e.g. ``--json``), since
    some runners (Click's ``CliRunner``) merge stderr into the captured
    stdout and would otherwise corrupt the parseable payload.
    """
    if not shutil.which("strace"):
        return TraceEnvResult(
            variables=_unset_report(names),
            mode="trace",
            error=_STRACE_MISSING,
        )
    if not command:
        return TraceEnvResult(
            variables=_unset_report(names),
            mode="trace",
            error="no command given to --trace (expected: ... --trace -- CMD ARGS)",
        )

    out_path = _new_log_path(command)
    if announce:
        print(
            f"[trace-env-vars] tracing under strace (multi-stage launches "
            f"can take a while) — watch live: tail -f {out_path}",
            file=sys.stderr,
        )
    stderr_text = ""
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
    # Capture strace's own stderr (ptrace-denied diagnostics land
    # here) while letting the traced command's stdout pass through.
    try:
        proc = subprocess.run(
            argv,
            timeout=timeout,
            check=False,
            stderr=subprocess.PIPE,
            text=True,
        )
        stderr_text = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        err = exc.stderr
        stderr_text = err if isinstance(err, str) else ""
    raw = out_path.read_text(encoding="utf-8", errors="replace")
    try:
        out_path.write_text(_redact_raw_log(raw), encoding="utf-8")
    except OSError:
        pass

    return _result_from_trace(names, raw, stderr_text)


# EOF
