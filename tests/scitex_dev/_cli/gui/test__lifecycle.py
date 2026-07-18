#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tri-state `gui status` + the four canonical verbs.

No mocks and no monkeypatch (STX-NM): every case uses a real state
file, a real process, or a real listening socket. Isolation comes from
the production seam `$SCITEX_DEV_GUI_STATE`, set through a yield
fixture that restores the previous value on teardown.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._cli.gui._lifecycle import gui_state_path, probe_status
from scitex_dev.gui_runtime import GuiRuntime

_ENV_KEY = "SCITEX_DEV_GUI_STATE"


@pytest.fixture()
def state_file(tmp_path):
    """Point the GUI state file at a tmp path for the duration of a test."""
    previous = os.environ.get(_ENV_KEY)
    path = tmp_path / "runtime" / "gui.json"
    os.environ[_ENV_KEY] = str(path)
    yield path
    if previous is None:
        os.environ.pop(_ENV_KEY, None)
    else:
        os.environ[_ENV_KEY] = previous


@pytest.fixture()
def free_port():
    """A port number nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Socket is closed by here, which is the point: the port is free.
    yield port


@pytest.fixture()
def bound_port():
    """A port with a real listening socket held open for the test."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        yield server.getsockname()[1]


@pytest.fixture()
def loopback_probe_works():
    """Skip when the sandbox filters loopback SYNs.

    Some containers drop outbound SYNs to 127.0.0.1, so a connect to a
    closed port times out instead of being refused. `probe_status` then
    correctly reports UNKNOWN, and any test asserting a definite verdict
    is testing the network, not the code. Declared as a precondition
    rather than silently tolerated.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    try:
        socket.create_connection(("127.0.0.1", closed_port), timeout=1).close()
    except ConnectionRefusedError:
        pass
    except OSError:
        pytest.skip("sandbox filters loopback connections; port probe is blind here")
    else:
        pytest.skip("unexpected listener on a port we just closed")
    yield True


@pytest.fixture()
def flask_installed():
    """Skip when the dashboard's Flask dependency is not installed."""
    return pytest.importorskip("flask")


@pytest.fixture()
def sleeping_process():
    """A real, live child process to record in the state file."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    yield child
    if child.poll() is None:
        child.kill()
    child.wait(timeout=10)


@pytest.fixture()
def dead_pid():
    """The pid of a process that has already exited and been reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=10)
    return child.pid


def test_state_path_honours_the_env_override(state_file):
    # Arrange
    expected = state_file
    # Act
    resolved = gui_state_path()
    # Assert
    assert resolved == expected


def test_status_is_stopped_when_no_state_file_and_port_free(
    state_file, free_port, loopback_probe_works
):
    # Arrange: the `state_file` fixture guarantees a pristine, absent file
    del state_file
    # Act
    report = probe_status("127.0.0.1", free_port)
    # Assert
    assert report["state"] == "stopped"


def test_status_is_unknown_when_state_file_is_corrupt(state_file, free_port):
    # Arrange
    gui_state_path().write_text("not json {{{")
    # Act
    report = probe_status("127.0.0.1", free_port)
    # Assert
    assert report["state"] == "unknown"


def test_corrupt_state_file_reason_names_the_read_failure(state_file, free_port):
    # Arrange
    gui_state_path().write_text("not json {{{")
    # Act
    report = probe_status("127.0.0.1", free_port)
    # Assert
    assert "unreadable or malformed" in report["reason"]


def test_status_is_unknown_when_port_bound_by_a_foreign_server(
    state_file, bound_port, loopback_probe_works
):
    # Arrange: a listener that nothing recorded in the state file
    del state_file
    # Act
    report = probe_status("127.0.0.1", bound_port)
    # Assert
    assert report["state"] == "unknown"


def test_foreign_listener_is_distinguished_from_a_blind_probe(
    state_file, bound_port, loopback_probe_works
):
    """`open` refuses on a foreign listener but proceeds on a blind probe."""
    # Arrange
    del state_file
    # Act
    report = probe_status("127.0.0.1", bound_port)
    # Assert
    assert report["reason_code"] == "foreign-listener"


def test_status_is_running_for_a_live_recorded_pid(state_file, sleeping_process):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(sleeping_process.pid, 8050, "127.0.0.1")
    # Act
    report = probe_status("127.0.0.1", 8050)
    # Assert
    assert report["state"] == "running"


def test_running_status_reports_the_browsable_url(state_file, sleeping_process):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(sleeping_process.pid, 8050, "127.0.0.1")
    # Act
    report = probe_status("127.0.0.1", 8050)
    # Assert
    assert report["url"] == "http://127.0.0.1:8050"


