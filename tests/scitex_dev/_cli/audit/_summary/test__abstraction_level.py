#!/usr/bin/env python3
"""Tests for the §13a abstraction-level audit rule.

Covers `check_cli_abstraction_level`:

* an INTENT name (`daemon`, `service`) beside a MECHANISM name (`cron`,
  `systemd`, `timer`) under one parent is flagged §13a, once, on the
  PARENT;
* a mechanism name with no intent sibling is NOT flagged — `dev cron`
  meaning "manage my crontab entries" is a legitimate group;
* two mechanism names together are NOT flagged (same level as each
  other);
* an intent and a mechanism in different groups are NOT flagged;
* a hidden Phase W alias does not put a mechanism on the menu;
* the same group object mounted twice yields ONE finding.

The last class is the honest test of the rule: it runs the checker
against scitex-dev's OWN real CLI tree. A rule that cannot fire against
a real command tree is not a rule.

No mocks — real click trees, real `deprecated_alias` registrations, and
the real `scitex_dev._cli._root.main`.
"""

from __future__ import annotations

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary._abstraction_level import (
    AXIS_FAMILIES,
    SCHEDULING_AXIS,
    check_cli_abstraction_level,
)
from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._ecosystem.click_compat import deprecated_alias


def _group(name: str) -> click.Group:
    """An empty click group — the rule reads names, so a shell suffices."""
    return click.Group(name)


def _findings(root: click.BaseCommand, package: str = "demo") -> list[Violation]:
    """Run the checker and hand back the accumulator it filled."""
    out: list[Violation] = []
    check_cli_abstraction_level(root, package, out)
    return out


@pytest.fixture
def our_own_cli_findings() -> list[Violation]:
    """§13a findings against scitex-dev's real, fully-built command tree."""
    from scitex_dev._cli._root import main

    return _findings(main, "scitex-dev")


class TestMixedMenuIsFlagged:
    def test_daemon_beside_cron_at_top_level_is_flagged(self):
        # Arrange
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(_group("cron"))
        # Act
        out = _findings(root)
        # Assert
        assert [v.rule for v in out] == ["§13a"]

    def test_the_finding_is_recorded_against_the_parent_menu(self):
        # Arrange
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(_group("cron"))
        # Act
        out = _findings(root)
        # Assert
        assert out[0].command == "demo"

    def test_a_nested_mixed_menu_is_flagged_on_its_own_group(self):
        # Arrange — the real shape: kind groups mounted side by side.
        root = click.Group("root")
        dev = _group("dev")
        root.add_command(dev)
        for name in ("service", "timer", "cron", "systemd"):
            dev.add_command(_group(name))
        # Act
        out = _findings(root)
        # Assert
        assert out[0].command == "demo dev"

    def test_a_mixed_menu_yields_one_finding_not_one_per_child(self):
        # Arrange — four offending children, one defective menu.
        root = click.Group("root")
        dev = _group("dev")
        root.add_command(dev)
        for name in ("service", "timer", "cron", "systemd"):
            dev.add_command(_group(name))
        # Act
        out = _findings(root)
        # Assert
        assert len(out) == 1

    def test_the_message_names_the_intent_side(self):
        # Arrange
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(_group("systemd"))
        # Act
        out = _findings(root)
        # Assert — a finding that does not say WHICH names collided is
        # not actionable from the audit log alone.
        assert "'daemon'" in out[0].message

    def test_the_message_names_the_mechanism_side(self):
        # Arrange
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(_group("systemd"))
        # Act
        out = _findings(root)
        # Assert
        assert "'systemd'" in out[0].message

    def test_leaf_commands_count_toward_the_menu_not_only_groups(self):
        # Arrange — the menu is names, not types; a leaf `cron` beside a
        # `daemon` group reads exactly as mixed to the user.
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(click.Command("cron", callback=lambda: None))
        # Act
        out = _findings(root)
        # Assert
        assert len(out) == 1


class TestLegitimateShapesAreNotFlagged:
    def test_a_mechanism_with_no_intent_sibling_is_not_flagged(self):
        # Arrange — `dev cron` = "manage MY crontab entries" names an
        # artefact, and is exactly the case this rule must not break.
        root = click.Group("root")
        dev = _group("dev")
        root.add_command(dev)
        for name in ("cron", "hooks", "skills"):
            dev.add_command(_group(name))
        # Act
        out = _findings(root)
        # Assert
        assert out == []

    def test_two_mechanisms_together_are_not_flagged(self):
        # Arrange — `cron` and `systemd` are the same level as each
        # other; the level is only wrong beside an intent.
        root = click.Group("root")
        root.add_command(_group("cron"))
        root.add_command(_group("systemd"))
        # Act
        out = _findings(root)
        # Assert
        assert out == []

    def test_an_intent_with_no_mechanism_sibling_is_not_flagged(self):
        # Arrange
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(_group("hooks"))
        # Act
        out = _findings(root)
        # Assert
        assert out == []

    def test_intent_and_mechanism_in_different_groups_are_not_flagged(self):
        # Arrange — nothing is offered as an alternative to anything, so
        # there is no mixed menu anywhere.
        root = click.Group("root")
        left = _group("left")
        right = _group("right")
        root.add_command(left)
        root.add_command(right)
        left.add_command(_group("daemon"))
        right.add_command(_group("cron"))
        # Act
        out = _findings(root)
        # Assert
        assert out == []

    def test_object_level_names_are_not_on_the_axis(self):
        # Arrange — `skills` is not another way of doing `daemon`.
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(_group("skills"))
        root.add_command(_group("shell"))
        # Act
        out = _findings(root)
        # Assert
        assert out == []

    def test_a_non_group_root_command_produces_no_finding(self):
        # Arrange
        @click.command()
        def root():
            pass

        # Act
        out = _findings(root)
        # Assert
        assert out == []


