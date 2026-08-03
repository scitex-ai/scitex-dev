#!/usr/bin/env python3
"""§1a accepts the `skills` group at either sanctioned location.

§13 lists `skills` among the six self-maintenance verbs that must nest
under `dev`. §1a requires a `skills {list,get,install}` group to exist.
Until 2026-08-03 §1a looked only at top level, which made the pair
unsatisfiable: satisfying §13 made §1a report the group missing, and
satisfying §1a made §13 report it un-nested. scitex-dev — which owns
both rules — was the first package caught between them, and every
package that adopts §13 reaches the same fork.

These tests pin the resolution so neither side can drift back:

* nested under `dev` satisfies §1a (the §13-compliant shape);
* top level still satisfies §1a (packages that have not migrated);
* neither present is still a violation (the rule keeps its teeth);
* a Phase W alias does NOT satisfy it — an alias forwards, it does not
  host the verbs, and accepting one would let a package delete its
  skills CLI and stay green.

No mocks — real click trees.
"""

from __future__ import annotations

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary._skills_group_location import (
    resolve_skills_group,
)
from scitex_dev._ecosystem.click_compat import deprecated_alias


def _skills_group() -> click.Group:
    @click.group("skills")
    def skills() -> None:
        pass

    for verb in ("list", "get", "install"):
        skills.command(verb)(lambda: None)
    return skills


class TestNestedUnderDev:
    def test_dev_skills_is_resolved(self):
        # Arrange
        @click.group()
        def root() -> None:
            pass

        @root.group("dev")
        def dev() -> None:
            pass

        dev.add_command(_skills_group())
        # Act
        found, _where = resolve_skills_group(root)
        # Assert
        assert found is not None

    def test_dev_skills_is_reported_at_its_real_path(self):
        # Arrange
        @click.group()
        def root() -> None:
            pass

        @root.group("dev")
        def dev() -> None:
            pass

        dev.add_command(_skills_group())
        # Act
        _found, where = resolve_skills_group(root)
        # Assert
        assert where == "dev skills"


class TestTopLevelStillAccepted:
    def test_unmigrated_top_level_skills_is_resolved(self):
        # Arrange
        @click.group()
        def root() -> None:
            pass

        root.add_command(_skills_group())
        # Act
        found, _where = resolve_skills_group(root)
        # Assert
        assert found is not None


class TestRuleKeepsItsTeeth:
    def test_absent_skills_group_resolves_to_none(self):
        # Arrange
        @click.group()
        def root() -> None:
            pass

        # Act
        found, _where = resolve_skills_group(root)
        # Assert
        assert found is None

    def test_phase_w_alias_alone_does_not_satisfy_the_rule(self):
        """An alias forwards; it does not host `list`/`get`/`install`.

        Accepting one would let a package delete its skills CLI, leave a
        forwarding stub behind, and still pass §1a.
        """
        # Arrange
        @click.group()
        def root() -> None:
            pass

        @root.group("dev")
        def dev() -> None:
            pass

        deprecated_alias(
            root, "skills", target=dev, remove_in="0.50", phase="warn"
        )
        # Act
        found, _where = resolve_skills_group(root)
        # Assert
        assert found is None


# EOF
