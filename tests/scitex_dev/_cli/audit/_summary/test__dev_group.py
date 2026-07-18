#!/usr/bin/env python3
"""Tests for the §13 canonical `dev` command-group audit rule.

Covers `check_dev_command_group`:

* a self-maintenance leaf (`cron`, `daemon`, ...) at the CLI top level is
  flagged §13;
* the same leaf nested under a `dev` group is NOT flagged;
* a hidden leaf carrying `_deprecated_alias` metadata (a properly
  migrated Phase W/E alias) is NOT flagged;
* a group with no self-maintenance commands produces no §13 finding.

No mocks — real click trees, real `deprecated_alias` registrations.
"""

from __future__ import annotations

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._dev_group import check_dev_command_group
from scitex_dev._ecosystem.click_compat import deprecated_alias


class TestTopLevelDetection:
    def test_top_level_cron_leaf_is_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("cron")
        def cron_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
        # Assert
        assert any(v.rule == "§13" and v.command == "demo cron" for v in out)

    def test_top_level_daemon_group_is_flagged(self):
        # Arrange — a self-maintenance GROUP at top level is still flagged.
        @click.group()
        def root():
            pass

        @root.group("daemon")
        def daemon_group():
            pass

        daemon_group.command("start")(lambda: None)
        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
        # Assert
        assert any(v.rule == "§13" and v.command == "demo daemon" for v in out)


class TestNestedUnderDev:
    def test_cron_nested_under_dev_group_is_not_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.group("dev")
        def dev_group():
            pass

        @dev_group.command("cron")
        def cron_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
        # Assert
        assert out == []

    def test_deeply_nested_under_dev_group_is_not_flagged(self):
        # Arrange — `dev cron install`: the `dev` ancestor exempts the
        # whole subtree, so even an inner `hooks` leaf is fine.
        @click.group()
        def root():
            pass

        @root.group("dev")
        def dev_group():
            pass

        @dev_group.group("cron")
        def cron_group():
            pass

        @cron_group.command("hooks")
        def hooks_leaf():
            pass

        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
        # Assert
        assert out == []


class TestDeprecatedAliasEscapeHatch:
    def test_hidden_deprecated_alias_at_top_level_is_not_flagged(self):
        # Arrange — Phase W: hidden alias forwarding to `dev cron`.
        @click.group()
        def root():
            pass

        @root.group("dev")
        def dev_group():
            pass

        @dev_group.command("cron")
        def cron_leaf():
            pass

        deprecated_alias(root, "cron", target="dev cron", remove_in="0.40")
        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
        # Assert
        assert not any(v.command == "demo cron" for v in out)

    def test_hidden_leaf_without_metadata_is_still_flagged(self):
        # Arrange — hidden alone (no `_deprecated_alias`) does not count.
        @click.group()
        def root():
            pass

        root.add_command(
            click.Command("cron", callback=lambda: None, hidden=True)
        )
        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
        # Assert
        assert any(v.command == "demo cron" for v in out)


class TestNoSelfMaintenanceCommands:
    def test_group_without_self_maintenance_commands_has_no_finding(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("status")
        def status_cmd():
            pass

        @root.command("list")
        def list_cmd():
            pass

        out: list[Violation] = []
        # Act
        check_dev_command_group(root, "demo", out)
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
        check_dev_command_group(root, "demo", out)
        # Assert
        assert out == []


# EOF
