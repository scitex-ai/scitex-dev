"""Unit tests for scitex_dev._cli.cron._ci_watch.

No live `gh` calls. We pass real callable fakes for the gh and sac
runner seams (per PA-306 / STX-NM*). The fakes return CompletedProcess-
shaped objects so the production code exercises its real JSON parse
path and its real result-aggregation path.
"""

from __future__ import annotations

import io
import json

import pytest

from scitex_dev._cli.cron import _ci_watch


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# Fixture: shape of `gh run list ... --json conclusion,workflowName,databaseId`.
# gh returns runs newest-first. We have two workflows:
#   - "ci"     — latest run is success
#   - "rtd"    — latest run is failure (older successes shouldn't matter)
_GH_JSON_FIXTURE = json.dumps(
    [
        {"conclusion": "success", "workflowName": "ci", "databaseId": 5},
        {"conclusion": "failure", "workflowName": "rtd", "databaseId": 4},
        {"conclusion": "success", "workflowName": "rtd", "databaseId": 3},
        {"conclusion": "failure", "workflowName": "ci", "databaseId": 2},
    ]
)

_GH_JSON_ALL_GREEN = json.dumps(
    [
        {"conclusion": "success", "workflowName": "ci", "databaseId": 5},
        {"conclusion": "success", "workflowName": "rtd", "databaseId": 4},
    ]
)


def _gh_runner_for(stdout: str, *, returncode: int = 0):
    """Return a fake gh runner that always replies with ``stdout``."""

    def _runner(args: list[str]) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=returncode, stdout=stdout)

    return _runner


# ---------------------------------------------------------------------------
# red_workflows_for
# ---------------------------------------------------------------------------


def test_red_workflows_returns_only_workflows_with_latest_failure():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    # Act
    reds = _ci_watch.red_workflows_for("owner/repo", gh_runner=gh)
    # Assert
    assert reds == ["rtd"]


def test_red_workflows_returns_empty_when_all_green():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_ALL_GREEN)
    # Act
    reds = _ci_watch.red_workflows_for("owner/repo", gh_runner=gh)
    # Assert
    assert reds == []


def test_red_workflows_returns_empty_for_empty_run_list():
    # Arrange
    gh = _gh_runner_for("[]")
    # Act
    reds = _ci_watch.red_workflows_for("owner/repo", gh_runner=gh)
    # Assert
    assert reds == []


def test_red_workflows_raises_on_gh_failure():
    # Arrange

    gh = _gh_runner_for("", returncode=1)
    # Act
    # Assert
    with pytest.raises(RuntimeError):
        _ci_watch.red_workflows_for("owner/repo", gh_runner=gh)


def test_red_workflows_calls_gh_with_repo_flag():
    # Arrange
    captured: dict = {}

    def gh(args):
        captured["args"] = args
        return _FakeCompletedProcess(returncode=0, stdout="[]")

    # Act
    _ci_watch.red_workflows_for("owner/scitex-stats", gh_runner=gh)
    # Assert
    assert "owner/scitex-stats" in captured["args"]


def test_red_workflows_calls_gh_with_branch_develop():
    # Arrange
    captured: dict = {}

    def gh(args):
        captured["args"] = args
        return _FakeCompletedProcess(returncode=0, stdout="[]")

    # Act
    _ci_watch.red_workflows_for("owner/scitex-stats", gh_runner=gh)
    # Assert
    assert "develop" in captured["args"]


# ---------------------------------------------------------------------------
# build_fix_prompt
# ---------------------------------------------------------------------------


def test_build_fix_prompt_mentions_repo():
    # Arrange
    # Act
    prompt = _ci_watch.build_fix_prompt("owner/scitex-stats", ["rtd"])
    # Assert
    assert "owner/scitex-stats" in prompt


def test_build_fix_prompt_lists_first_red_workflow():
    # Arrange
    # Act
    prompt = _ci_watch.build_fix_prompt("owner/repo", ["rtd", "ci"])
    # Assert
    assert "rtd" in prompt


