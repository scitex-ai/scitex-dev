#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A store must refuse PGDATA that will not survive a container rebuild.

Found by the OPERATOR, 2026-08-10 02:52, reviewing the store design. He
named the requirement directly:

    「コンテナの外にデータベースの実態をおかないと、コンテナを壊した
      ときにデータが復旧できなくなるので、そういった状態は検知して
      エラーを出す」

He was right that it was missing. `_host.py` carried a COMMENT saying
PGDATA is "bind-mounted OUTSIDE any container, so rebuilding the container
destroys no data" — and nothing verified it. A comment states an intention
and cannot notice when the intention fails.

THE FAILURE IT PREVENTS. `$HOME` is `/home/agent` inside these containers
while the durable bind lives under the host's home. If `~/.scitex/pg`
resolves container-local, the store comes up, works perfectly, accepts
every write, and loses all of it at the next image rebuild — with no error
and no warning at any point.

MEASURED DISCRIMINATOR, on scitex-compute-04:

    /home/ywatanabe   ext4                  <- host bind, survives
    /                 fuse.fuse-overlayfs   <- container-local, does not

WHY IT RAISES RATHER THAN WARNS. The same night this was found, four days
of operator-facing Telegram silence had gone unnoticed because every check
available was advisory and every one reported healthy. For a durability
property the only honest response is refusal: a store that cannot keep what
it accepts must not accept it.

WHY THE ENVIRONMENT CHECKS ARE `skipif` DECORATORS rather than `pytest.skip`
in the body: both express the same condition, but a skip inside the body
reads as a second assertion to the test-quality linter and buries the
precondition where a reader finds it only after the setup. At collection
time it is a property of the test, which is what it actually is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.store._errors import StoreTargetError
from scitex_dev.store._host import (
    _EPHEMERAL_FSTYPES,
    _fstype_of,
    require_durable_pgdata,
)

#: A real ephemeral filesystem to test the refusal against. `/dev/shm` is
#: tmpfs on Linux — an actual ephemeral mount, not a simulated one.
EPHEMERAL = Path("/dev/shm")


def _a_durable_directory() -> "Path | None":
    """Any real directory on a filesystem that survives a rebuild.

    NOT pytest's `tmp_path`: measured on this container, `tmp_path` lands on
    an EPHEMERAL filesystem, so using it skipped both acceptance tests and
    left the guard's "does not refuse everything" direction unexercised.
    That is the direction which, if wrong, makes the guard itself the
    outage — the half that must not go untested.
    """
    for candidate in (Path.home(), Path("/etc"), Path("/usr"), Path("/")):
        if _fstype_of(candidate) not in _EPHEMERAL_FSTYPES:
            return candidate
    return None


DURABLE = _a_durable_directory()

needs_ephemeral = pytest.mark.skipif(
    _fstype_of(EPHEMERAL) not in _EPHEMERAL_FSTYPES,
    reason="/dev/shm is not an ephemeral filesystem on this host",
)
needs_durable = pytest.mark.skipif(
    DURABLE is None,
    reason="no durable filesystem is visible from this container",
)


def _refusal_message(path: Path) -> str:
    """The guard's complaint, as text. Empty when it did not complain."""
    try:
        require_durable_pgdata(path)
    except StoreTargetError as exc:
        return str(exc)
    return ""


class TestAnEphemeralFilesystemIsRefused:
    """The whole point of the guard."""

    @needs_ephemeral
    def test_a_tmpfs_path_raises(self):
        # Arrange
        target = EPHEMERAL / "scitex-pg"
        # Act / raises is the assertion
        with pytest.raises(StoreTargetError):
            # Assert
            require_durable_pgdata(target)

    @needs_ephemeral
    def test_the_refusal_names_the_filesystem_type(self):
        # Arrange
        target = EPHEMERAL / "scitex-pg"
        # Act
        message = _refusal_message(target)
        # Assert
        assert "tmpfs" in message

    @needs_ephemeral
    def test_the_refusal_shows_what_it_resolved_from(self):
        """$HOME differing host-vs-container is the failure; show both."""
        # Arrange
        target = EPHEMERAL / "scitex-pg"
        # Act
        message = _refusal_message(target)
        # Assert
        assert "Resolved from:" in message

    @needs_ephemeral
    def test_the_refusal_says_it_will_not_survive(self):
        # Arrange
        target = EPHEMERAL / "scitex-pg"
        # Act
        message = _refusal_message(target)
        # Assert
        assert "DOES NOT SURVIVE" in message


