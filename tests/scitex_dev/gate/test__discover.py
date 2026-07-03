"""Tests for the gate-check federation discovery."""

from __future__ import annotations

from scitex_dev.gate import GateCheck, GateResult, discover_gate_checks
from scitex_dev.gate._discover import ENTRY_POINT_GROUP


def _ok(w, c):
    return GateResult(passed=True)


def test_entry_point_group_name_is_stable():
    # Arrange
    expected = "scitex_dev.gate.checks"
    # Act
    got = ENTRY_POINT_GROUP
    # Assert
    assert got == expected


def test_builtin_is_discovered_without_entry_points():
    # Arrange
    # Act
    ids = [c.id for c in discover_gate_checks(include_entry_points=False)]
    # Assert
    assert "gate-workdir-present" in ids


def test_include_builtins_false_drops_builtin():
    # Arrange
    # Act
    ids = [
        c.id
        for c in discover_gate_checks(
            include_entry_points=False, include_builtins=False
        )
    ]
    # Assert
    assert ids == []


def test_stage_filter_returns_only_that_stage():
    # Arrange
    def prov():
        return [GateCheck("post-x", "post-submission", _ok)]

    # Act
    pre = discover_gate_checks(
        "pre-submission", extra_providers=[prov], include_entry_points=False
    )
    # Assert
    assert "post-x" not in [c.id for c in pre]


def test_results_are_sorted_by_id():
    # Arrange
    def prov():
        return [
            GateCheck("zzz", "pre-submission", _ok),
            GateCheck("aaa", "pre-submission", _ok),
        ]

    # Act
    ids = [
        c.id
        for c in discover_gate_checks(
            "pre-submission",
            extra_providers=[prov],
            include_entry_points=False,
            include_builtins=False,
        )
    ]
    # Assert
    assert ids == ["aaa", "zzz"]


def test_duplicate_id_first_wins():
    # Arrange
    def first():
        return [GateCheck("dup", "pre-submission", _ok, description="first")]

    def second():
        return [GateCheck("dup", "pre-submission", _ok, description="second")]

    # Act
    checks = discover_gate_checks(
        "pre-submission",
        extra_providers=[first, second],
        include_entry_points=False,
        include_builtins=False,
    )
    # Assert
    assert [c.description for c in checks] == ["first"]


def test_a_raising_provider_is_skipped_not_fatal():
    # Arrange
    def boom():
        raise RuntimeError("bad provider")

    def ok():
        return [GateCheck("good", "pre-submission", _ok)]

    # Act
    ids = [
        c.id
        for c in discover_gate_checks(
            "pre-submission",
            extra_providers=[boom, ok],
            include_entry_points=False,
            include_builtins=False,
        )
    ]
    # Assert
    assert ids == ["good"]
