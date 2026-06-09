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


# ---------------------------------------------------------------------------
# scitex-todo hook — pure helper + DI-seam tests
# ---------------------------------------------------------------------------
#
# Tests use hand-rolled fakes (PA-306 / STX-NM*). No unittest.mock, no
# monkeypatch, no real scitex-todo import. The production code's
# `todo_api` keyword seam is exactly the injection point.


class _FakeTaskValidationError(Exception):
    """Stand-in for scitex_todo._model.TaskValidationError."""


class _FakeAddTaskCallable:
    """Hand-rolled fake of scitex_todo._store.add_task.

    Captures every call's kwargs into ``calls`` and raises ``raises``
    when set. Mirrors the real ``add_task(store_path, /, **fields)``
    positional shape so the production call site exercises its real
    signature path.
    """

    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, store_path, **kwargs) -> None:
        self.calls.append({"store_path": store_path, **kwargs})
        if self.raises is not None:
            raise self.raises


def _make_fake_todo_api(raises: Exception | None = None) -> _ci_watch._TodoApi:
    """Build a _TodoApi populated with hand-rolled fakes."""
    return _ci_watch._TodoApi(
        add_task=_FakeAddTaskCallable(raises=raises),
        validation_error_cls=_FakeTaskValidationError,
        store_path="/tmp/fake-todo-store.yaml",
    )


def test_todo_task_id_normalizes_workflow_slug():
    # Arrange
    repo = "ywatanabe1989/scitex-stats"
    workflow = "pytest-matrix-on-ubuntu-py3.12"
    head_sha = "abcd1234567890abcdef00000000000000000000"

    # Act
    task_id = _ci_watch._todo_task_id_for(repo, workflow, head_sha)

    # Assert
    assert task_id == "ci-fail-scitex-stats-pytest-matrix-on-ubuntu-py3-12-abcd1234"


def test_todo_task_id_falls_back_when_sha_empty():
    # Arrange
    repo = "ywatanabe1989/scitex-stats"
    workflow = "tests"
    head_sha = ""

    # Act
    task_id = _ci_watch._todo_task_id_for(repo, workflow, head_sha)

    # Assert
    assert task_id == "ci-fail-scitex-stats-tests-nosha"


def test_create_todo_new_path_calls_add_task_once():
    # Arrange
    api = _make_fake_todo_api()
    failing = _ci_watch.FailingRun(
        workflow="tests",
        run_id=42,
        head_sha="abcd1234ef567890abcdef00000000000000bbbb",
    )

    # Act
    created = _ci_watch._create_todo_if_new(
        agent="proj-scitex-stats",
        repo="ywatanabe1989/scitex-stats",
        failing_run=failing,
        todo_api=api,
    )

    # Assert
    fake_add = api.add_task
    assert created is True and len(fake_add.calls) == 1 and fake_add.calls[0][
        "id"
    ] == "ci-fail-scitex-stats-tests-abcd1234"


def test_create_todo_duplicate_path_returns_false_silently():
    # Arrange
    dup_exc = _FakeTaskValidationError(
        "/store.yaml: duplicate task id 'ci-fail-scitex-stats-tests-abcd1234'"
    )
    api = _make_fake_todo_api(raises=dup_exc)
    failing = _ci_watch.FailingRun(
        workflow="tests",
        run_id=42,
        head_sha="abcd1234ef567890abcdef00000000000000bbbb",
    )

    # Act
    created = _ci_watch._create_todo_if_new(
        agent="proj-scitex-stats",
        repo="ywatanabe1989/scitex-stats",
        failing_run=failing,
        todo_api=api,
    )

    # Assert
    assert created is False


def test_create_todo_other_validation_error_reraises():
    # Arrange
    other_exc = _FakeTaskValidationError(
        "/store.yaml: required field 'title' missing"
    )
    api = _make_fake_todo_api(raises=other_exc)
    failing = _ci_watch.FailingRun(
        workflow="tests",
        run_id=42,
        head_sha="abcd1234ef567890abcdef00000000000000bbbb",
    )

    # Act
    # Assert
    with pytest.raises(_FakeTaskValidationError):
        _ci_watch._create_todo_if_new(
            agent="proj-scitex-stats",
            repo="ywatanabe1989/scitex-stats",
            failing_run=failing,
            todo_api=api,
        )


def test_create_todo_returns_false_when_api_missing():
    # Arrange
    failing = _ci_watch.FailingRun(
        workflow="tests",
        run_id=42,
        head_sha="abcd1234ef567890abcdef00000000000000bbbb",
    )

    # Act — pass todo_api=None and rely on _resolve_todo_api short-circuit.
    # In CI sandboxes without scitex-todo installed (or whenever the
    # import path raises) the production helper degrades to no-op.
    # We replace the module-level resolver with one that returns None
    # so the test does not depend on the test runner's installed deps.
    saved_resolve = _ci_watch._resolve_todo_api
    _ci_watch._resolve_todo_api = lambda store_path=None: None  # type: ignore[assignment]
    try:
        created = _ci_watch._create_todo_if_new(
            agent="proj-scitex-stats",
            repo="ywatanabe1989/scitex-stats",
            failing_run=failing,
            todo_api=None,
        )
    finally:
        _ci_watch._resolve_todo_api = saved_resolve  # type: ignore[assignment]

    # Assert
    assert created is False


def test_red_runs_extracts_head_sha_and_run_id():
    # Arrange — gh JSON now includes headSha alongside the existing fields.
    payload = json.dumps(
        [
            {
                "conclusion": "failure",
                "workflowName": "tests",
                "databaseId": 99,
                "headSha": "deadbeef00000000000000000000000000000000",
            },
            {
                "conclusion": "success",
                "workflowName": "rtd",
                "databaseId": 98,
                "headSha": "cafef00d00000000000000000000000000000000",
            },
        ]
    )
    gh = _gh_runner_for(payload)

    # Act
    reds = _ci_watch.red_runs_for("owner/repo", gh_runner=gh)

    # Assert
    assert reds == [
        _ci_watch.FailingRun(
            workflow="tests",
            run_id=99,
            head_sha="deadbeef00000000000000000000000000000000",
        )
    ]