def test_status_is_stopped_for_a_dead_recorded_pid(state_file, dead_pid, free_port):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(dead_pid, 8050, "127.0.0.1")
    # Act
    report = probe_status("127.0.0.1", free_port)
    # Assert
    assert report["state"] == "stopped"


def test_dead_recorded_pid_self_heals_the_state_file(state_file, dead_pid, free_port):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(dead_pid, 8050, "127.0.0.1")
    # Act
    probe_status("127.0.0.1", free_port)
    # Assert
    assert not gui_state_path().exists()


def test_stop_terminates_the_recorded_process(state_file, sleeping_process):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(sleeping_process.pid, 8050, "127.0.0.1")
    # Act
    CliRunner().invoke(main, ["gui", "stop", "--yes"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and sleeping_process.poll() is None:
        time.sleep(0.1)
    # Assert
    assert sleeping_process.poll() is not None


def test_stop_clears_the_state_file(state_file, sleeping_process):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(sleeping_process.pid, 8050, "127.0.0.1")
    # Act
    CliRunner().invoke(main, ["gui", "stop", "--yes"])
    # Assert
    assert not gui_state_path().exists()


def test_stop_is_idempotent_on_a_stopped_instance(state_file):
    # Arrange: the `state_file` fixture guarantees a pristine, absent file
    del state_file
    # Act
    result = CliRunner().invoke(main, ["gui", "stop", "--yes"])
    # Assert
    assert result.exit_code == 0


def test_stop_reports_nothing_to_stop_when_not_running(state_file):
    # Arrange: the `state_file` fixture guarantees a pristine, absent file
    del state_file
    # Act
    result = CliRunner().invoke(main, ["gui", "stop", "--yes"])
    # Assert
    assert "nothing to stop" in result.output


def test_stop_refuses_without_yes(state_file):
    # Arrange: the `state_file` fixture guarantees a pristine, absent file
    del state_file
    # Act
    result = CliRunner().invoke(main, ["gui", "stop"])
    # Assert
    assert result.exit_code == 2


def test_stop_dry_run_leaves_the_process_alive(state_file, sleeping_process):
    # Arrange
    GuiRuntime(gui_state_path()).write_state(sleeping_process.pid, 8050, "127.0.0.1")
    # Act
    CliRunner().invoke(main, ["gui", "stop", "--dry-run"])
    # Assert
    assert sleeping_process.poll() is None


def test_status_json_is_machine_readable(state_file, free_port, loopback_probe_works):
    # Arrange
    import json

    # Act
    result = CliRunner().invoke(
        main, ["gui", "status", "--json", "--port", str(free_port)]
    )
    # Assert
    assert json.loads(result.output)["state"] == "stopped"


def test_open_refuses_an_unknown_surface(state_file):
    # Arrange
    surface = "editor"
    # Act
    result = CliRunner().invoke(main, ["gui", "open", surface])
    # Assert
    assert "unknown surface" in result.output


def test_open_dry_run_starts_nothing(state_file):
    # Arrange: the `state_file` fixture guarantees a pristine, absent file
    del state_file
    # Act
    CliRunner().invoke(main, ["gui", "open", "--dry-run"])
    # Assert
    assert not gui_state_path().exists()


def test_serve_dry_run_starts_nothing(state_file):
    # Arrange: the `state_file` fixture guarantees a pristine, absent file
    del state_file
    # Act
    CliRunner().invoke(main, ["gui", "serve", "--dry-run", "--port", "9999"])
    # Assert
    assert not gui_state_path().exists()


def test_serve_clears_its_state_file_when_the_server_dies(
    state_file, bound_port, flask_installed
):
    # Arrange: the port is already taken, so the server dies on bind. Run
    # it in a child so the crash does not need catching here — the point
    # under test is the write/clear bracket, not the exception.
    child = [
        sys.executable,
        "-c",
        "from scitex_dev._cli.gui._lifecycle import run_server; "
        f"run_server('127.0.0.1', {bound_port})",
    ]
    # Act
    subprocess.run(child, capture_output=True, timeout=60)
    # Assert
    assert not state_file.exists()


def test_written_state_records_the_serving_pid(state_file):
    # Arrange
    runtime = GuiRuntime(gui_state_path())
    # Act
    runtime.write_state(os.getpid(), 8050, "0.0.0.0", surface="web")
    # Assert
    assert runtime.read_state()["pid"] == os.getpid()


def test_written_state_records_the_surface(state_file):
    # Arrange
    runtime = GuiRuntime(gui_state_path())
    # Act
    runtime.write_state(os.getpid(), 8050, "0.0.0.0", surface="web")
    # Assert
    assert runtime.read_state()["surface"] == "web"


# EOF
