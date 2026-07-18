"""Tests for ``scitex-dev trace-env-vars`` — CLI surface (click wiring).

Keeps only the CLI-surface tests that drive the ``trace-env-vars`` click
command through ``CliRunner``: exit code, ``--json`` output shape, the quiet
one-line summary, and the dynamic ``--trace`` passthrough split.

The engine-level suites live alongside their src modules under
``tests/scitex_dev/trace_env/`` — ``test_config.py`` (matching + redaction),
``test_scan.py`` (static scan), ``test_trace.py`` (strace tracer).

Env-dependent CLI tests use a yield-based fixture that mutates the real
environment and restores it on teardown (no ``monkeypatch``, per the
ecosystem NM002 rule).
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli._root import main


# --------------------------------------------------------------------
# Fixture — real-environment mutation with restore-on-teardown.
# --------------------------------------------------------------------


@pytest.fixture
def cli_var():
    # Arrange: set a real env var, restore on teardown.
    key = "MY_CLI_TRACE_VAR"
    prior = os.environ.get(key)
    os.environ[key] = "v1"
    yield key
    if prior is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = prior


# --------------------------------------------------------------------
# CLI wiring + --json output shape.
# --------------------------------------------------------------------


def test_cli_scan_exit_code_zero(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux"]
    )
    # Assert
    assert result.exit_code == 0, result.output


def test_cli_scan_mentions_var(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux"]
    )
    # Assert
    assert cli_var in result.output


def test_cli_json_mode_field(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "--json"]
    )
    # Assert
    assert json.loads(result.output)["mode"] == "scan"


def test_cli_json_variable_name(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "--json"]
    )
    # Assert
    assert json.loads(result.output)["variables"][0]["name"] == cli_var


def test_cli_json_currently_set(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "--json"]
    )
    # Assert
    assert json.loads(result.output)["variables"][0]["currently_set"] is True


def test_cli_quiet_one_line_summary(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "-q"]
    )
    # Assert
    assert result.output.startswith("scan:")


# --------------------------------------------------------------------
# Dynamic trace (--trace) — CLI passthrough split + exec-stage locate.
# Skipped where strace is unavailable (e.g. some CI runners).
# --------------------------------------------------------------------


_NEEDS_STRACE = pytest.mark.skipif(
    shutil.which("strace") is None, reason="strace not installed"
)


@_NEEDS_STRACE
def test_cli_trace_locates_var_injected_at_inner_exec_stage():
    # Arrange: `sh -c` injects TRACE_ME then execs `env true`, so the
    # var first appears at the inner exec — the command tokens after
    # `--` must be split off from the traced NAME.
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main,
        [
            "trace-env-vars",
            "TRACE_ME_XYZ",
            "--trace",
            "--json",
            "--",
            "sh",
            "-c",
            "TRACE_ME_XYZ=injected exec env true",
        ],
    )
    # Assert
    assert json.loads(result.output)["trace_hits"], result.output


@_NEEDS_STRACE
def test_cli_trace_splits_command_from_names():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main,
        [
            "trace-env-vars",
            "TRACE_ME_XYZ",
            "--trace",
            "--json",
            "--",
            "sh",
            "-c",
            "TRACE_ME_XYZ=injected exec env true",
        ],
    )
    # Assert
    assert [v["name"] for v in json.loads(result.output)["variables"]] == [
        "TRACE_ME_XYZ"
    ]


# EOF
