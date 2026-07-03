"""Tests for the frozen GateCheck / GateResult / Finding contract."""

from __future__ import annotations

import pytest

from scitex_dev.gate import Finding, GateCheck, GateResult


def _ok(w, c):
    return GateResult(passed=True)


def test_finding_rejects_unknown_severity():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        Finding("id", "kind", "msg", severity="fatal")


def test_gatecheck_rejects_unknown_stage():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        GateCheck("id", "mid-submission", _ok)


def test_gatecheck_rejects_empty_id():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        GateCheck("", "pre-submission", _ok)


def test_gatecheck_rejects_non_callable_run():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        GateCheck("id", "pre-submission", run="not-callable")


def test_finding_defaults_to_error_severity():
    # Arrange
    # Act
    f = Finding("id", "kind", "msg")
    # Assert
    assert f.severity == "error"


def test_gateresult_defaults_to_no_findings():
    # Arrange
    # Act
    r = GateResult(passed=True)
    # Assert
    assert r.findings == ()
