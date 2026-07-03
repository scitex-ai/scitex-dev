"""Tests for scitex-dev's built-in gate check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from scitex_dev.gate._builtin import BUILTIN_CHECKS, provide


def test_provide_returns_the_builtin_checks():
    # Arrange
    # Act
    checks = provide()
    # Assert
    assert [c.id for c in checks] == ["gate-workdir-present"]


def test_builtin_check_is_pre_submission_stage():
    # Arrange
    check = BUILTIN_CHECKS[0]
    # Act
    stage = check.stage
    # Assert
    assert stage == "pre-submission"


def test_builtin_passes_for_existing_dir():
    # Arrange
    check = BUILTIN_CHECKS[0]
    with tempfile.TemporaryDirectory() as td:
        # Act
        result = check.run(Path(td), {})
        # Assert
        assert result.passed is True


def test_builtin_fails_with_fix_hint_for_missing_dir():
    # Arrange
    check = BUILTIN_CHECKS[0]
    # Act
    result = check.run(Path("/no/such/dir"), {})
    # Assert
    assert result.passed is False and result.findings[0].fix_hint != ""
