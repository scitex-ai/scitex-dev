"""Bounded Git trace joins use real process evidence and fail closed."""

import copy
import json
import subprocess

import pytest

from ._release_trace_correlation import correlate_git_trace_candidate

COMMAND = ["git", "--version"]
SID = "20261118T211137.364828Z-H4809c6ad-P000004d2"


def records():
    return [{"event": "version", "sid": SID, "evt": "3", "exe": "2.43.0"},
            {"event": "start", "sid": SID, "argv": COMMAND}]


def encoded(events):
    return "".join(json.dumps(event) + "\n" for event in events)


def observation():
    return {"samples": [{"state": "observed", "child": {"pid": 1234, "birth_ticks": 7}}]}


def test_known_trace_and_consistent_samples_correlate_without_echoing_inputs():
    # Arrange
    events = records()
    events[0]["private"] = "private-marker"
    samples = observation()
    samples["samples"] *= 2
    # Act
    result = correlate_git_trace_candidate(COMMAND, encoded(events), samples)
    # Assert
    assert (result["state"], result["git_pid_low32"], result["matching_candidate_samples"]) == ("correlated", 1234, 2)


def test_correlated_result_does_not_echo_trace_content():
    # Arrange
    events = records()
    events[0]["private"] = "private-marker"
    # Act
    result = correlate_git_trace_candidate(COMMAND, encoded(events), observation())
    # Assert
    assert SID not in json.dumps(result) and "private-marker" not in json.dumps(result)


@pytest.mark.parametrize("trace", [None, "", " " * (8193 - len(encoded(records()))) + encoded(records()), "not-json\n", "[]\n", encoded(records())[:-1]])
def test_incomplete_malformed_or_unbounded_trace_stays_unknown(trace):
    # Arrange
    samples = observation()
    # Act
    result = correlate_git_trace_candidate(COMMAND, trace, samples)
    # Assert
    assert result["state"] == "unknown"


def test_complete_valid_trace_at_character_bound_is_accepted():
    # Arrange
    trace = encoded(records())
    trace = " " * (8192 - len(trace)) + trace
    # Act
    result = correlate_git_trace_candidate(COMMAND, trace, observation())
    # Assert
    assert result["state"] == "correlated"


def test_exact_candidate_sample_bound_is_accepted():
    # Arrange
    samples = observation()
    samples["samples"] *= 24
    # Act
    result = correlate_git_trace_candidate(COMMAND, encoded(records()), samples)
    # Assert
    assert result["matching_candidate_samples"] == 24


def unsupported_trace(change):
    events = records()
    if change == "version":
        events[0]["exe"] = "2.44.0"
    elif change == "format":
        events[0]["evt"] = "4"
    elif change == "sid":
        events[1]["sid"] = "private-unsupported-session"
    elif change == "command":
        events[1]["argv"] = ["git", "private-other-command"]
    elif change == "zero":
        for event in events:
            event["sid"] = SID[:-8] + "00000000"
    elif change == "duplicate-start":
        events.append(copy.deepcopy(events[1]))
    else:
        events.append(copy.deepcopy(events[0]))
    return encoded(events)


@pytest.mark.parametrize("change", ["version", "format", "sid", "command", "zero", "duplicate-start", "duplicate-version"])
def test_unsupported_or_ambiguous_trace_is_not_correlated(change):
    # Arrange
    trace = unsupported_trace(change)
    # Act
    result = correlate_git_trace_candidate(COMMAND, trace, observation())
    # Assert
    assert result["state"] == "unknown"


def unsupported_candidates(change):
    samples = observation()
    if change == "missing":
        samples = None
    elif change == "empty":
        samples["samples"] = []
    elif change == "too-many":
        samples["samples"] *= 25
    elif change == "other-pid":
        samples["samples"][0]["child"]["pid"] = 4321
    elif change == "bool-pid":
        samples["samples"][0]["child"]["pid"] = True
    elif change == "changed-birth":
        samples["samples"].append({"state": "observed", "child": {"pid": 1234, "birth_ticks": 8}})
    else:
        samples["samples"] = ["private-malformed-row"]
    return samples


@pytest.mark.parametrize("change", ["missing", "empty", "too-many", "other-pid", "bool-pid", "changed-birth", "malformed"])
def test_missing_mixed_or_unbounded_candidates_stay_unknown(change):
    # Arrange
    samples = unsupported_candidates(change)
    # Act
    result = correlate_git_trace_candidate(COMMAND, encoded(records()), samples)
    # Assert
    assert result["state"] == "unknown"


def test_unknown_result_does_not_echo_private_inputs():
    # Arrange
    samples = {"samples": ["private-malformed-row"]}
    # Act
    result = correlate_git_trace_candidate(COMMAND, "private-invalid-trace\n", samples)
    # Assert
    assert "private-" not in json.dumps(result)


@pytest.fixture(scope="module")
def real_git_observation(tmp_path_factory):
    root = tmp_path_factory.mktemp("trace-correlation")
    trace = root / "trace.jsonl"
    environment = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_TRACE2_EVENT": str(trace)}
    with subprocess.Popen(COMMAND, cwd=root, env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        stdout, stderr = child.communicate(timeout=5)
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    # Candidate data is structured control input with the real child's PID.
    # The fixed birth value is not a live procfs birth observation.
    samples = {"samples": [{"state": "observed", "child": {"pid": child.pid, "birth_ticks": 7}}]}
    version = next(event for event in events if event.get("event") == "version")
    supported = version["exe"] == "2.43.0" and version["evt"] == "3" and child.pid <= 0xffffffff
    expected = ("correlated", child.pid) if supported else ("unknown", None)
    return child.returncode, stdout, stderr, trace.read_text(), samples, expected


def test_real_git_version_command_completes_without_stderr(real_git_observation):
    # Arrange
    code, stdout, stderr, _, _, _ = real_git_observation
    # Act
    actual = (code, stdout.startswith(b"git version "), stderr)
    # Assert
    assert actual == (0, True, b"")


def test_real_git_trace_joins_actual_pid_or_refuses_unknown_version(real_git_observation):
    # Arrange
    _, _, _, trace, samples, expected = real_git_observation
    # Act
    result = correlate_git_trace_candidate(COMMAND, trace, samples)
    # Assert
    assert (result["state"], result.get("git_pid_low32")) == expected