class TestHiddenCommandsAreNotOnTheMenu:
    def test_a_hidden_mechanism_does_not_mix_the_menu(self):
        # Arrange — a hidden command is not offered as an alternative.
        root = click.Group("root")
        root.add_command(_group("daemon"))
        root.add_command(
            click.Command("cron", callback=lambda: None, hidden=True)
        )
        # Act
        out = _findings(root)
        # Assert
        assert out == []

    def test_a_migrated_phase_w_alias_is_not_reflagged(self):
        # Arrange — the real migration shape: `<pkg> systemd` warn-forwards
        # to `<pkg> dev systemd`, and `deprecated_alias` hides it. Top
        # level then holds `daemon` + a HIDDEN `systemd`, and `dev` holds
        # only the mechanism, so neither menu is mixed.
        root = click.Group("root")
        root.add_command(_group("daemon"))
        dev = _group("dev")
        root.add_command(dev)
        target = _group("systemd")
        dev.add_command(target)
        deprecated_alias(root, "systemd", target=target, remove_in="0.50")
        # Act
        out = _findings(root)
        # Assert
        assert out == []


class TestSharedCommandObjects:
    def test_one_group_mounted_twice_yields_one_finding(self):
        # Arrange — `deprecated_alias` mounts the SAME object under two
        # names, so an unguarded walk reports one mixed menu twice.
        root = click.Group("root")
        shared = _group("shared")
        shared.add_command(_group("service"))
        shared.add_command(_group("cron"))
        root.add_command(shared)
        root.add_command(shared, name="alias")
        # Act
        out = _findings(root)
        # Assert
        assert len(out) == 1


class TestAxisFamilyVocabulary:
    def test_the_seeded_axis_keeps_its_two_sides_disjoint(self):
        # Arrange — a word on both sides would make the rule fire on a
        # single command that is its own sibling.
        family = SCHEDULING_AXIS
        # Act
        overlap = family.intent & family.mechanism
        # Assert
        assert overlap == frozenset()

    def test_every_registered_family_keeps_its_two_sides_disjoint(self):
        # Arrange — holds as families are added.
        families = AXIS_FAMILIES
        # Act
        overlapping = [f.axis for f in families if f.intent & f.mechanism]
        # Assert
        assert overlapping == []

    def test_the_job_kind_intent_spellings_are_covered(self):
        # Arrange — the vocabulary is seeded from `jobs/_kinds.py`; if
        # those spellings drifted out, the rule would silently stop
        # recognising the very case it was built for.
        expected = {"daemon", "periodic", "service"}
        # Act
        intent = SCHEDULING_AXIS.intent
        # Assert
        assert expected <= intent

    def test_the_job_kind_mechanism_spellings_are_covered(self):
        # Arrange
        expected = {"cron", "timer", "systemd"}
        # Act
        mechanism = SCHEDULING_AXIS.mechanism
        # Assert
        assert expected <= mechanism


class TestRuleFiresAgainstOurOwnRealCli:
    """The anti-phantom test: a rule that cannot fire is not a rule.

    `scitex-dev ecosystem dev` mounts one group per JobSpec KIND —
    `service`, `timer`, `cron` — plus the deprecated `systemd` alias
    group, all as visible siblings. That menu offers `service` (the
    mechanism-agnostic INTENT, per `jobs/_kinds.py`) beside `timer` and
    `cron` (MECHANISMS for one intent), which is exactly the shape §13a
    describes.

    This is a KNOWN, STANDING violation in scitex-dev's own CLI, pinned
    here rather than hidden: the remedy collapses published CLI verbs
    into `periodic --mechanism`, which is a MIGRATION (Phase W alias
    first, removal later) and is deliberately out of scope for the
    reporting-only change that introduced the rule. When that migration
    lands, this test flips to asserting compliance — and until then it
    proves the rule fires against a real tree, not only synthetic ones.
    """

    def test_ecosystem_dev_is_flagged(self, our_own_cli_findings):
        # Arrange
        flagged = {v.command for v in our_own_cli_findings if v.rule == "§13a"}
        # Act
        hit = "scitex-dev ecosystem dev" in flagged
        # Assert
        assert hit, (
            "§13a no longer fires on scitex-dev's own `ecosystem dev` "
            "menu; if the migration landed, flip this test to assert "
            f"compliance. Currently flagged: {sorted(flagged)}"
        )

    def test_the_finding_names_the_intent_verb(self, our_own_cli_findings):
        # Arrange
        target = "scitex-dev ecosystem dev"
        # Act
        message = next(
            v.message for v in our_own_cli_findings if v.command == target
        )
        # Assert
        assert "'service'" in message

    def test_the_finding_names_a_mechanism_verb(self, our_own_cli_findings):
        # Arrange
        target = "scitex-dev ecosystem dev"
        # Act
        message = next(
            v.message for v in our_own_cli_findings if v.command == target
        )
        # Assert
        assert "'cron'" in message or "'timer'" in message

    def test_our_own_dev_group_is_clean(self, our_own_cli_findings):
        # Arrange — `scitex-dev dev` holds `cron`/`hooks`/`skills`, a
        # mechanism with no intent sibling. That is the legitimate shape
        # and must stay unflagged, or the rule punishes what it permits.
        target = "scitex-dev dev"
        # Act
        flagged = {v.command for v in our_own_cli_findings}
        # Assert
        assert target not in flagged


# EOF
