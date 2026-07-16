"""Tests for the run-level resolver (``scitex_dev.ci.why._resolve``).

No mocks. The default ``run_gh`` seam is exercised through its ``_run``
injection point (a plain callable returning a ``CompletedProcess``); the
resolver + ``explain_run`` + ``explain_ci_run`` through an injected
``run_gh`` callable returning canned gh output. Nothing here touches the
network. AAA, one logical assertion per test.
"""

from __future__ import annotations

import json
import subprocess

from scitex_dev.ci.why import (
    CIWhyError,
    RunFailures,
    explain_ci_run,
    explain_run,
    render_text,
    resolve_run_ids,
    run_gh,
)
from tests.scitex_dev.ci.why.test__parse import PYTEST_LOG, _PJ


# ---------------------------------------------------------------------------
# run_gh seam — honest failure, and gh-pr-checks non-zero semantics.
# ---------------------------------------------------------------------------


def test_run_gh_raises_when_gh_missing():
    # Arrange
    def _no_gh(*_a, **_kw):
        raise FileNotFoundError("gh")

    captured = None
    # Act
    try:
        run_gh(["run", "list"], _run=_no_gh)
    except CIWhyError as exc:
        captured = exc
    # Assert
    assert captured is not None


def test_run_gh_returns_stdout_on_nonzero_with_output():
    # Arrange — gh pr checks exits non-zero when checks fail, yet prints JSON.
    def _fake(argv, **_kw):
        return subprocess.CompletedProcess(argv, 1, stdout='[{"a":1}]', stderr="")

    # Act
    out = run_gh(["pr", "checks", "712"], _run=_fake)
    # Assert
    assert out == '[{"a":1}]'


def test_run_gh_raises_on_nonzero_with_empty_output():
    # Arrange — a bad run id: non-zero AND nothing on stdout is a real error.
    def _fake(argv, **_kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")

    captured = None
    # Act
    try:
        run_gh(["run", "view", "0"], _run=_fake)
    except CIWhyError as exc:
        captured = exc
    # Assert
    assert captured is not None


# ---------------------------------------------------------------------------
# resolve_run_ids — target → failing run id(s), through the injected seam.
# ---------------------------------------------------------------------------


def test_resolve_run_ids_treats_large_number_as_run_id_without_calling_gh():
    # Arrange — a run id must not cost a gh round-trip.
    def _boom(_args):
        raise RuntimeError("gh should not be called for a bare run id")

    # Act
    ids = resolve_run_ids("29446283736", run_gh=_boom)
    # Assert
    assert ids == ["29446283736"]


def test_resolve_run_ids_pr_number_extracts_failing_run_id():
    # Arrange — one failing check, its link carries the run id.
    checks = [
        {"bucket": "pass", "state": "SUCCESS", "link": ".../actions/runs/111/job/1"},
        {
            "bucket": "fail",
            "state": "FAILURE",
            "link": "https://github.com/o/r/actions/runs/29446283736/job/9",
        },
    ]

    def _fake(_args):
        return json.dumps(checks)

    # Act
    ids = resolve_run_ids("712", run_gh=_fake)
    # Assert
    assert ids == ["29446283736"]


# ---------------------------------------------------------------------------
# explain_run / explain_ci_run — through the injected run_gh seam.
# ---------------------------------------------------------------------------


def _gh_router(jobs: list, log_text: str):
    """A canned run_gh: run-view JSON on --json, the log on --log-failed."""

    def _router(args: list) -> str:
        if "--log-failed" in args:
            return log_text
        if "--json" in args:
            return json.dumps(
                {
                    "workflowName": "tests",
                    "displayTitle": "t",
                    "headBranch": "b",
                    "jobs": jobs,
                }
            )
        raise RuntimeError(f"unexpected gh args: {args}")

    return _router


def test_explain_run_green_has_no_failures():
    # Arrange
    router = _gh_router([{"name": "x", "conclusion": "success"}], "")
    # Act
    run = explain_run("10000001", run_gh=router)
    # Assert
    assert run.failures == []


def test_explain_run_parses_the_failing_job():
    # Arrange
    jobs = [{"name": _PJ, "conclusion": "failure"}]
    router = _gh_router(jobs, PYTEST_LOG)
    # Act
    run = explain_run("10000002", run_gh=router)
    # Assert
    assert (
        run.failures[0]
        .failed_tests[0]
        .startswith("FAILED tests/test_math.py::test_math")
    )


def test_explain_ci_run_returns_a_list_of_run_failures():
    # Arrange
    jobs = [{"name": _PJ, "conclusion": "failure"}]
    router = _gh_router(jobs, PYTEST_LOG)
    # Act
    runs = explain_ci_run("10000003", run_gh=router)
    # Assert
    assert len(runs) == 1 and isinstance(runs[0], RunFailures)


# ---------------------------------------------------------------------------
# render_text — compact human output.
# ---------------------------------------------------------------------------


def test_render_text_says_no_failures_when_empty():
    # Arrange
    run = RunFailures(run_id="1")
    # Act
    rendered = render_text(run)
    # Assert
    assert rendered == "no failures"


def test_render_text_is_far_smaller_than_the_raw_log():
    # Arrange — the whole point: the reason costs a fraction of the log.
    jobs = [{"name": _PJ, "conclusion": "failure"}]
    run = explain_run("1", run_gh=_gh_router(jobs, PYTEST_LOG))
    # Act
    rendered = render_text(run)
    # Assert
    assert len(rendered) < len(PYTEST_LOG) // 2


def test_render_text_includes_the_failing_test_id():
    # Arrange
    jobs = [{"name": _PJ, "conclusion": "failure"}]
    run = explain_run("1", run_gh=_gh_router(jobs, PYTEST_LOG))
    # Act
    rendered = render_text(run)
    # Assert
    assert "tests/test_math.py::test_math" in rendered
