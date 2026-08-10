# -*- coding: utf-8 -*-
"""The scope contract — the rules that must not be re-decided per app.

Pinned here rather than in each leaf, because a rule every app re-implements is
a rule every app gets slightly wrong. No mocks: these are plain values.
"""

from __future__ import annotations

import pytest

from scitex_dev.scope import (
    AppSpec,
    Member,
    Principal,
    Project,
    Scope,
    effective_role,
)


class TestAgentsAreRealPrincipals:
    """An agent is not a mode its owner is in; it is its own principal."""

    def test_an_agent_carries_its_owner(self):
        # Arrange
        agent = Principal(id="scitex-dev", kind="agent", owner="ywatanabe")
        # Act
        owner = agent.owner
        # Assert
        assert owner == "ywatanabe"

    def test_an_agent_without_an_owner_is_refused(self):
        # Arrange
        kwargs = dict(id="rogue-bot", kind="agent")
        # Act
        raised = pytest.raises(ValueError, match="no owner")
        # Assert
        with raised:
            Principal(**kwargs)

    def test_a_user_may_not_carry_an_owner(self):
        # Arrange
        kwargs = dict(id="k.oishi", kind="user", owner="ywatanabe")
        # Act
        raised = pytest.raises(ValueError, match="act on behalf")
        # Assert
        with raised:
            Principal(**kwargs)

    def test_an_agent_is_not_human(self):
        # Arrange
        agent = Principal(id="writer-bot", kind="agent", owner="k.oishi")
        # Act
        human = agent.is_human
        # Assert
        assert human is False


class TestAnAgentNeverExceedsItsOwner:
    """Creating an agent must not be a way to gain permission."""

    def test_a_grant_above_the_owner_is_capped(self):
        # Arrange
        granted, owner_role = "admin", "read"
        # Act
        actual = effective_role(granted, owner_role)
        # Assert
        assert actual == "read"

    def test_a_grant_below_the_owner_is_kept(self):
        # Arrange
        granted, owner_role = "read", "admin"
        # Act
        actual = effective_role(granted, owner_role)
        # Assert
        assert actual == "read"

    def test_revoking_the_owner_revokes_the_agent(self):
        # Arrange
        granted, owner_role = "write", None
        # Act
        raised = pytest.raises(PermissionError, match="no ceiling")
        # Assert
        with raised:
            effective_role(granted, owner_role)


class TestScopeSaysWhatNotWho:
    def test_no_scope_means_cross_cutting(self):
        # Arrange
        scope = Scope()
        # Act
        cross = scope.is_cross_cutting
        # Assert
        assert cross is True

    def test_a_project_without_an_owner_is_refused(self):
        # Arrange
        kwargs = dict(project="thesis")
        # Act
        raised = pytest.raises(ValueError, match="no owner")
        # Assert
        with raised:
            Scope(**kwargs)

    def test_the_query_has_at_most_two_keys(self):
        # Arrange
        scope = Scope(owner="ywatanabe", project="thesis")
        # Act
        query = scope.query()
        # Assert
        assert query == {"owner": "ywatanabe", "project": "thesis"}

    def test_a_cross_cutting_scope_has_an_empty_query(self):
        # Arrange
        scope = Scope()
        # Act
        query = scope.query()
        # Assert
        assert query == {}


class TestProjectIdentityMatchesTheUrl:
    def test_the_path_is_owner_slash_name(self):
        # Arrange
        project = Project(owner="ywatanabe", name="thesis")
        # Act
        path = project.path()
        # Assert
        assert path == "ywatanabe/thesis"

    def test_a_project_defaults_to_private(self):
        # Arrange
        project = Project(owner="ywatanabe", name="thesis")
        # Act
        public = project.is_public
        # Assert
        assert public is False

    def test_public_is_a_real_state(self):
        # Arrange
        project = Project(owner="scitex", name="docs", visibility="public")
        # Act
        public = project.is_public
        # Assert
        assert public is True


class TestTheTwoAppAxesAreIndependent:
    """Checked against the five shipped apps."""

    @pytest.mark.parametrize(
        "app,lives,view",
        [
            ("writer", "project", "pinned"),
            ("figrecipe", "project", "pinned"),
            ("cards", "project", "cross"),
            ("scholar", "owner", "pinned"),
            ("storage", "owner", "cross"),
        ],
    )
    def test_every_shipped_combination_is_expressible(self, app, lives, view):
        # Arrange
        spec = AppSpec(app=app, data_lives_at=lives, view=view)
        # Act
        described = (spec.data_lives_at, spec.view)
        # Assert
        assert described == (lives, view)

    def test_a_cross_app_must_not_carry_an_ambient_scope(self):
        # Arrange
        cards = AppSpec(app="cards", data_lives_at="project", view="cross")
        # Act
        ambient = cards.wants_ambient_scope
        # Assert
        assert ambient is False

    def test_a_pinned_app_carries_an_ambient_scope(self):
        # Arrange
        writer = AppSpec(app="writer", data_lives_at="project", view="pinned")
        # Act
        ambient = writer.wants_ambient_scope
        # Assert
        assert ambient is True


class TestRolesReadPlainly:
    def test_write_may_write(self):
        # Arrange
        member = Member(
            principal=Principal(id="k.oishi", kind="user"), role="write"
        )
        # Act
        may = member.may_write
        # Assert
        assert may is True

    def test_read_may_not_write(self):
        # Arrange
        member = Member(
            principal=Principal(id="reviewer-1", kind="user"), role="read"
        )
        # Act
        may = member.may_write
        # Assert
        assert may is False


# EOF
