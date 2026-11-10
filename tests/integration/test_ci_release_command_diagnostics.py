"""Real subprocess controls for timeout evidence without weakening deadlines."""

import json
import os
import subprocess
import sys

import pytest

from ._release_child_observation import OwnedChildObservation
from ._release_command import _LIMIT, _NOTE_PREFIX, _read_bounded, run_release_command


def test_real_timeout_keeps_deadline_and_actual_git_trace(tmp_path):
    # Arrange
    root = tmp_path / "fixture"
    root.mkdir()
    trace = tmp_path / "git-trace.jsonl"
    environment = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_TRACE2_EVENT": str(trace)}
    run_release_command(["git", "--version"], root, environment, check=True)
    command = [sys.executable, "-I", "-S", "-B", "-c", "import time; time.sleep(30)"]
    observed = None
    # Act
    try:
        run_release_command(command, root, environment, check=True)
    except subprocess.TimeoutExpired as error:
        note = next(note for note in error.__notes__ if note.startswith(_NOTE_PREFIX))
        evidence = json.loads(note[len(_NOTE_PREFIX):])
        events = [json.loads(line) for line in evidence["git_trace_tail"].splitlines()]
        observed = (error.timeout, error.cmd, evidence["timeout_seconds"],
                    any(event.get("name") == "version" for event in events),
                    "MemTotal:" in evidence["memory"],
                    set(evidence) >= {"observed_utc", "loadavg", "io_pressure", "memory"},
                    any(row.get("fixture_filesystem", {}).get("state") == "observed"
                        and row["fixture_filesystem"]["device"] == root.stat().st_dev
                        and 0 <= row["fixture_filesystem"]["available_bytes"]
                        <= row["fixture_filesystem"]["free_bytes"]
                        <= row["fixture_filesystem"]["capacity_bytes"]
                        for row in evidence["owned_child_observation"]["samples"]))
    # Assert
    assert observed == (5, command, 5, True, True, True, True)


def test_diagnostic_reads_are_bounded_and_missing_data_is_explicit(tmp_path):
    # Arrange
    trace = tmp_path / "git-trace.jsonl"
    trace.write_bytes(b"discard" + b"x" * _LIMIT)
    # Act
    observed = (_read_bounded(trace, tail=True), _read_bounded(trace),
                _read_bounded(tmp_path / "absent"))
    # Assert
    assert observed == ("x" * _LIMIT, "discard" + "x" * (_LIMIT - 7),
                        "unavailable: FileNotFoundError")


@pytest.mark.parametrize("code", [0, 7])
def test_real_exit_status_and_output_remain_visible(tmp_path, code):
    # Arrange
    command = [sys.executable, "-I", "-S", "-B", "-c",
               f"import sys; print('owned output'); sys.exit({code})"]
    # Act
    result = run_release_command(command, tmp_path, {}, text=True, check=False)
    # Assert
    assert (result.returncode, result.stdout, result.stderr) == (code, "owned output\n", "")


def test_check_true_retains_original_nonzero_exception(tmp_path):
    # Arrange
    command = [sys.executable, "-I", "-S", "-B", "-c", "raise SystemExit(7)"]
    # Act
    # Assert
    with pytest.raises(subprocess.CalledProcessError, match="exit status 7"):
        run_release_command(command, tmp_path, {}, check=True)


def test_live_timeout_evidence_excludes_existing_child_and_private_inputs(tmp_path):
    # Arrange
    environment = {"PATH": "/usr/bin:/bin", "PRIVATE_MARKER": "private-not-for-evidence"}
    unrelated = subprocess.Popen(
        [sys.executable, "-I", "-S", "-B", "-c", "import time;time.sleep(30)",
         "unrelated-private-argument"], cwd=tmp_path, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    command = [sys.executable, "-I", "-S", "-B", "-c",
               "import time;sum(i*i for i in range(2000000));time.sleep(30)"]
    observed = None
    # Act
    try:
        try:
            run_release_command(command, tmp_path, environment, check=True)
        except subprocess.TimeoutExpired as error:
            note = next(n for n in error.__notes__ if n.startswith(_NOTE_PREFIX))
            evidence = json.loads(note[len(_NOTE_PREFIX):])
            observation = evidence["owned_child_observation"]
            children = [r["child"] for r in observation["samples"]
                        if r["state"] == "observed"]
            observed = (
                error.timeout, bool(children), observation["collector_stopped"],
                all(c["pid"] != unrelated.pid and c["uid"] == os.getuid()
                    and c["parent_pid"] == os.getpid() for c in children),
                any(c["own_cpu_ticks"] > 0 for c in children),
                unrelated.poll() is None,
                "private-not-for-evidence" not in json.dumps(observation)
                and "unrelated-private-argument" not in json.dumps(observation),
            )
    finally:
        unrelated.kill()
        unrelated.wait(timeout=5)
    # Assert
    assert observed == (5, True, True, True, True, True, True)


def test_live_observation_missing_proc_is_unknown_and_stops_cleanly(tmp_path):
    # Arrange
    observation = OwnedChildObservation(tmp_path, proc_root=tmp_path / "absent")
    # Act
    observation.start()
    observation.close()
    result = observation.snapshot()
    # Assert
    assert (result["state"], result["reason"], result["samples"],
            result["collector_stopped"]) == ("unknown", "FileNotFoundError", [], True)


def test_live_observation_does_not_attribute_ambiguous_real_children(tmp_path):
    # Arrange
    observation = OwnedChildObservation(tmp_path)
    children = [subprocess.Popen(
        [sys.executable, "-I", "-S", "-B", "-c", "import time;time.sleep(30)"],
        cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) for _ in range(2)]
    # Act
    try:
        result = observation._sample()
    finally:
        for child in children:
            child.kill()
            child.wait(timeout=5)
    # Assert
    assert result == {"state": "unknown", "reason": "no unique candidate child in owned fixture"}


def test_missing_fixture_space_is_explicitly_unknown(tmp_path):
    # Arrange
    root = tmp_path / "owned"
    root.mkdir()
    observation = OwnedChildObservation(root)
    root.rmdir()
    # Act
    result = observation._fixture_filesystem()
    # Assert
    assert result == {"state": "unknown", "reason": "FileNotFoundError"}


def test_replaced_fixture_directory_refuses_space_attribution(tmp_path):
    # Arrange
    root = tmp_path / "owned"
    root.mkdir()
    observation = OwnedChildObservation(root)
    root.rename(tmp_path / "original")
    root.mkdir()
    # Act
    result = observation._fixture_filesystem()
    # Assert
    assert result == {"state": "unknown", "reason": "fixture directory identity changed"}