def test_build_fix_prompt_lists_second_red_workflow():
    # Arrange
    # Act
    prompt = _ci_watch.build_fix_prompt("owner/repo", ["rtd", "ci"])
    # Assert
    assert "ci" in prompt


def test_build_fix_prompt_asks_for_pr_url_or_blocked():
    # Arrange
    # Act
    prompt = _ci_watch.build_fix_prompt("owner/repo", ["rtd"])
    # Assert
    assert "BLOCKED" in prompt


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------


def test_run_once_dry_run_does_not_call_sac():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    sac_calls: list = []

    def sac(args, *, input_text=""):
        sac_calls.append(args)
        return _FakeCompletedProcess(returncode=0)

    out = io.StringIO()
    # Act
    _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/repo"},
        dry_run=True,
        gh_runner=gh,
        sac_runner=sac,
        out=out,
    )
    # Assert
    assert sac_calls == []


def test_run_once_dry_run_prints_would_be_prompt():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    out = io.StringIO()
    # Act
    _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/repo"},
        dry_run=True,
        gh_runner=gh,
        out=out,
    )
    # Assert
    assert "would dispatch" in out.getvalue()


def test_run_once_all_green_returns_no_red_result():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_ALL_GREEN)
    out = io.StringIO()
    # Act
    results = _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/repo"},
        dry_run=True,
        gh_runner=gh,
        out=out,
    )
    # Assert
    assert results[0].red_workflows == ()


def test_run_once_red_repo_dispatches_when_not_dry_run():
    # Arrange — sac_runner sees `db query` (busy-probe, returns empty
    # row so dispatch proceeds) AND `agents send` (the real dispatch).
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    sac_calls: list = []

    def sac(args, *, input_text=""):
        sac_calls.append(args)
        # db query returns an empty JSON list → busy probe sees no
        # active row → falls through (no probe possible, treat as not-busy).
        if args and args[0] == "db":
            return _FakeCompletedProcess(returncode=0, stdout="[]")
        return _FakeCompletedProcess(returncode=0, stdout="ok")

    out = io.StringIO()
    # Act
    _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/repo"},
        dry_run=False,
        gh_runner=gh,
        sac_runner=sac,
        out=out,
    )
    # Assert — exactly one `agents send` call dispatched (db query is
    # the busy-probe; this assertion targets the dispatch surface).
    send_calls = [c for c in sac_calls if c and c[0] == "agents" and c[1] == "send"]
    assert len(send_calls) == 1


def test_run_once_dispatches_to_named_agent():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    sac_calls: list = []

    def sac(args, *, input_text=""):
        sac_calls.append(args)
        if args and args[0] == "db":
            return _FakeCompletedProcess(returncode=0, stdout="[]")
        return _FakeCompletedProcess(returncode=0, stdout="ok")

    out = io.StringIO()
    # Act
    _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/repo"},
        dry_run=False,
        gh_runner=gh,
        sac_runner=sac,
        out=out,
    )
    # Assert
    send_calls = [c for c in sac_calls if c and c[0] == "agents" and c[1] == "send"]
    assert send_calls[0][:3] == ["agents", "send", "agent-x"]


def test_run_once_only_agent_filters_other_agents():
    # Arrange
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    out = io.StringIO()
    # Act
    results = _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/a", "agent-y": "owner/b"},
        only_agent="agent-x",
        dry_run=True,
        gh_runner=gh,
        out=out,
    )
    # Assert
    assert [r.agent for r in results] == ["agent-x"]


def test_run_once_records_error_when_gh_fails():
    # Arrange
    gh = _gh_runner_for("", returncode=1)
    out = io.StringIO()
    # Act
    results = _ci_watch.run_once(
        agents_to_repos={"agent-x": "owner/repo"},
        dry_run=True,
        gh_runner=gh,
        out=out,
    )
    # Assert
    assert results[0].error is not None


