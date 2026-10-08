"""Actions variable behavior through an explicit synthetic driver boundary."""
import json
import subprocess

import pytest

from scitex_dev.ci.runner import _variables


def driver(existing=True, failure=None):
    calls = []
    private = "PRIVATE_BODY_DO_NOT_EMIT"
    def invoke(argv):
        calls.append(argv)
        n = len(calls)
        if failure == "lookup" or failure == "write" and n == 2:
            return subprocess.CompletedProcess(argv, 1, stdout=private, stderr=private)
        if n == 1:
            payload = {"name": "CI_RUNS_ON", "value": "old"} if existing else {"status": "404"}
            return subprocess.CompletedProcess(argv, 0 if existing else 1, stdout=json.dumps(payload), stderr="")
        payload = {"name": "CI_RUNS_ON", "value": '["ubuntu-latest"]' if failure != "readback" else "wrong"}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")
    return invoke, calls


@pytest.mark.parametrize("existing,method,endpoint", [
    (True, "PATCH", "repos/ywatanabe1989/.dotfiles/actions/variables/CI_RUNS_ON"),
    (False, "POST", "repos/ywatanabe1989/.dotfiles/actions/variables")])
def test_mutation_request_has_exact_create_or_update_contract(existing, method, endpoint):
    # Arrange
    invoke, calls = driver(existing)
    # Act
    _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]', invoke=invoke)
    # Assert
    assert calls[1] == ["gh", "api", endpoint, "--method", method, "-f", "name=CI_RUNS_ON", "-f", 'value=["ubuntu-latest"]']


def test_success_requires_actual_destination_readback():
    # Arrange
    invoke, calls = driver()
    # Act
    _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]', invoke=invoke)
    # Assert
    assert calls[-1] == ["gh", "api", "repos/ywatanabe1989/.dotfiles/actions/variables/CI_RUNS_ON"]


@pytest.mark.parametrize("failure,message", [("lookup", "lookup unavailable"), ("write", "write failed"), ("readback", "readback did not confirm")])
def test_unknown_api_or_failed_write_or_readback_remains_a_visible_failure(failure, message):
    # Arrange
    invoke, calls = driver(failure=failure)
    # Act
    # Assert
    with pytest.raises(ValueError, match=message):
        _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]', invoke=invoke)


def test_private_driver_errors_are_not_exposed():
    # Arrange
    invoke, calls = driver(failure="lookup")
    error = None
    # Act
    try:
        _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]', invoke=invoke)
    except ValueError as exc:
        error = str(exc)
    # Assert
    assert error == "Actions variable lookup unavailable; no write attempted"


def test_ambiguous_lookup_cannot_authorize_a_mutation():
    # Arrange
    invoke, calls = driver(failure="lookup")
    # Act
    try:
        _variables.set_runs_on("ywatanabe1989/.dotfiles", "CI_RUNS_ON", '["ubuntu-latest"]', invoke=invoke)
    except ValueError:
        pass
    # Assert
    assert len(calls) == 1


@pytest.mark.parametrize("repo,name", [("scitex-ai/../escape", "CI_RUNS_ON"), ("scitex-ai/repo", "CI_RUNS_ON/../../other")])
def test_invalid_target_refuses_before_any_driver_call(repo, name):
    # Arrange
    invoke, calls = driver()
    # Act
    try:
        _variables.set_runs_on(repo, name, '["ubuntu-latest"]', invoke=invoke)
    except ValueError:
        pass
    # Assert
    assert calls == []
