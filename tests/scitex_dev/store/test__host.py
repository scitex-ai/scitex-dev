#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The host store resolves to the central Postgres, and never falls back.

These lock the decisions that are cheapest to erode later: the default
engine, the default TARGET (the fleet's one writable node, not this host's
read-only replica), the refusal of Postgres's own 5432, and — the one that
matters most — that a host with no Postgres gets an ERROR rather than a
private local file nobody else can see.

The default flipped on 2026-08-30. It was this host's own Postgres over a
UNIX socket, measured to be a read-only replica of one central primary, and
so a store that could not be written and said nothing about it.

The environment is manipulated through real ``os.environ`` fixtures that
restore on teardown, not through ``monkeypatch``: the variable IS the
production input here, so setting it for real is testing production rather
than rewriting it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterator

import pytest

from scitex_dev.store import Backend, StoreTarget, host_store, socket_dsn
from scitex_dev.store._errors import StoreTargetError
from scitex_dev.store._host import (
    DEFAULT_CENTRAL_HOST,
    DEFAULT_SOCKET_DIR,
    DEFAULT_TCP_PORT,
    STORE_DSN_ENV,
    is_socket_dsn,
    require_durable_pgdata,
)


@pytest.fixture
def unconfigured_host() -> Iterator[None]:
    """A host with no override set — the state a fresh machine is in."""
    saved = os.environ.pop(STORE_DSN_ENV, None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[STORE_DSN_ENV] = saved


@pytest.fixture
def set_store_override() -> Iterator[Callable[[str], None]]:
    """Set the real override variable, restoring whatever was there."""
    saved = os.environ.get(STORE_DSN_ENV)

    def _set(value: str) -> None:
        os.environ[STORE_DSN_ENV] = value

    try:
        yield _set
    finally:
        if saved is None:
            os.environ.pop(STORE_DSN_ENV, None)
        else:
            os.environ[STORE_DSN_ENV] = saved


class TestDefaultIsTheCentralPostgres:
    """An unconfigured host resolves to the fleet's ONE WRITABLE node.

    Not to its own. Measured 2026-08-30, `scitex-primary:55432` reports
    `pg_is_in_recovery() = FALSE` and every other host's local 55432 reports
    `TRUE`, all of them carrying the same `system_identifier` — one cluster,
    streaming replication, one primary. Resolving to the local node handed
    back a store that could not be written, with nothing failing to say so.
    """

    def test_default_backend_is_postgres(self, unconfigured_host):
        # Arrange
        package = "cards"
        # Act
        target = host_store(pkg=package)
        # Assert
        assert target.backend is Backend.POSTGRES

    def test_default_dsn_names_the_central_host(self, unconfigured_host):
        """The one node that can accept a write."""
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert f"//{DEFAULT_CENTRAL_HOST}:" in dsn

    def test_default_dsn_carries_the_fleet_port(self, unconfigured_host):
        """55432, explicitly — this replaces the assertion that the default
        carried no port at all, which was true only while it was a socket."""
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert f":{DEFAULT_TCP_PORT}/" in dsn

    def test_default_dsn_is_not_a_socket_directory(self, unconfigured_host):
        """It was one until 2026-08-30, and that is exactly the defect: a
        socket can only ever reach the local instance, which is a replica."""
        # Arrange
        package = "cards"
        # Act
        target = host_store(pkg=package)
        # Assert
        assert not is_socket_dsn(target)

    def test_default_dsn_does_not_carry_the_postgres_default_port(
        self, unconfigured_host
    ):
        """5432 stays refused on TCP too. It collides with any system
        Postgres, and an address that could name either is how an SSH tunnel
        to a laptop passed for a local server on 2026-08-09."""
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert ":5432" not in dsn

    def test_default_dsn_carries_no_unexpanded_home(self, unconfigured_host):
        """A literal '~' reaching libpq is a lookup for a directory named
        '~'. The default no longer holds a path, so this now pins that it
        did not acquire one."""
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert "~" not in dsn


@pytest.fixture
def durable_socket_dir() -> Path:
    """A socket directory the durability guard accepts on THIS machine.

    The REAL local socket directory, not a ``tmp_path``: that is the target
    the local branch exists to serve, and on a container whose ``/tmp`` is a
    tmpfs the guard refuses ``tmp_path`` and this test would skip everywhere
    while appearing to be written.

    Nothing is created or connected to — ``socket_dsn`` only requires the
    path be absolute. Whether it survives a container rebuild is a property
    of the machine, not of the resolver under test, so the real guard is
    asked rather than rewritten, and the test SKIPS rather than weakens where
    the answer is no.
    """
    directory = DEFAULT_SOCKET_DIR.expanduser()
    try:
        require_durable_pgdata(directory)
    except StoreTargetError:
        pytest.skip(f"{directory} is on an ephemeral filesystem here")
    return directory


class TestTheLocalInstanceIsStillReachable:
    """Demoted from the default, not removed.

    The code that MANAGES this host's Postgres — starts it, checks it,
    replicates from it — wants the local instance and not the fleet's
    centre. Naming `socket_dir` is how it asks, and that branch is also
    where the PGDATA durability guard still lives: it is the one target
    whose storage this process can actually observe.
    """

    def test_an_explicit_socket_dir_resolves_to_the_local_socket(
        self, unconfigured_host, durable_socket_dir
    ):
        # Arrange
        package = "cards"
        # Act
        target = host_store(pkg=package, socket_dir=durable_socket_dir)
        # Assert
        assert is_socket_dsn(target)


@pytest.fixture
def relative_socket_refusal() -> str:
    """The message produced by a relative socket directory.

    The raising call lives here so each test below asserts exactly once —
    a test that both raises and inspects would hide the second check behind
    the first failure.
    """
    with pytest.raises(StoreTargetError) as excinfo:
        socket_dsn(socket_dir="relative/pg")
    return str(excinfo.value)


@pytest.fixture
def path_override_refusal(set_store_override, tmp_path) -> str:
    """The message produced when the override holds a filesystem path."""
    set_store_override(str(tmp_path / "cards.db"))
    with pytest.raises(StoreTargetError) as excinfo:
        host_store(pkg="cards")
    return str(excinfo.value)


class TestRelativeSocketDirectoryIsRefused:
    """libpq resolves a relative host= against CWD — same config, two sockets."""

    def test_a_relative_socket_directory_raises(self):
        # Arrange
        relative = "relative/pg"
        # Act
        # Assert
        with pytest.raises(StoreTargetError):
            socket_dsn(socket_dir=relative)

    def test_the_refusal_explains_the_cwd_hazard(self, relative_socket_refusal):
        # Arrange
        message = relative_socket_refusal
        # Act
        mentions_cwd = "CWD" in message
        # Assert
        assert mentions_cwd


class TestNoSilentFallbackToAPrivateFile:
    """The refusal that keeps a host from quietly writing only to itself.

    A host that fell back to a local file would accept every write, report success,
    and reach nobody — the 2026-08-09 failure reproduced by design.
    """

    def test_a_filesystem_path_in_the_override_is_refused(
        self, set_store_override, tmp_path
    ):
        # Arrange
        set_store_override(str(tmp_path / "cards.db"))
        # Act
        # Assert
        with pytest.raises(StoreTargetError):
            host_store(pkg="cards")

    def test_the_refusal_says_a_path_is_never_accepted(
        self, path_override_refusal
    ):
        """An error that only refuses is half-written.

        There is no other route to offer any more, so the refusal has to say
        that plainly rather than point at one.
        """
        # Arrange
        message = path_override_refusal
        # Act
        rules_out_paths = "not accepted here, or anywhere" in message
        # Assert
        assert rules_out_paths

    def test_the_refusal_shows_the_expected_dsn_shape(self, path_override_refusal):
        # Arrange
        message = path_override_refusal
        # Act
        shows_the_shape = "postgresql://" in message
        # Assert
        assert shows_the_shape

class TestExplicitOverrideWins:
    """An override is honoured outright, including a TCP one."""

    def test_override_dsn_is_used_verbatim(self, set_store_override):
        # Arrange
        dsn = "postgresql://someone@127.0.0.1:55432/scitex"
        set_store_override(dsn)
        # Act
        target = host_store(pkg="cards")
        # Assert
        assert target.dsn == dsn

    def test_a_tcp_override_is_not_reported_as_a_socket(self, set_store_override):
        # Arrange
        set_store_override("postgresql://someone@127.0.0.1:55432/scitex")
        # Act
        target = host_store(pkg="cards")
        # Assert
        assert not is_socket_dsn(target)


class TestOneStoreNotOnePerPackage:
    """Packages share one database; they do not each get one."""

    def test_two_packages_resolve_to_the_same_database(self, unconfigured_host):
        """A per-package database is how four storage locations appeared."""
        # Arrange
        cards = host_store(pkg="cards")
        # Act
        writer = host_store(pkg="writer")
        # Assert
        assert cards.dsn == writer.dsn

    def test_the_asking_package_is_still_recorded_on_the_target(
        self, unconfigured_host
    ):
        # Arrange
        package = "writer"
        # Act
        target = host_store(pkg=package)
        # Assert
        assert target.pkg == package


class TestTheDsnCannotBecomeADirectory:
    """The locator type still refuses the filesystem, on either transport."""

    def test_passing_the_locator_to_path_raises(self, unconfigured_host):
        # Arrange
        target = host_store(pkg="cards")
        # Act
        # Assert
        with pytest.raises(TypeError):
            Path(target.locator)  # type: ignore[arg-type]


class TestTheTestHarnessNeverReachesTheFleetStore:
    """`writable_dsn()` must never hand a test suite the central primary.

    This asserts the property DIRECTLY rather than leaving it to topology. It
    used to hold only by accident: `host_store()` resolved to this host's socket,
    every host's local node is a read-only replica, so the writability check said
    no. Once the default names the central primary that accident is gone, and the
    old route would have yielded the live fleet board to any run with
    SCITEX_STORE_DSN unset.
    """

    def test_writable_dsn_never_yields_the_central_primary(self, unconfigured_host):
        # Arrange
        from scitex_dev.store.testing import writable_dsn

        # Act
        # Whichever way this goes, ONE string carries the verdict: the DSN that
        # was handed over, or the refusal that explains why none was. Collapsing
        # both outcomes into `offered` keeps this to a single assertion, and it
        # widens the check rather than narrowing it — the central host must not
        # appear in the failure text either.
        try:
            with writable_dsn() as dsn:
                offered = dsn
        except RuntimeError as exc:
            offered = str(exc)

        # Assert
        assert DEFAULT_CENTRAL_HOST not in offered

    def test_the_testing_helper_does_not_resolve_the_host_store_at_all(self):
        # Arrange
        import inspect

        from scitex_dev.store import testing as testing_mod

        # Act
        # Comments explaining the removal are expected and fine; a CALL is not,
        # so comment lines are stripped before looking for one.
        source = inspect.getsource(testing_mod.writable_dsn)
        body = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )

        # Assert
        assert "host_store(" not in body

