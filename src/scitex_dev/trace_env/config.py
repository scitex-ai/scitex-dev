#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: scitex_dev/trace_env/config.py

"""Dataclasses + redaction/matching helpers for env-var tracing.

The engine (``scan.py`` / ``trace.py``) is pure and testable; this
module holds the value objects it returns plus the two pieces of shared
logic every surface needs:

- ``assignment_regex`` — WORD-BOUNDARY assignment matcher. Searching for
  ``SCITEX_TODO_AGENT`` must NOT match ``SCITEX_TODO_AGENT_ID`` (a
  different, longer variable). The compiled pattern anchors the name
  with a non-identifier boundary on both sides, then requires an ``=``.
- ``redact`` / ``is_secret_shaped`` — env dumps routinely carry API
  keys; any secret-shaped variable's VALUE is replaced with
  ``<redacted: N chars>`` in ALL output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Variable-name suffixes (as ``_``-delimited components) that mark a
# value as secret-shaped and therefore redaction-worthy.
_SECRET_TOKENS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASS",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "SESSION",
)
_SECRET_RE = re.compile(
    r"(?:^|_)(" + "|".join(_SECRET_TOKENS) + r")$", re.IGNORECASE
)


def is_secret_shaped(name: str) -> bool:
    """True if ``name`` looks secret-shaped (``*_KEY``/``*_TOKEN``/...).

    KNOWN LIMITATION — this is a deliberately conservative, name-based
    heuristic: it matches only when one of a fixed 9-keyword set (``KEY``,
    ``TOKEN``, ``SECRET``, ``PASSWORD``, ``PASS``, ``CREDENTIAL``,
    ``AUTH``, ``COOKIE``, ``SESSION``) is the LAST ``_``-delimited
    component of the name. So it catches ``AWS_SECRET_ACCESS_KEY`` and
    ``GH_TOKEN``, but MISSES names that carry a secret without one of
    those trailing keywords — e.g. ``GITHUB_PAT``, ``JSESSIONID``, or a
    ``DATABASE_URL`` with embedded credentials. Treat a non-redacted
    value as "not recognized as secret-shaped", NOT as "confirmed safe":
    do not over-trust this when pasting output into a shared channel.
    """
    return bool(_SECRET_RE.search(name))


def redact(name: str, value: str | None) -> str | None:
    """Return ``value`` verbatim, or ``<redacted: N chars>`` if secret.

    ``None`` (variable unset) passes through unchanged.
    """
    if value is None:
        return None
    if is_secret_shaped(name):
        return f"<redacted: {len(value)} chars>"
    return value


def assignment_regex(name: str) -> re.Pattern[str]:
    """Compile a WORD-BOUNDARY assignment matcher for ``name``.

    Matches ``NAME=`` / ``export NAME=`` / ``NAME =`` but NOT a longer
    identifier such as ``NAME_ID=``. The name is bounded by a
    non-identifier character on both sides; a single ``=`` (not ``==``)
    must follow, optionally after whitespace.
    """
    return re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(name)
        + r"(?![A-Za-z0-9_])\s*=(?!=)"
    )


@dataclass
class Assignment:
    """One place a variable is assigned on an environment-definition surface."""

    var: str
    surface: str  # e.g. "shell-init", "direnv", "tmux", "process-env"
    file: str
    line: int
    text: str  # matched line, value already redacted if secret-shaped


@dataclass
class VarReport:
    """Per-variable static-scan finding."""

    name: str
    currently_set: bool
    current_value: str | None  # redacted if secret-shaped
    secret_shaped: bool
    assignments: list[Assignment] = field(default_factory=list)


@dataclass
class ExecStageHit:
    """First ``execve`` stage at which a traced var appears in the child env."""

    var: str
    stage_index: int  # 0-based index into the observed execve sequence
    binary: str
    argv: list[str]
    value: str | None  # redacted if secret-shaped


@dataclass
class TraceEnvResult:
    """Aggregate result for both static-scan and dynamic-trace modes."""

    variables: list[VarReport]
    scanned_files: int = 0
    tmux_available: bool = False
    mode: str = "scan"  # "scan" | "trace"
    exec_stages: int = 0  # dynamic mode: number of execve calls observed
    trace_hits: list[ExecStageHit] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable view (mirrors rename-symbols' ``--json`` shape)."""
        return {
            "mode": self.mode,
            "scanned_files": self.scanned_files,
            "tmux_available": self.tmux_available,
            "exec_stages": self.exec_stages,
            "error": self.error,
            "variables": [
                {
                    "name": v.name,
                    "currently_set": v.currently_set,
                    "current_value": v.current_value,
                    "secret_shaped": v.secret_shaped,
                    "assignments": [
                        {
                            "surface": a.surface,
                            "file": a.file,
                            "line": a.line,
                            "text": a.text,
                        }
                        for a in v.assignments
                    ],
                }
                for v in self.variables
            ],
            "trace_hits": [
                {
                    "var": h.var,
                    "stage_index": h.stage_index,
                    "binary": h.binary,
                    "argv": h.argv,
                    "value": h.value,
                }
                for h in self.trace_hits
            ],
        }


# EOF
