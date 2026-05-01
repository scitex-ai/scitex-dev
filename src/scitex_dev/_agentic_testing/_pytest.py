"""Drop-in pytest harness for skill trigger-rate tests.

Usage in a package's tests/test_skill_trigger.py:

    from scitex_dev._agentic_testing import make_skill_trigger_tests
    test_skill_trigger = make_skill_trigger_tests(
        eval_path="tests/skill_evals/<pkg>.json",
        model="claude-haiku-4-5",
        backend=None,  # or "host" | "docker"; None -> SCITEX_DEV_AGENTIC_BACKEND
    )
"""

from __future__ import annotations

import atexit
from pathlib import Path

import pytest

from ._core import (
    ClaudeRunner,
    EvalCase,
    get_runner,
    load_eval_set,
    run_trigger_case,
)


def make_skill_trigger_tests(
    eval_path: str | Path,
    model: str = "claude-haiku-4-5",
    backend: str | None = None,
):
    cases = load_eval_set(Path(eval_path))
    if not cases:

        def _no_cases():
            pytest.skip(f"no eval cases at {eval_path}")

        return _no_cases

    # Single session-wide runner, built lazily on first test so that
    # ``pytest --collect-only`` doesn't try to spin up a docker container.
    # close() is registered with atexit (docker runner also registers its
    # own, which is idempotent).
    _slot: dict[str, ClaudeRunner] = {}

    def _get() -> ClaudeRunner:
        if "r" not in _slot:
            r = get_runner(backend)
            _slot["r"] = r
            atexit.register(r.close)
        return _slot["r"]

    @pytest.mark.skill_trigger
    @pytest.mark.parametrize("case", cases, ids=lambda c: c.id)
    def _test(case: EvalCase):
        result = run_trigger_case(_get(), case, model=model)
        assert result.passed, (
            f"Trigger rate {result.pass_rate:.0%} for '{case.id}' "
            f"(expected {case.expected_skill!r}, got views "
            f"{result.viewed_paths_per_run})"
        )

    return _test