# EOF


class TestTheSocketDsnActuallyReachesTheServer:
    """The step-2 DSN had three faults at once and had never connected.

    Reached only where SCITEX_STORE_DSN is unset, and every working host
    sets it — so nothing exercised this path until sac isolated the faults
    one at a time on 2026-08-20, on compute-04:

        as built          pg/.s.PGSQL.5432       no such file
        directory fixed   pg/run/.s.PGSQL.5432   no such file
        port fixed        pg/.s.PGSQL.55432      no such file
        both + user       pg/run/.s.PGSQL.55432  CONNECTED

    Each test below pins ONE of the three, so a regression names which.
    """

    def test_the_socket_directory_is_the_run_subdirectory(self):
        # Arrange — the socket lives in PGDATA/run, not PGDATA.
        dsn = socket_dsn()
        # Act
        points_at_run = "/pg/run" in dsn
        # Assert
        assert points_at_run

    def test_the_socket_directory_is_expanded_rather_than_left_as_a_tilde(self):
        # Arrange — a literal '~' reaching libpq is a lookup for a directory
        # NAMED '~'. This assertion used to ride on the default resolver; the
        # default no longer holds a path, so it is pinned at its real source.
        dsn = socket_dsn()
        # Act
        expanded = "~" not in dsn
        # Assert
        assert expanded

    def test_the_port_is_carried(self):
        # Arrange — libpq names the socket FILE .s.PGSQL.<port>, so a DSN
        # without the port looks for 5432 and misses a 55432 server.
        dsn = socket_dsn()
        # Act
        carries_port = "port=55432" in dsn
        # Assert
        assert carries_port

    def test_a_user_can_be_carried(self):
        # Arrange — without a role libpq falls back to the OS user and the
        # server answers "fe_sendauth: no password supplied", which names a
        # password problem for a missing role.
        dsn = socket_dsn(user="scitex_cards")
        # Act
        carries_user = dsn.startswith("postgresql://scitex_cards@/")
        # Assert
        assert carries_user

    def test_the_user_is_omitted_when_not_given(self):
        # Arrange — omitted, not empty: libpq then resolves PGUSER itself.
        dsn = socket_dsn()
        # Act
        authority = dsn.split("://", 1)[1].split("/", 1)[0]
        # Assert
        assert authority == ""

    def test_pgdata_and_socket_dir_are_different_paths(self):
        # Arrange — one constant meant both until 2026-08-20, which is what
        # made the DSN point one level too shallow.
        from scitex_dev.store._host import DEFAULT_PGDATA_DIR, DEFAULT_SOCKET_DIR

        # Act
        differ = DEFAULT_SOCKET_DIR != DEFAULT_PGDATA_DIR
        # Assert
        assert differ

    def test_the_socket_dir_is_under_pgdata(self):
        # Arrange
        from scitex_dev.store._host import DEFAULT_PGDATA_DIR, DEFAULT_SOCKET_DIR

        # Act
        parent = DEFAULT_SOCKET_DIR.parent
        # Assert
        assert parent == DEFAULT_PGDATA_DIR

# EOF
