#!/usr/bin/env python3
"""scitex-dev's OWN CLI must satisfy the §13 `dev`-group rule it ships.

The rule (``_cli/audit/_summary/_dev_group.py``) had been firing against
this package since it shipped, and that gap was not cosmetic: measured
2026-08-02, two peer agents independently concluded — from an adoption
count of zero, its author included — that the convention did not exist.
A rule whose owner violates it is indistinguishable from no rule.

So this file pins the compliance rather than the mechanism. It asserts
the checker's verdict on the real CLI tree, which is the same question
the fleet-wide audit asks of every other package.

Both halves of §13 are covered, because they are different surfaces that
happen to share a name:

* ``scitex-dev dev …``           scitex-dev's own upkeep, as a leaf.
* ``scitex-dev ecosystem dev …`` the federation across every installed
                                 package's ``dev``.

The alias assertions are not decoration. The old spellings live in
crontabs, unit files, shell scripts and agent prompts that cannot be
grepped from this repository, so a migration that quietly drops one is a
silent breakage — and, since the §13 finding disappears either way, the
audit alone cannot tell the two outcomes apart.

No mocks — the real CLI tree, the real checker.
"""

from __future__ import annotations

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli._root import main
from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._dev_group import check_dev_command_group


class TestOwnCliIsCompliant:
    def test_no_section_13_findings_against_our_own_cli(self):
        # Arrange
        out: list[Violation] = []
        # Act
        check_dev_command_group(main, "scitex-dev", out)
        # Assert — the message names each offender, so a regression here
        # says WHICH command drifted back to the top level.
        assert out == [], "§13 violations in scitex-dev's own CLI: " + ", ".join(
            v.command for v in out
        )


class TestSelfMaintenanceIsNested:
    @pytest.mark.parametrize("name", ["cron", "hooks", "skills", "secret"])
    def test_verb_is_mounted_under_dev(self, name: str):
        # Arrange
        dev = main.commands["dev"]
        # Act
        mounted = set(dev.commands)
        # Assert
        assert name in mounted


class TestEcosystemFederationIsNested:
    @pytest.mark.parametrize("name", ["cron", "systemd"])
    def test_federated_job_verb_is_mounted_under_ecosystem_dev(self, name: str):
        # Arrange
        ecosystem = main.commands["ecosystem"]
        # Act
        mounted = set(ecosystem.commands["dev"].commands)
        # Assert
        assert name in mounted


class TestOldSpellingsStillResolve:
    @pytest.mark.parametrize("name", ["cron", "hooks", "skills"])
    def test_top_level_old_name_still_resolves(self, name: str):
        # Arrange
        commands = main.commands
        # Act
        alias = commands.get(name)
        # Assert
        assert alias is not None

    @pytest.mark.parametrize("name", ["cron", "hooks", "skills"])
    def test_top_level_old_name_is_marked_as_an_alias(self, name: str):
        # Arrange — an UNMARKED leftover would be the un-migrated command
        # itself, which looks identical from the caller's side.
        commands = main.commands
        # Act
        marker = getattr(commands.get(name), "_deprecated_alias", None)
        # Assert
        assert marker is not None

    @pytest.mark.parametrize("name", ["cron", "systemd"])
    def test_ecosystem_old_name_still_resolves(self, name: str):
        # Arrange
        ecosystem = main.commands["ecosystem"]
        # Act
        alias = ecosystem.commands.get(name)
        # Assert
        assert alias is not None

    @pytest.mark.parametrize("name", ["cron", "systemd"])
    def test_ecosystem_old_name_is_marked_as_an_alias(self, name: str):
        # Arrange
        ecosystem = main.commands["ecosystem"]
        # Act
        marker = getattr(ecosystem.commands.get(name), "_deprecated_alias", None)
        # Assert
        assert marker is not None


class TestOneCanonicalDevGroup:
    def test_dev_group_carries_both_secret_and_migrated_verbs(self):
        """Guards the failure that a second builder would reintroduce.

        Two ``@main.group("dev")`` declarations both succeed; click's
        ``add_command`` is a dict assignment, so the later one silently
        replaces the earlier group and everything mounted on it. Measured
        here 2026-08-03: ``dev`` held ``secret`` alone, cron/hooks/skills
        gone, no error raised anywhere. Asserting that verbs from BOTH
        builders coexist is what detects it.
        """
        # Arrange
        dev = main.commands["dev"]
        # Act
        mounted = set(dev.commands)
        # Assert
        assert {"secret", "cron", "hooks", "skills"} <= mounted


# EOF
