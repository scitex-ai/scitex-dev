"""Tests for the ``scitex-dev ecosystem ci why`` CLI verb.

No mocks. The group/help wiring is probed with Click's ``CliRunner``.
The end-to-end verb is driven against a REAL (fake) ``gh`` executable
placed on ``PATH`` — a tiny script emitting canned ``gh run view`` JSON
and ``--log-failed`` output — so the actual ``run_gh`` subprocess seam is
exercised without a network. AAA, one logical assertion per test.
"""

from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands

_JOB = "pytest-matrix-on-ubuntu-py3.11"

# A fake `gh`: emit run-view JSON on --json, job-prefixed --log-failed log.
_FAKE_GH = f'''#!/usr/bin/env python3
import sys, json
argv = sys.argv[1:]
JOB = "{_JOB}"
if "--log-failed" in argv:
    rows = [
        JOB + "\\tRun pytest\\t2026-07-15T10:00:02.0Z "
        "=========== short test summary info ===========",
        JOB + "\\tRun pytest\\t2026-07-15T10:00:02.1Z "
        "FAILED tests/test_x.py::test_y - AssertionError: assert 1 == 2",
        JOB + "\\tRun pytest\\t2026-07-15T10:00:02.2Z "
        "=========== 1 failed in 0.01s ===========",
    ]
    sys.stdout.write("\\n".join(rows) + "\\n")
elif "--json" in argv:
    sys.stdout.write(json.dumps({{
        "workflowName": "tests", "displayTitle": "t", "headBranch": "b",
        "url": "https://github.com/o/r/actions/runs/10000042",
        "jobs": [{{"name": JOB, "conclusion": "failure", "url": "https://x/1"}}],
    }}))
sys.exit(0)
'''

# A broken `gh`: always non-zero with empty stdout — an UNKNOWN, not green.
_BROKEN_GH = """#!/usr/bin/env python3
import sys
sys.stderr.write("gh: could not resolve\\n")
sys.exit(1)
"""


def _build_main():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return main


def _put_gh_on_path(tmp_path, script: str):
    """Write an executable fake ``gh`` and prepend its dir to PATH.

    Returns a ``restore()`` callable that puts PATH back — no pytest
    env-patching fixture (PA-306 forbids it), just real env save/restore.
    """
    gh = tmp_path / "gh"
    gh.write_text(script)
    gh.chmod(0o755)
    saved = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}{os.pathsep}{saved}"
    return lambda: os.environ.__setitem__("PATH", saved)


def test_ci_group_registered_under_ecosystem():
    # Arrange
    main = _build_main()
    # Act
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "ci", "--help"])
    # Assert
    assert result.exit_code == 0


def test_ci_why_help_documents_target():
    # Arrange
    main = _build_main()
    # Act
    runner = CliRunner()
    result = runner.invoke(main, ["ecosystem", "ci", "why", "--help"])
    # Assert
    assert "TARGET" in result.output


def test_ci_why_extracts_failing_test_from_fake_gh(tmp_path):
    # Arrange
    restore = _put_gh_on_path(tmp_path, _FAKE_GH)
    main = _build_main()
    # Act
    try:
        result = CliRunner().invoke(main, ["ecosystem", "ci", "why", "10000042"])
    finally:
        restore()
    # Assert
    assert "tests/test_x.py::test_y" in result.output


def test_ci_why_exits_1_when_failures_found(tmp_path):
    # Arrange
    restore = _put_gh_on_path(tmp_path, _FAKE_GH)
    main = _build_main()
    # Act
    try:
        result = CliRunner().invoke(main, ["ecosystem", "ci", "why", "10000042"])
    finally:
        restore()
    # Assert
    assert result.exit_code == 1


def test_ci_why_json_emits_failed_tests(tmp_path):
    # Arrange
    restore = _put_gh_on_path(tmp_path, _FAKE_GH)
    main = _build_main()
    # Act
    try:
        result = CliRunner().invoke(
            main, ["ecosystem", "ci", "why", "10000042", "--json"]
        )
    finally:
        restore()
    # Assert
    assert json.loads(result.output)[0]["failures"][0]["failed_tests"]


def test_ci_why_exits_2_when_gh_cannot_read(tmp_path):
    # Arrange — a broken gh is UNKNOWN; it must never read as green (exit 0).
    restore = _put_gh_on_path(tmp_path, _BROKEN_GH)
    main = _build_main()
    # Act
    try:
        result = CliRunner().invoke(main, ["ecosystem", "ci", "why", "10000042"])
    finally:
        restore()
    # Assert
    assert result.exit_code == 2
