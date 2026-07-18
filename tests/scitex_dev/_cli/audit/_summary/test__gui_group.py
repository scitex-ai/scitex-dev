#!/usr/bin/env python3
"""Tests for the §12 canonical `gui` command-group audit rule.

Covers both sub-checks of `check_gui_command_group`:

* (a) legacy/flat gui-adjacent leaves (`gui`, `board`, `dashboard`,
  `start-gui`, ...) are flagged UNLESS already a properly-deprecated
  Phase W/E alias (hidden + `_deprecated_alias` metadata).
* (b) a `gui` GROUP is checked for the four required verbs
  (open/serve/status/stop); a hidden `gui` group is not checked.

No mocks — real click trees, real `deprecated_alias` registrations.
"""

from __future__ import annotations

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._gui_group import check_gui_command_group
from scitex_dev._ecosystem.click_compat import deprecated_alias


def _canonical_gui_group(root, verbs=("open", "serve", "status", "stop")):
    """Attach a `gui` group with the given verbs registered as no-op leaves."""

    @root.group("gui")
    def gui_group():
        pass

    for verb in verbs:
        gui_group.command(verb)(lambda: None)
    return gui_group


class TestLegacyLeafDetection:
    def test_bare_gui_leaf_with_no_deprecation_metadata_is_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("gui")
        def gui_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any(v.rule == "§12" and v.command == "demo gui" for v in out)

    def test_bare_board_leaf_with_no_deprecation_metadata_is_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("board")
        def board_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any(v.rule == "§12" and v.command == "demo board" for v in out)

    def test_start_gui_compound_leaf_is_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("start-gui")
        def start_gui_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any(v.rule == "§12" and v.command == "demo start-gui" for v in out)

    def test_dashboard_leaf_nested_under_another_group_is_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.group("admin")
        def admin_group():
            pass

        @admin_group.command("dashboard")
        def dashboard_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any(
            v.rule == "§12" and v.command == "demo admin dashboard" for v in out
        )

    def test_a_properly_deprecated_warn_alias_is_not_flagged(self):
        # Arrange — Phase W: hidden alias forwarding to `gui open`.
        @click.group()
        def root():
            pass

        _canonical_gui_group(root)
        deprecated_alias(root, "board", target="gui open", remove_in="0.30")
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert not any(v.command == "demo board" for v in out)

    def test_a_properly_deprecated_error_alias_is_not_flagged(self):
        # Arrange — Phase E: hidden redirect, still counts as migrated.
        @click.group()
        def root():
            pass

        _canonical_gui_group(root)
        deprecated_alias(
            root, "dashboard", target="gui open", remove_in="0.30", phase="error"
        )
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert not any(v.command == "demo dashboard" for v in out)

    def test_a_hidden_leaf_without_deprecation_metadata_is_still_flagged(self):
        # Arrange — hidden alone (no `_deprecated_alias` attribute) does
        # not count as a properly-migrated alias.
        @click.group()
        def root():
            pass

        root.add_command(click.Command("board", callback=lambda: None, hidden=True))
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any(v.command == "demo board" for v in out)

    def test_an_unrelated_command_name_produces_no_finding(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("status")
        def status_cmd():
            pass

        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert out == []


class TestGuiGroupVerbCoverage:
    def test_gui_group_with_all_four_verbs_produces_no_finding(self):
        # Arrange
        @click.group()
        def root():
            pass

        _canonical_gui_group(root)
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert out == []

    def test_gui_group_missing_stop_verb_is_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        _canonical_gui_group(root, verbs=("open", "serve", "status"))
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any(
            v.rule == "§12" and v.command == "demo gui" and "stop" in v.message
            for v in out
        )

    def test_gui_group_missing_verb_message_names_the_missing_verb(self):
        # Arrange
        @click.group()
        def root():
            pass

        _canonical_gui_group(root, verbs=("serve", "status", "stop"))
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert any("open" in v.message for v in out if v.command == "demo gui")

    def test_hidden_gui_group_is_not_checked_for_verb_coverage(self):
        # Arrange — an internal/hidden gui group shouldn't be audited.
        @click.group()
        def root():
            pass

        @root.group("gui", hidden=True)
        def gui_group():
            pass

        gui_group.command("open")(lambda: None)
        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert out == []


class TestNonGroupRoot:
    def test_a_non_group_root_command_produces_no_finding(self):
        # Arrange
        @click.command()
        def root():
            pass

        out: list[Violation] = []
        # Act
        check_gui_command_group(root, "demo", out)
        # Assert
        assert out == []


# EOF
