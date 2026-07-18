#!/usr/bin/env python3
"""Tests for the audit-cli baseline ratchet (`_baseline`).

The ratchet records today's violation fingerprints once; later runs
suppress the recorded ones and fail/warn only on NEW violations.
Fingerprints are stable keys: rule id + command path + the
message-invariant part (digit runs normalized, whitespace collapsed,
truncated) so counts/timings churning between runs don't break the
match.

No mocks — real Violation dataclasses, real files under tmp_path.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("click")

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._baseline import (
    DEFAULT_BASELINE_RELPATH,
    fingerprint_violation,
    load_baseline,
    partition_violations,
    resolve_baseline_path,
    write_baseline,
)


@pytest.fixture
def cwd_sandbox(tmp_path):
    """Sandboxed cwd so the default baseline path resolves under tmp_path."""
    saved_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(saved_cwd)


# --------------------------------------------------------------------------- #
# Fingerprint stability                                                        #
# --------------------------------------------------------------------------- #


class TestFingerprintKeying:
    def test_fingerprint_contains_rule_and_command_path(self):
        # Arrange
        violation = Violation("demo card list", "§2", "read verb missing --json")
        # Act
        fp = fingerprint_violation(violation)
        # Assert — the stable key is rule|command|invariant-message.
        assert fp.startswith("§2|demo card list|")

    def test_digit_churn_yields_identical_fingerprint(self):
        # Arrange — same finding, different measured numbers.
        slow_run = Violation("demo", "§10", "`import demo` adds 812ms over baseline")
        slower_run = Violation("demo", "§10", "`import demo` adds 1204ms over baseline")
        # Act
        fingerprints = {fingerprint_violation(slow_run), fingerprint_violation(slower_run)}
        # Assert
        assert len(fingerprints) == 1

    def test_different_rule_yields_different_fingerprint(self):
        # Arrange — identical command + message, different rule id.
        first = Violation("demo card list", "§2", "same message")
        second = Violation("demo card list", "§4", "same message")
        # Act
        fingerprints = {fingerprint_violation(first), fingerprint_violation(second)}
        # Assert
        assert len(fingerprints) == 2

    def test_different_command_path_yields_different_fingerprint(self):
        # Arrange
        first = Violation("demo card list", "§2", "same message")
        second = Violation("demo card get", "§2", "same message")
        # Act
        fingerprints = {fingerprint_violation(first), fingerprint_violation(second)}
        # Assert
        assert len(fingerprints) == 2


# --------------------------------------------------------------------------- #
# Store round-trip                                                             #
# --------------------------------------------------------------------------- #


class TestBaselineStoreRoundTrip:
    def test_write_then_load_returns_recorded_fingerprints(self, tmp_path):
        # Arrange
        path = tmp_path / "cli-audit-baseline.yaml"
        violations = [
            Violation("demo card list", "§2", "read verb missing --json"),
            Violation("demo", "§4b", "help is free-form text"),
        ]
        write_baseline(path, violations)
        # Act
        loaded = load_baseline(path)
        # Assert
        assert loaded == {fingerprint_violation(v) for v in violations}

    def test_write_returns_deduplicated_count(self, tmp_path):
        # Arrange — two violations collapsing to one fingerprint.
        path = tmp_path / "cli-audit-baseline.yaml"
        violations = [
            Violation("demo", "§10", "adds 812ms over baseline"),
            Violation("demo", "§10", "adds 1204ms over baseline"),
        ]
        # Act
        n_written = write_baseline(path, violations)
        # Assert
        assert n_written == 1

    def test_write_creates_parent_directories(self, tmp_path):
        # Arrange — the default location nests under .scitex/dev/.
        path = tmp_path / ".scitex" / "dev" / "cli-audit-baseline.yaml"
        # Act
        write_baseline(path, [Violation("demo", "§2", "x")])
        # Assert
        assert path.is_file()

    def test_load_malformed_baseline_raises_value_error(self, tmp_path):
        # Arrange — a corrupt baseline must fail loud, never silently
        # suppress nothing/everything.
        path = tmp_path / "cli-audit-baseline.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        # Act
        raised = pytest.raises(ValueError)
        # Assert
        with raised:
            load_baseline(path)


# --------------------------------------------------------------------------- #
# Partition — old suppressed, new flagged                                      #
# --------------------------------------------------------------------------- #


class TestPartitionAgainstBaseline:
    def test_recorded_violation_is_suppressed(self, tmp_path):
        # Arrange — baseline holds yesterday's finding.
        old = Violation("demo card list", "§2", "read verb missing --json")
        path = tmp_path / "baseline.yaml"
        write_baseline(path, [old])
        baseline = load_baseline(path)
        # Act
        _new, suppressed = partition_violations([old], baseline)
        # Assert
        assert suppressed == [old]

    def test_new_violation_is_kept(self, tmp_path):
        # Arrange — baseline holds one finding; a fresh one appears.
        old = Violation("demo card list", "§2", "read verb missing --json")
        fresh = Violation("demo card delete", "§2", "mutating verb missing --dry-run")
        path = tmp_path / "baseline.yaml"
        write_baseline(path, [old])
        baseline = load_baseline(path)
        # Act
        new, _suppressed = partition_violations([old, fresh], baseline)
        # Assert
        assert new == [fresh]

    def test_digit_churned_recurrence_is_still_suppressed(self, tmp_path):
        # Arrange — the recorded §10 timing recurs with a different number.
        recorded = Violation("demo", "§10", "adds 812ms over baseline")
        recurrence = Violation("demo", "§10", "adds 1204ms over baseline")
        path = tmp_path / "baseline.yaml"
        write_baseline(path, [recorded])
        baseline = load_baseline(path)
        # Act
        new, _suppressed = partition_violations([recurrence], baseline)
        # Assert
        assert new == []


# --------------------------------------------------------------------------- #
# Path resolution                                                              #
# --------------------------------------------------------------------------- #


class TestBaselinePathResolution:
    def test_explicit_path_wins(self, tmp_path):
        # Arrange
        explicit = tmp_path / "custom-baseline.yaml"
        # Act
        resolved = resolve_baseline_path(str(explicit))
        # Assert
        assert resolved == explicit

    def test_default_resolves_under_cwd(self, cwd_sandbox):
        # Arrange
        expected = cwd_sandbox / DEFAULT_BASELINE_RELPATH
        # Act
        resolved = resolve_baseline_path(None)
        # Assert
        assert resolved == expected
