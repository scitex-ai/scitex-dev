# -*- coding: utf-8 -*-
"""``Context`` — one derivation of where a secret lives, for every situation.

The same leaf app runs standalone, inside scitex-hub for a logged-in user, for
a group, and scoped to a project. These tests pin the layout so a leaf can rely
on ONE shape, and pin the refusals that keep one owner from addressing
another's store.

Pure path derivation — real environment variables, no gpg, no writes.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev.secret import Context, name_reservation_error

_HOME = "/tmp/scitex-test-home"


@pytest.fixture(autouse=True)
def home_env():
    """Pin the store home, and clear the absolute-root override.

    The override would short-circuit every derivation under test, so a suite
    run after something that exported it would pass while testing nothing.
    """
    # Arrange
    previous = {
        key: os.environ.get(key)
        for key in ("SCITEX_SECRET_HOME", "SCITEX_DEV_SECRET_ROOT")
    }
    os.environ["SCITEX_SECRET_HOME"] = _HOME
    os.environ.pop("SCITEX_DEV_SECRET_ROOT", None)
    yield _HOME
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class TestTheAppIsAlwaysFirst:
    """The invariant a leaf relies on: `<home>/<app>/secret/…` in every case."""

    def test_standalone_is_the_app_root(self):
        # Arrange
        ctx = Context(app="figrecipe")
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == f"{_HOME}/figrecipe/secret"

    def test_a_user_nests_under_the_same_app_root(self):
        # Arrange
        ctx = Context(app="cards", user="ywatanabe")
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == f"{_HOME}/cards/secret/users/ywatanabe"

    def test_a_group_nests_under_the_same_app_root(self):
        # Arrange
        ctx = Context(app="scholar", group="scitex")
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == f"{_HOME}/scholar/secret/groups/scitex"

    def test_a_project_nests_under_its_owner(self):
        # Arrange
        ctx = Context(app="writer", user="ywatanabe", project="thesis")
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == (
            f"{_HOME}/writer/secret/users/ywatanabe/projects/thesis"
        )

    def test_a_group_project_nests_under_the_group(self):
        # Arrange
        ctx = Context(app="scholar", group="scitex", project="paper1")
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == (
            f"{_HOME}/scholar/secret/groups/scitex/projects/paper1"
        )


class TestOwnersAreDistinct:
    """Two owners must never resolve to one directory."""

    def test_two_users_do_not_share_a_root(self):
        # Arrange
        a = Context(app="cards", user="alice")
        b = Context(app="cards", user="bob")
        # Act
        same = a.secret_root() == b.secret_root()
        # Assert
        assert same is False

    def test_a_user_and_a_group_of_the_same_name_do_not_collide(self):
        # Arrange
        u = Context(app="cards", user="scitex")
        g = Context(app="cards", group="scitex")
        # Act
        same = u.secret_root() == g.secret_root()
        # Assert
        assert same is False


class TestIncoherentContextsAreRefused:
    """Shapes that could not hold a readable secret fail at construction."""

    def test_both_user_and_group_is_refused(self):
        # Arrange
        kwargs = dict(app="cards", user="ywatanabe", group="scitex")
        # Act
        raised = pytest.raises(ValueError, match="ONE owner")
        # Assert
        with raised:
            Context(**kwargs)

    def test_a_project_without_an_owner_is_refused(self):
        # Arrange
        kwargs = dict(app="cards", project="thesis")
        # Act
        raised = pytest.raises(ValueError, match="requires a user or a group")
        # Assert
        with raised:
            Context(**kwargs)

    @pytest.mark.parametrize(
        "user", ["../etc", "a/b", "", ".hidden", "with space"]
    )
    def test_a_traversing_or_odd_owner_is_refused(self, user):
        # Arrange
        kwargs = dict(app="cards", user=user)
        # Act
        raised = pytest.raises(ValueError)
        # Assert
        with raised:
            Context(**kwargs)

    def test_a_traversing_app_is_refused(self):
        # Arrange
        kwargs = dict(app="../../etc")
        # Act
        raised = pytest.raises(ValueError)
        # Assert
        with raised:
            Context(**kwargs)


class TestReservedNames:
    """`users/` and `groups/` are directories, so they cannot also be secrets."""

    @pytest.mark.parametrize("name", ["users", "users/token", "groups/key"])
    def test_a_reserved_prefix_is_reported(self, name):
        # Arrange
        candidate = name
        # Act
        reason = name_reservation_error(candidate)
        # Assert
        assert reason is not None

    @pytest.mark.parametrize(
        "name", ["api/openai", "usersx/token", "mail/sales"]
    )
    def test_an_ordinary_name_is_allowed(self, name):
        # Arrange
        candidate = name
        # Act
        reason = name_reservation_error(candidate)
        # Assert
        assert reason is None


class TestStandaloneIsExplicit:
    def test_no_owner_means_standalone(self):
        # Arrange
        ctx = Context(app="cards")
        # Act
        standalone = ctx.is_standalone
        # Assert
        assert standalone is True

    def test_a_user_is_not_standalone(self):
        # Arrange
        ctx = Context(app="cards", user="ywatanabe")
        # Act
        standalone = ctx.is_standalone
        # Assert
        assert standalone is False

    def test_a_group_context_is_shared(self):
        # Arrange
        ctx = Context(app="cards", group="scitex")
        # Act
        shared = ctx.is_shared
        # Assert
        assert shared is True


# EOF
