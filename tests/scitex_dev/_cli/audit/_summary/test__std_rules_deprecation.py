#!/usr/bin/env python3
"""Tests for the slice-4 §5 deprecation-ladder auditor upgrades.

Two halves (split out of `test__std_rules.py` to keep each test module
under the 512-line cap):

* Static `_deprecated_alias` metadata verification
  (`check_deprecated_alias_metadata`): the target must exist in the
  command tree and `remove_in` must be set.
* Phase-aware behavioral assessment (`assess_hidden_leaf`, pure
  decision logic over (exit code, stderr, metadata)): phase="warn"
  aliases MUST exit 0 AND print 'deprecated' on stderr; phase="error"
  MUST exit 2; metadata-less hidden leaves keep the legacy expectation
  (non-zero + redirect hint on stderr).

No mocks — real click trees and real `deprecated_alias` registrations;
the behavioral half feeds the pure function real (rc, stderr) values.
"""

from __future__ import annotations

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._std_rules import (
    assess_hidden_leaf,
    check_deprecated_alias_metadata,
)
from scitex_dev._ecosystem.click_compat import deprecated_alias


# --------------------------------------------------------------------------- #
# §5 — static `_deprecated_alias` metadata verification                         #
# --------------------------------------------------------------------------- #


class TestDeprecatedAliasStaticMetadata:
    def test_wellformed_warn_alias_passes_static_check(self):
        # Arrange — real registration via the shared helper.
        @click.group()
        def root():
            pass

        @root.command("status")
        def status_cmd():
            pass

        deprecated_alias(root, "show-status", target="status", remove_in="0.30")
        out: list[Violation] = []
        # Act
        check_deprecated_alias_metadata(root, "demo", out)
        # Assert
        assert out == []

    def test_alias_target_in_nested_group_passes(self):
        # Arrange — target lives under a noun group; metadata names the
        # multi-word path resolved from root.
        @click.group()
        def root():
            pass

        @root.group("card")
        def card_group():
            pass

        @card_group.command("status")
        def card_status_cmd():
            pass

        deprecated_alias(
            root,
            "show-status",
            target="status",
            remove_in="0.30",
            target_name="card status",
        )
        out: list[Violation] = []
        # Act
        check_deprecated_alias_metadata(root, "demo", out)
        # Assert
        assert out == []

    def test_alias_with_missing_target_is_flagged(self):
        # Arrange — string target never registered anywhere in the tree.
        @click.group()
        def root():
            pass

        deprecated_alias(
            root, "old-thing", target="definitely-not-registered", remove_in="0.30"
        )
        out: list[Violation] = []
        # Act
        check_deprecated_alias_metadata(root, "demo", out)
        # Assert
        assert any(
            v.rule == "§5" and "not found in" in v.message and "old-thing" in v.command
            for v in out
        )

    def test_alias_with_empty_remove_in_is_flagged(self):
        # Arrange — metadata shape produced by a mis-wired caller; a real
        # hidden command carrying the attribute the helper would set.
        @click.group()
        def root():
            pass

        @root.command("status")
        def status_cmd():
            pass

        alias = click.Command("show-status", callback=lambda: None, hidden=True)
        alias._deprecated_alias = {"target": "status", "remove_in": "", "phase": "warn"}
        root.add_command(alias)
        out: list[Violation] = []
        # Act
        check_deprecated_alias_metadata(root, "demo", out)
        # Assert
        assert any(v.rule == "§5" and "remove_in" in v.message for v in out)


# --------------------------------------------------------------------------- #
# §5 — phase-aware behavioral assessment (pure decision logic)                 #
# --------------------------------------------------------------------------- #


def _warn_meta() -> dict:
    return {"target": "status", "remove_in": "0.30", "phase": "warn"}


def _error_meta() -> dict:
    return {"target": "status", "remove_in": "0.30", "phase": "error"}


class TestAssessHiddenLeafWarnPhase:
    def test_warn_phase_exit_zero_with_deprecated_stderr_passes(self):
        # Arrange — the doctrine-format Phase W behavior.
        stderr = "'show-status' is deprecated — use 'status' (removed in v0.30)\n"
        # Act
        findings = assess_hidden_leaf("demo show-status", 0, stderr, _warn_meta())
        # Assert
        assert findings == []

    def test_warn_phase_nonzero_exit_is_flagged(self):
        # Arrange — Phase W must forward and exit 0.
        stderr = "'show-status' is deprecated — use 'status' (removed in v0.30)\n"
        # Act
        findings = assess_hidden_leaf("demo show-status", 2, stderr, _warn_meta())
        # Assert
        assert any("exited 2" in f.message for f in findings)

    def test_warn_phase_missing_deprecated_warning_is_flagged(self):
        # Arrange — forwards fine but stays silent.
        silent_stderr = ""
        # Act
        findings = assess_hidden_leaf("demo show-status", 0, silent_stderr, _warn_meta())
        # Assert
        assert any("'deprecated'" in f.message for f in findings)

    def test_warn_phase_subprocess_failure_yields_no_finding(self):
        # Arrange — rc == -1 is "binary unrunnable", not ladder evidence.
        unrunnable_rc = -1
        # Act
        findings = assess_hidden_leaf("demo show-status", unrunnable_rc, "", _warn_meta())
        # Assert
        assert findings == []


class TestAssessHiddenLeafErrorPhase:
    def test_error_phase_exit_two_passes(self):
        # Arrange — Phase E hard redirect.
        stderr = "error: `demo show-status` was renamed to `demo status`.\n"
        # Act
        findings = assess_hidden_leaf("demo show-status", 2, stderr, _error_meta())
        # Assert
        assert findings == []

    def test_error_phase_exit_zero_is_flagged(self):
        # Arrange — an error-phase alias must NOT succeed.
        succeeded_rc = 0
        # Act
        findings = assess_hidden_leaf("demo show-status", succeeded_rc, "", _error_meta())
        # Assert
        assert any("expected 2" in f.message for f in findings)


class TestAssessHiddenLeafLegacyExpectation:
    """Metadata-less hidden leaves keep today's contract exactly."""

    def test_unmetadata_hidden_leaf_exit_zero_is_flagged(self):
        # Arrange — legacy expectation: non-zero redirect.
        no_metadata = None
        # Act
        findings = assess_hidden_leaf("demo old-cmd", 0, "", no_metadata)
        # Assert
        assert any("exited 0" in f.message for f in findings)

    def test_unmetadata_hidden_leaf_redirect_hint_passes(self):
        # Arrange
        stderr = "error: `demo old-cmd` was renamed to `demo new-cmd`.\n"
        # Act
        findings = assess_hidden_leaf("demo old-cmd", 2, stderr, None)
        # Assert
        assert findings == []

    def test_unmetadata_hidden_leaf_missing_hint_is_flagged(self):
        # Arrange — non-zero but unhelpful stderr.
        unhelpful_stderr = "boom\n"
        # Act
        findings = assess_hidden_leaf("demo old-cmd", 2, unhelpful_stderr, None)
        # Assert
        assert any("redirect hint" in f.message for f in findings)

    def test_unknown_phase_metadata_is_flagged(self):
        # Arrange — corrupt metadata must fail loud, not fall through.
        meta = {"target": "status", "remove_in": "0.30", "phase": "removed"}
        # Act
        findings = assess_hidden_leaf("demo old-cmd", 0, "", meta)
        # Assert
        assert any("unknown phase" in f.message for f in findings)
