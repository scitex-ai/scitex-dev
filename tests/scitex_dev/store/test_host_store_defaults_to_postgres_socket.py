#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The host store resolves to Postgres over a socket, and never falls back.

These lock the ADR-0006 decisions that are cheapest to erode later: the
default engine, the absence of a TCP port, and — the one that matters most —
that a host with no Postgres gets an ERROR rather than a private SQLite file
nobody else can see.

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
    DEFAULT_TCP_PORT,
    STORE_DSN_ENV,
    is_socket_dsn,
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


class TestDefaultIsPostgresOverASocket:
    """An unconfigured host resolves to its own Postgres, via a socket."""

    def test_default_backend_is_postgres(self, unconfigured_host):
        # Arrange
        package = "cards"
        # Act
        target = host_store(pkg=package)
        # Assert
        assert target.backend is Backend.POSTGRES

    def test_default_dsn_points_at_a_socket_directory(self, unconfigured_host):
        # Arrange
        package = "cards"
        # Act
        target = host_store(pkg=package)
        # Assert
        assert is_socket_dsn(target)

    def test_default_dsn_does_not_carry_the_postgres_default_port(
        self, unconfigured_host
    ):
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert ":5432" not in dsn

    def test_default_dsn_does_not_carry_the_opt_in_tcp_port_either(
        self, unconfigured_host
    ):
        """A socket has no port at all — not even ours."""
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert f":{DEFAULT_TCP_PORT}" not in dsn

    def test_socket_directory_is_expanded_rather_than_left_as_a_tilde(
        self, unconfigured_host
    ):
        """A literal '~' would make libpq look for a directory named '~'."""
        # Arrange
        package = "cards"
        # Act
        dsn = host_store(pkg=package).dsn or ""
        # Assert
        assert "~" not in dsn


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

    A host that fell back to SQLite would accept every write, report success,
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

    def test_the_refusal_names_the_explicit_sqlite_route(
        self, path_override_refusal
    ):
        """An error that only refuses is half-written."""
        # Arrange
        message = path_override_refusal
        # Act
        names_the_route = "StoreTarget.sqlite" in message
        # Assert
        assert names_the_route

    def test_the_refusal_shows_the_expected_dsn_shape(self, path_override_refusal):
        # Arrange
        message = path_override_refusal
        # Act
        shows_the_shape = "postgresql://" in message
        # Assert
        assert shows_the_shape

    def test_sqlite_remains_reachable_when_asked_for_explicitly(self, tmp_path):
        """Not deprecated — just not what an unconfigured host resolves to."""
        # Arrange
        path = tmp_path / "cards.db"
        # Act
        target = StoreTarget.sqlite(path, pkg="cards")
        # Assert
        assert target.backend is Backend.SQLITE


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


class TestOneStorePerHostNotPerPackage:
    """Packages share the host's database; they do not each get one."""

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


class TestTheSocketDsnCannotBecomeADirectory:
    """The locator type still refuses the filesystem, socket DSN included."""

    def test_passing_the_locator_to_path_raises(self, unconfigured_host):
        # Arrange
        target = host_store(pkg="cards")
        # Act
        # Assert
        with pytest.raises(TypeError):
            Path(target.locator)  # type: ignore[arg-type]

    def test_a_socket_target_reports_itself_as_not_file_backed(
        self, unconfigured_host
    ):
        # Arrange
        target = host_store(pkg="cards")
        # Act
        file_backed = target.is_file_backed
        # Assert
        assert not file_backed

    def test_a_socket_target_has_no_path(self, unconfigured_host):
        # Arrange
        target = host_store(pkg="cards")
        # Act
        path = target.path
        # Assert
        assert path is None


# EOF
