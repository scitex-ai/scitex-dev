#!/usr/bin/env python3
# Timestamp: 2026-07-29
# File: tests/develop/test__inert_ini_guard.py

"""A declared ini setting that nothing implements must fail the run.

`[tool.pytest.ini_options]` accepts any key. When no installed plugin
registers it, pytest warns `Unknown config option` and carries on — the
setting is inert and the run is indistinguishable from one where it
applied.

`timeout` is the key with the stake: pytest-timeout lives in `[dev]`, so
a venv installed without it runs this suite with NO per-test cap.
Measured 2026-07-29 by scitex-hpc on a live host running this suite —
`pytest_timeout spec: ABSENT`, third-party plugins empty — so the guard
whose comment promises a hung test "fails loud + names itself in ~5 min"
was doing nothing there, and had been since 2026-06-16 (#206).

Verified by SUBPROCESS rather than by calling the hook: the defect is a
property of a pytest session's startup, and a unit call would assert
that the function I wrote does what I wrote it to do while proving
nothing about whether a real run fails. `-p no:timeout` reproduces the
plugin-absent venv without uninstalling anything (no mocks — the plugin
really is not loaded).
"""

import subprocess
import sys
from pathlib import Path

# Lives under tests/develop/ with the other repo-level meta tests (PS-203
# forbids a loose top-level test, and this one has no src module to mirror
# — it exercises tests/conftest.py's session guard).
_REPO_ROOT = Path(__file__).resolve().parents[2]
# A fast, self-contained target — this test only cares about startup.
_TARGET = "tests/scitex_dev/_cli/audit/test__diff_fail_open.py"


def _run(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", _TARGET, "-q", "-p", "no:cacheprovider", *extra],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={**__import__("os").environ, "SCITEX_DEV_ALLOW_PARTIAL_RUN": "1"},
    )


def test_a_run_without_the_timeout_plugin_fails():
    # Arrange — `-p no:timeout` is a venv with pytest-timeout absent.
    # Act
    result = _run("-p", "no:timeout")
    # Assert
    assert result.returncode != 0


def test_the_failure_names_the_inert_setting():
    # Arrange
    # Act
    result = _run("-p", "no:timeout")
    # Assert — an error that only says "something is wrong" is half-written.
    assert "timeout" in (result.stdout + result.stderr)


def test_the_failure_names_the_missing_provider():
    # Arrange
    # Act
    result = _run("-p", "no:timeout")
    # Assert
    assert "pytest-timeout" in (result.stdout + result.stderr)


def test_the_failure_states_the_consequence():
    # Arrange
    # Act
    result = _run("-p", "no:timeout")
    # Assert — the reader must learn what they LOSE, not just what is unset.
    assert "NO PER-TEST CAP" in (result.stdout + result.stderr)


def test_a_run_with_the_plugin_present_is_unaffected():
    # Arrange — the guard must not be able to fail a healthy run; a gate
    # that cannot pass is as broken as one that cannot fail.
    # Act
    result = _run()
    # Assert
    assert result.returncode == 0