# ---------------------------------------------------------------------------
# _is_agent_busy — fail-open semantics against the sac /_active endpoint
# ---------------------------------------------------------------------------


def _http_runner_returning(status: int, body: bytes):
    """Return a fake HTTP runner that always replies with (status, body)."""

    def _runner(url: str, timeout: float) -> tuple[int, bytes]:
        return status, body

    return _runner


def _http_runner_raising(exc: Exception):
    def _runner(url: str, timeout: float) -> tuple[int, bytes]:
        raise exc

    return _runner


def test_is_agent_busy_returns_true_when_tasks_list_non_empty():
    # Arrange
    runner = _http_runner_returning(200, b'{"tasks":[{"id":"t1","state":"running"}]}')
    # Act
    busy = _ci_watch._is_agent_busy("h", 1234, "a", http_runner=runner)
    # Assert
    assert busy is True


def test_is_agent_busy_returns_false_when_tasks_list_empty():
    # Arrange
    runner = _http_runner_returning(200, b'{"tasks":[]}')
    # Act
    busy = _ci_watch._is_agent_busy("h", 1234, "a", http_runner=runner)
    # Assert
    assert busy is False


def test_is_agent_busy_fails_open_on_404_response():
    # Arrange
    runner = _http_runner_returning(404, b'{"error":"unknown agent"}')
    # Act
    busy = _ci_watch._is_agent_busy("h", 1234, "a", http_runner=runner)
    # Assert
    assert busy is False


def test_is_agent_busy_fails_open_on_runner_exception():
    # Arrange
    runner = _http_runner_raising(TimeoutError("probe timeout"))
    # Act
    busy = _ci_watch._is_agent_busy("h", 1234, "a", http_runner=runner)
    # Assert
    assert busy is False


def test_is_agent_busy_fails_open_on_non_json_body():
    # Arrange
    runner = _http_runner_returning(200, b"not json")
    # Act
    busy = _ci_watch._is_agent_busy("h", 1234, "a", http_runner=runner)
    # Assert
    assert busy is False


def test_is_agent_busy_fails_open_when_tasks_key_missing():
    # Arrange
    runner = _http_runner_returning(200, b'{"other":"shape"}')
    # Act
    busy = _ci_watch._is_agent_busy("h", 1234, "a", http_runner=runner)
    # Assert
    assert busy is False


# EOF
def test_run_once_skips_dispatch_when_agent_busy():
    """When the busy-probe sees active tasks, sac agents send is NOT called."""
    # Arrange
    gh = _gh_runner_for(_GH_JSON_FIXTURE)
    sac_calls: list = []

    def sac(args, *, input_text=""):
        sac_calls.append(args)
        # db query returns a live row → busy probe gets a (host, port).
        if args and args[0] == "db":
            return _FakeCompletedProcess(
                returncode=0,
                stdout='[{"host":"h","a2a_port":12345}]',
            )
        return _FakeCompletedProcess(returncode=0, stdout="ok")

    # HTTP probe returns a non-empty tasks list → busy → must skip.
    busy_http = _http_runner_returning(
        200, b'{"tasks":[{"id":"t1","state":"running"}]}'
    )

    # Swap the module-level default http runner so _is_agent_busy uses it.
    saved = _ci_watch._default_http_runner
    _ci_watch._default_http_runner = busy_http  # type: ignore[assignment]
    try:
        out = io.StringIO()
        # Act
        _ci_watch.run_once(
            agents_to_repos={"agent-x": "owner/repo"},
            dry_run=False,
            gh_runner=gh,
            sac_runner=sac,
            out=out,
        )
    finally:
        _ci_watch._default_http_runner = saved  # type: ignore[assignment]
    # Assert — busy was detected, dispatch was skipped (only db query happened).
    send_calls = [c for c in sac_calls if c and c[0] == "agents" and c[1] == "send"]
    assert send_calls == []
