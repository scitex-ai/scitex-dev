#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: scitex_dev/trace_env/__init__.py

"""Trace where an environment variable is defined or injected.

A "silver bullet" for diagnosing WHERE a (possibly stale) env var comes
from. Two modes:

- static scan (:func:`scan_env_vars`) — every assignment site across
  shell init files, direnv, tmux global env, and the current process
  environment, with WORD-BOUNDARY matching (``FOO`` never matches
  ``FOO_BAR``) and secret-value redaction.
- dynamic trace (:func:`trace_env_vars`) — run a command under strace
  and report the FIRST exec stage whose child env carries the var,
  pinpointing the process layer that injects it in a multi-stage launch.
"""

from .config import (
    Assignment,
    ExecStageHit,
    TraceEnvResult,
    VarReport,
    assignment_regex,
    is_secret_shaped,
    redact,
)
from .report import format_quiet, format_report
from .scan import scan_env_vars
from .trace import trace_env_vars

__all__ = [
    "Assignment",
    "ExecStageHit",
    "TraceEnvResult",
    "VarReport",
    "assignment_regex",
    "is_secret_shaped",
    "redact",
    "format_quiet",
    "format_report",
    "scan_env_vars",
    "trace_env_vars",
]

# EOF
