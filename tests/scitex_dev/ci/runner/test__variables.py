"""Actions variables require different create/update API routes."""
import json
import subprocess

import pytest

from scitex_dev.ci.runner import _variables


@pytest.mark.parametrize("exists,method,endpoint", [
    (True, "PATCH", "repos/ywatanabe1989/.dotfiles/actions/variables/CI_RUNS_ON"),
    (False, "POST", "repos/ywatanabe1989/.dotfiles/actions/variables"),
])
def test_hosted_destination_is_written_with_real_create_or_update_contract(monkeypatch, exists, method, endpoint):
    calls = []
    def invoke(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return subprocess.CompletedProcess(argv, 0 if exists else 1,
                stdout=json.dumps({"name": "CI_RUNS_ON", "value": "old"} if exists else {"status": "404"}), stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout='{"name":"CI_RUNS_ON","value":"[\\"ubuntu-latest\\"]"}' if len(calls) == 3 else "", stderr="")
    monkeypatch.setattr(_variables.subprocess, "run", invoke)
    _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]')
    assert calls[1][2] == endpoint
    assert calls[1][calls[1].index("--method") + 1] == method
    assert "name=CI_RUNS_ON" in calls[1]
    assert 'value=["ubuntu-latest"]' in calls[1]
    assert calls[2][2] == "repos/ywatanabe1989/.dotfiles/actions/variables/CI_RUNS_ON"


def test_api_failure_or_ambiguous_404_never_mutates_or_logs_private_error(monkeypatch):
    calls = []
    private = "PRIVATE_BODY_DO_NOT_PRINT"
    def invoke(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, stdout=private, stderr=private)
    monkeypatch.setattr(_variables.subprocess, "run", invoke)
    with pytest.raises(ValueError) as error:
        _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]')
    assert len(calls) == 1
    assert private not in str(error.value)


def test_destination_writes_are_visible_failures_not_success_warnings(monkeypatch):
    calls = []
    def invoke(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0 if len(calls) == 1 else 1,
            stdout='{"name":"CI_RUNS_ON","value":"old"}', stderr="PRIVATE_WRITE_BODY")
    monkeypatch.setattr(_variables.subprocess, "run", invoke)
    with pytest.raises(ValueError, match="write failed"):
        _variables.set_runs_on("scitex-ai/scitex-dev", "CI_RUNS_ON", '["ubuntu-latest"]')


@pytest.mark.parametrize("repo,name", [("scitex-ai/../escape", "CI_RUNS_ON"),
                                       ("scitex-ai/repo", "CI_RUNS_ON/../../other")])
def test_target_path_is_bounded_before_any_api_call(monkeypatch, repo, name):
    def forbidden(*a, **k):
        pytest.fail("unsafe target reached API")
    monkeypatch.setattr(_variables.subprocess, "run", forbidden)
    with pytest.raises(ValueError):
        _variables.set_runs_on(repo, name, '["ubuntu-latest"]')