class TestADurablePathIsAccepted:
    """A guard that refuses everything is an outage, not a check."""

    @needs_durable
    def test_a_durable_path_is_accepted(self):
        # Arrange
        target = DURABLE / "scitex-pg-probe"
        # Act
        result = require_durable_pgdata(target)
        # Assert
        assert result is None

    @needs_durable
    def test_a_path_that_does_not_exist_yet_is_judged_by_its_parent(self):
        """PGDATA is created on first start; the question is where it lands."""
        # Arrange
        target = DURABLE / "not" / "created" / "yet"
        # Act
        result = require_durable_pgdata(target)
        # Assert
        assert result is None


class TestItAbstainsWhenItCannotTell:
    """"Cannot determine" is not "unsafe". Blocking every host with an
    unreadable mount table would make the guard the outage."""

    def test_an_unresolvable_filesystem_is_not_treated_as_ephemeral(self):
        # Arrange
        unknown = None
        # Act
        outcome = unknown not in _EPHEMERAL_FSTYPES
        # Assert
        assert outcome


class TestTheDiscriminatorItself:
    def test_root_reports_some_filesystem(self):
        # Arrange
        root = Path("/")
        # Act
        fstype = _fstype_of(root)
        # Assert
        assert fstype is not None

    def test_the_ephemeral_set_contains_the_measured_overlay_type(self):
        """The exact string measured on compute-04, not a guess."""
        # Arrange
        measured = "fuse.fuse-overlayfs"
        # Act
        listed = measured in _EPHEMERAL_FSTYPES
        # Assert
        assert listed

    def test_the_longest_matching_mount_wins(self):
        """`/home/x` must beat `/` for a path under it, or every path on a
        bind would report the container root's filesystem."""
        # Arrange
        home = Path.home()
        # Act
        same_as_root = _fstype_of(home) == _fstype_of(Path("/"))
        # Assert
        assert not same_as_root


class TestTheGuardSurvivesATransportChange:
    """ADR-0006 Decision 7 was REVERSED on 2026-08-10: TCP on 55432 becomes
    the default instead of the UNIX socket.

    This guard was wired to the socket branch of `host_store()` because, when
    it was written, the socket WAS the instance this host manages. The
    reversal separates those two ideas, and a durability check that rides on
    a transport disappears when the transport does — with nothing failing to
    announce it.

    These tests pin the INVARIANT rather than the current wiring, so the
    protection is not quietly lost by whoever flips the default.
    """

    def test_the_parameter_is_not_named_after_a_transport(self):
        """`pgdata_dir`, not `socket_dir` — PGDATA is where the data lives;
        the socket is one way to reach it."""
        # Arrange
        import inspect

        # Act
        params = list(
            inspect.signature(require_durable_pgdata).parameters
        )
        # Assert
        assert params == ["pgdata_dir"]

    @needs_ephemeral
    def test_host_store_refuses_an_ephemeral_pgdata(self):
        """The guard must fire through `host_store()`, not merely exist.

        This is the test that fails if a future transport change drops the
        call — which is the whole point of writing it.
        """
        # Arrange
        from scitex_dev.store._host import host_store

        target = EPHEMERAL / "scitex-pg"
        # Act / raises is the assertion
        with pytest.raises(StoreTargetError):
            # Assert
            host_store(pkg="scitex_dev", socket_dir=target)


# EOF
