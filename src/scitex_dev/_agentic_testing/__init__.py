"""Agentic-test harness — runs `claude` CLI against eval skills + asserts.

Module map:
- `_core`   — runners (HostRunner, NewbieDockerRunner), eval primitives
- `_poc`    — `python -m scitex_dev._agentic_testing._poc` smoke entrypoint
- `_pytest` — `make_skill_trigger_tests(...)` factory for pytest integration
"""

from __future__ import annotations

from ._core import (
    DEFAULT_ACCOUNTS,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    RUNS_PER_CASE,
    ClaudeCodePool,
    ClaudeRunner,
    EvalCase,
    HostRunner,
    NewbieDockerRunner,
    TriggerResult,
    extract_viewed_paths,
    get_runner,
    load_eval_set,
    run_trigger_case,
)
from ._pytest import make_skill_trigger_tests

__all__ = [
    "DEFAULT_ACCOUNTS",
    "DEFAULT_DOCKER_IMAGE",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT",
    "RUNS_PER_CASE",
    "ClaudeCodePool",
    "ClaudeRunner",
    "EvalCase",
    "HostRunner",
    "NewbieDockerRunner",
    "TriggerResult",
    "extract_viewed_paths",
    "get_runner",
    "load_eval_set",
    "run_trigger_case",
    "make_skill_trigger_tests",
]
