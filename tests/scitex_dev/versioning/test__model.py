#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The tri-state model: UNKNOWN is in the TYPE and never renders as FRESH.

Non-negotiable #1. The empty-report case is the sharp edge — a report that
checked nothing must be UNKNOWN, because "nothing was checked" is exactly the
state this whole primitive exists to stop being read as good news.
"""

from __future__ import annotations

from scitex_dev.versioning._model import Currency, Finding, Report


def _f(state, check="c", **kw):
    return Finding(check=check, state=state, summary="s", **kw)


def test_three_states_exist():
    # Arrange
    expected = {Currency.FRESH, Currency.STALE, Currency.UNKNOWN}
    # Act
    actual = set(Currency)
    # Assert
    assert actual == expected


def test_empty_report_is_unknown_not_fresh():
    # Arrange
    report = Report()
    # Act
    state = report.state
    # Assert
    assert state is Currency.UNKNOWN


def test_any_stale_makes_report_stale():
    # Arrange
    report = Report(findings=(_f(Currency.FRESH), _f(Currency.STALE), _f(Currency.UNKNOWN)))
    # Act
    state = report.state
    # Assert
    assert state is Currency.STALE


def test_unknown_outranks_fresh():
    # Arrange
    report = Report(findings=(_f(Currency.FRESH), _f(Currency.UNKNOWN)))
    # Act
    state = report.state
    # Assert
    assert state is Currency.UNKNOWN


def test_all_fresh_is_fresh():
    # Arrange
    report = Report(findings=(_f(Currency.FRESH), _f(Currency.FRESH)))
    # Act
    state = report.state
    # Assert
    assert state is Currency.FRESH


def test_stale_property_excludes_unknown():
    # Arrange
    report = Report(findings=(_f(Currency.UNKNOWN), _f(Currency.STALE, check="x")))
    # Act
    actionable = [f.check for f in report.stale]
    # Assert
    assert actionable == ["x"]


def test_stale_finding_is_stale():
    # Arrange
    finding = _f(Currency.STALE)
    # Act
    result = finding.is_stale
    # Assert
    assert result is True


def test_unknown_finding_is_not_stale():
    # Arrange
    finding = _f(Currency.UNKNOWN)
    # Act
    result = finding.is_stale
    # Assert
    assert result is False


def test_report_round_trip_preserves_state():
    # Arrange
    report = Report(findings=(_f(Currency.STALE, remedy="git pull"),), generated_at=123.0)
    # Act
    restored = Report.from_dict(report.to_dict())
    # Assert
    assert restored.state is Currency.STALE


def test_report_round_trip_preserves_remedy():
    # Arrange
    report = Report(findings=(_f(Currency.STALE, remedy="git pull"),), generated_at=123.0)
    # Act
    restored = Report.from_dict(report.to_dict())
    # Assert
    assert restored.findings[0].remedy == "git pull"


def test_unrecognised_state_decays_to_unknown():
    # Arrange
    raw = {"check": "c", "state": "teleporting", "summary": "s"}
    # Act
    finding = Finding.from_dict(raw)
    # Assert
    assert finding.state is Currency.UNKNOWN


# EOF
