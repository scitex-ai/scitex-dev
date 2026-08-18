#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end: the gate's own message must not lie about WHY it failed.

`test__audit_outcome.py` pins the classifier. This file pins the thing a
human actually reads — the `AssertionError` pytest prints — by running
`audit_all_for_package` against a REAL `scitex-dev` executable shimmed onto
PATH, exactly like `test__audit_conformance.py` does for `--path`.

PA-306 no-mocks: no `monkeypatch`, no patched `subprocess.run`. The shim is a
real script, invoked by the helper's real subprocess call, and the assertions
read the real exception text. A mocked validator here would prove only that
the mock returns what the test told it to.

The simulated could-not-run is `Error: No module named 'requests'` — the line
scitex-hub's CI carried from 2026-08-05, reported to every reader as
"audit-all reported violations".
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest


@pytest.fixture
def no_skip_audit_env():
    """Ensure SCITEX_DEV_SKIP_AUDIT is unset for the test, restore on exit."""
    saved = os.environ.pop("SCITEX_DEV_SKIP_AUDIT", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["SCITEX_DEV_SKIP_AUDIT"] = saved



def _shimmed_launcher(tmp_path: Path) -> list[str]:
    """The auditor these tests mean, named OUT LOUD.

    These tests used to select their auditor by planting a shim first on
    PATH — which worked only BECAUSE `audit_all_for_package` resolved
    through `shutil.which`. That resolution was the defect (sac, P1,
    2026-08-18: local and CI graded against different rule corpora with
    no code difference), and removing it necessarily removes the tests'
    smuggling route too.

    PATH is still shimmed by the fixtures, deliberately: if the helper
    ever consults it again, these tests keep working and the dedicated
    hostile-PATH test in `test__auditor_comes_from_the_env_under_test.py`
    is the one that fails. Naming the launcher here is the honest form —
    a test should say which binary it means rather than arrange for the
    environment to answer.
    """
    return [str(tmp_path / "bin" / "scitex-dev")]

@contextmanager
def _scitex_dev_that(tmp_path: Path, *, stdout: str, stderr: str, code: int):
    """Put a real `scitex-dev` first on PATH that prints and exits `code`."""
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(exist_ok=True)
    script = shim_dir / "scitex-dev"
    script.write_text(
        "#!/bin/sh\n"
        f"cat <<'STDOUT_EOF'\n{stdout}\nSTDOUT_EOF\n"
        f"cat >&2 <<'STDERR_EOF'\n{stderr}\nSTDERR_EOF\n"
        f"exit {code}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    saved = os.environ["PATH"]
    os.environ["PATH"] = f"{shim_dir}{os.pathsep}{saved}"
    try:
        yield
    finally:
        os.environ["PATH"] = saved


CRASH = "Error: No module named 'requests'"

FINDING = (
    "WARN:   [SK-704 §FM frontmatter-tags-missing] "
    "/repo/src/pkg/_skills/pkg/25_naming-conventions.md: missing `tags:` field"
)

TRACEBACK_THEN_FINDING = (
    "Traceback (most recent call last):\nERRO:   [SK-704 §FM] /repo/x.md: y"
)


def _raised_message(tmp_path, *, stdout="", stderr="", code=1, skip_rules=()) -> str:
    """Run the gate against a shim and return the AssertionError text.

    Fails the calling test if nothing was raised, so "it still fails" needs
    no second assertion of its own.
    """
    from scitex_dev.testing import audit_all_for_package

    with _scitex_dev_that(tmp_path, stdout=stdout, stderr=stderr, code=code):
        with pytest.raises(AssertionError) as excinfo:
            audit_all_for_package(
                "scitex-io",
                path=tmp_path,
                skip_rules=skip_rules,
                launcher=_shimmed_launcher(tmp_path),
            )
    return str(excinfo.value)


class TestASimulatedCouldNotRun:
    """A gate that cannot run must say so, not invent a violation."""

    def test_it_does_not_read_as_a_violation_report(self, no_skip_audit_env, tmp_path):
        # Arrange
        stderr = CRASH
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert "reported violations" not in message

    def test_it_says_could_not_run(self, no_skip_audit_env, tmp_path):
        # Arrange
        stderr = CRASH
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert "COULD NOT RUN" in message

    def test_it_quotes_the_underlying_error(self, no_skip_audit_env, tmp_path):
        # Arrange
        stderr = CRASH
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert CRASH in message

    def test_it_tells_the_reader_not_to_hunt_for_a_violation(
        self, no_skip_audit_env, tmp_path
    ):
        """The whole cost of the old wording was a search with no end."""
        # Arrange
        stderr = CRASH
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert "Do NOT go looking for a lint violation" in message

    def test_a_crash_on_stdout_is_found_too(self, no_skip_audit_env, tmp_path):
        """Auditors split themselves across both streams; so must the reader."""
        # Arrange
        stdout = CRASH
        # Act
        message = _raised_message(tmp_path, stdout=stdout)
        # Assert
        assert "COULD NOT RUN" in message

    def test_it_still_fails_the_test(self, no_skip_audit_env, tmp_path):
        """UNKNOWN is not a pass. Green-by-absence is the worse bug.

        `_raised_message` wraps `pytest.raises`, so reaching the assertion at
        all means an AssertionError was raised.
        """
        # Arrange
        stderr = CRASH
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert message


class TestSkipRulesCannotMaskACouldNotRun:
    """Declared deferrals must never swallow "the audit did not happen".

    Masking is keyed on rule ids and a crash line carries none, so no entry
    can MATCH one — but a crash line with no level word (a bare `Traceback
    (most recent call last):`) used to land in neither bucket, and the
    `if skipped and not non_skipped` downgrade then returned green.
    """

    def test_a_traceback_survives_a_matching_skip_rule(
        self, no_skip_audit_env, tmp_path
    ):
        # Arrange
        stderr = TRACEBACK_THEN_FINDING
        # Act
        message = _raised_message(tmp_path, stderr=stderr, skip_rules=("SK-704",))
        # Assert
        assert "COULD NOT RUN" in message


class TestAGenuineViolationKeepsItsWords:
    """The FAIL message must stay a FAIL message."""

    def test_a_findings_run_still_says_reported_violations(
        self, no_skip_audit_env, tmp_path
    ):
        # Arrange
        stderr = FINDING
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert "reported violations" in message

    def test_the_findings_are_digested_above_the_raw_dump(
        self, no_skip_audit_env, tmp_path
    ):
        """The five interesting lines were arriving buried in several hundred."""
        # Arrange
        stderr = FINDING
        # Act
        message = _raised_message(tmp_path, stderr=stderr)
        # Assert
        assert message.index("SK-704") < message.index("--- stdout ---")

    def test_a_clean_run_raises_nothing(self, no_skip_audit_env, tmp_path):
        # Arrange
        from scitex_dev.testing import audit_all_for_package

        raised = None
        # Act
        with _scitex_dev_that(
            tmp_path, stdout="SUCC: no violations", stderr="", code=0
        ):
            try:
                audit_all_for_package(
                    "scitex-io", path=tmp_path, launcher=_shimmed_launcher(tmp_path)
                )
            except AssertionError as exc:  # pragma: no cover - regression guard
                raised = exc
        # Assert
        assert raised is None


# EOF
