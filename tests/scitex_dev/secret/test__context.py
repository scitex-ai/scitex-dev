# -*- coding: utf-8 -*-
"""``SecretContext`` — one derivation of where a secret lives.

Built on ``scitex_dev.scope.Scope`` rather than restating it: an earlier draft
carried its own user/group/project fields, which was a second definition of the
same idea. These tests pin the layout so a leaf can rely on ONE shape.

Pure path derivation — real environment variables, no gpg, no writes.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev.scope import Scope
from scitex_dev.secret import SecretContext, name_reservation_error

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
        ctx = SecretContext(app="figrecipe", scope=Scope.standalone())
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == f"{_HOME}/figrecipe/secret"

    def test_an_owner_nests_under_the_same_app_root(self):
        # Arrange
        ctx = SecretContext(app="cards", scope=Scope(owner="ywatanabe"))
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == f"{_HOME}/cards/secret/owners/ywatanabe"

    def test_a_project_nests_under_its_owner(self):
        # Arrange
        ctx = SecretContext(
            app="writer", scope=Scope(owner="ywatanabe", project="thesis")
        )
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == (
            f"{_HOME}/writer/secret/owners/ywatanabe/projects/thesis"
        )


class TestOneOwnerNamespace:
    """A user and an org cannot collide, because the URL never told them apart."""

    def test_an_org_uses_the_same_shape_as_a_user(self):
        # Arrange
        ctx = SecretContext(app="scholar", scope=Scope(owner="scitex"))
        # Act
        root = ctx.secret_root()
        # Assert
        assert root.as_posix() == f"{_HOME}/scholar/secret/owners/scitex"

    def test_two_owners_do_not_share_a_root(self):
        # Arrange
        a = SecretContext(app="cards", scope=Scope(owner="alice"))
        b = SecretContext(app="cards", scope=Scope(owner="bob"))
        # Act
        same = a.secret_root() == b.secret_root()
        # Assert
        assert same is False


class TestIncoherentScopesAreRefused:
    """`Scope` validates itself, so the refusals hold here too."""

    def test_a_project_without_an_owner_is_refused(self):
        # Arrange
        kwargs = dict(project="thesis")
        # Act
        raised = pytest.raises(ValueError, match="no owner")
        # Assert
        with raised:
            Scope(**kwargs)

    @pytest.mark.parametrize("owner", ["../etc", "a/b", "", ".hidden"])
    def test_a_traversing_or_odd_owner_is_refused(self, owner):
        # Arrange
        kwargs = dict(owner=owner)
        # Act
        raised = pytest.raises(ValueError)
        # Assert
        with raised:
            Scope(**kwargs)

    def test_a_traversing_app_is_refused(self):
        """A VALID scope is passed on purpose.

        Without it this raises TypeError for the missing argument and never
        reaches the app check — the test would look like it passed while
        proving nothing about traversal. Supplying the scope makes the app
        validation the only thing that can fail here.
        """
        # Arrange
        kwargs = dict(app="../../etc", scope=Scope.standalone())
        # Act
        raised = pytest.raises(ValueError)
        # Assert
        with raised:
            SecretContext(**kwargs)


class TestReservedNames:
    """`owners/` is a directory, so it cannot also be a secret name."""

    @pytest.mark.parametrize("name", ["owners", "owners/token"])
    def test_a_reserved_prefix_is_reported(self, name):
        # Arrange
        candidate = name
        # Act
        reason = name_reservation_error(candidate)
        # Assert
        assert reason is not None

    @pytest.mark.parametrize(
        "name", ["api/openai", "ownersx/token", "mail/sales", "users/x"]
    )
    def test_an_ordinary_name_is_allowed(self, name):
        # Arrange
        candidate = name
        # Act
        reason = name_reservation_error(candidate)
        # Assert
        assert reason is None


class TestScopeMustBeStated:
    """`scope` has no default — operator directive 2026-08-04.

    The point is not tidiness. A defaulted scope lets the most dangerous
    call — a request handler that forgot to pass the requesting user —
    construct successfully and quietly read the standalone store. A missing
    argument is loud and immediate; a defaulted one is a silent wrong answer.
    """

    def test_omitting_scope_is_a_type_error(self):
        # Arrange
        kwargs = dict(app="cards")
        # Act
        raised = pytest.raises(TypeError)
        # Assert
        with raised:
            SecretContext(**kwargs)

    def test_standalone_is_stated_not_omitted(self):
        # Arrange
        ctx = SecretContext(app="cards", scope=Scope.standalone())
        # Act
        standalone = ctx.is_standalone
        # Assert
        assert standalone is True

    def test_standalone_never_looks_up_the_current_user(self):
        """`Scope.standalone()` must not resolve to $USER.

        If it did, a forgotten scope in a web request would resolve to the
        SERVICE ACCOUNT's store — a successful-looking read of the wrong
        data, which is the failure this whole design avoids.
        """
        # Arrange
        scope = Scope.standalone()
        # Act
        owner = scope.owner
        # Assert
        assert owner is None

    def test_everything_and_standalone_are_distinct_intentions(self):
        """Same value, different names — a reader must not have to guess."""
        # Arrange
        cross = Scope.everything()
        # Act
        cross_cutting = cross.is_cross_cutting
        # Assert
        assert cross_cutting is True

    def test_an_owner_is_not_standalone(self):
        # Arrange
        ctx = SecretContext(app="cards", scope=Scope(owner="ywatanabe"))
        # Act
        standalone = ctx.is_standalone
        # Assert
        assert standalone is False


# EOF
