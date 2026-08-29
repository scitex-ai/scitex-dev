#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A Postgres DSN must never be usable as a filesystem path.

The measured failure, reported by scitex-cards: directory trees on a live
host named ``postgresql:/<user>@<host>:<port>/runtime/todo.db``, each a real
file that nothing reads. They are what ``Path("postgresql://...")``
produces when something ``mkdir``s it relative to the process CWD — the DSN
is not rejected, it is accepted as a relative path.

**Two of them, not the thirteen first reported** — scitex-db caught that the
original count walked one directory through thirteen symlinks. The accurate
number is used here on purpose: an inflated one invites the next reader to
check, find two, and discount the finding.

The argument was never the count. It is the SPREAD: three separate sites
made the same mistake in a single day, which is enough to stop treating it
as carelessness. A ``str`` locator WILL be passed to ``Path()``, because a
string that describes a location is indistinguishable from a path to every
API that takes one.

So the guard is a TYPE, and these tests assert the misuse raises rather
than that a convention is documented.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scitex_dev.store import StoreTarget, StoreTargetError
from scitex_dev.store._locator import PostgresDsn
from scitex_dev.store._target import Backend

DSN = "postgresql://scitex_cards:hunter2@127.0.0.1:5432/cards"


@pytest.fixture
def pg_target() -> StoreTarget:
    """A Postgres target, as a leaf package would construct one."""
    return StoreTarget.postgres(DSN, pkg="cards")


@pytest.fixture
def path_error(pg_target) -> str:
    """The message raised when the DSN locator reaches the filesystem API.

    Via ``os.fspath`` rather than ``Path``, deliberately. Both REFUSE — the
    guard holds either way, which is what the separate raise-tests cover —
    but ``pathlib`` catches ``TypeError`` from ``__fspath__`` and substitutes
    its own generic message, so our explanation only survives on the direct
    route. Asserting the message through ``Path`` would be asserting
    pathlib's wording, not ours.
    """
    try:
        os.fspath(pg_target.locator)
    except TypeError as exc:
        return str(exc)
    raise AssertionError("os.fspath(dsn_locator) did not raise — the guard is gone")


def test_passing_a_dsn_locator_to_path_raises(pg_target):
    """``Path(locator)`` must fail rather than build a relative path."""
    # Arrange
    locator = pg_target.locator

    # Act
    def act() -> None:
        Path(locator)

    # Assert
    with pytest.raises(TypeError):
        act()


def test_passing_a_dsn_locator_to_fspath_raises(pg_target):
    """Everything in the filesystem API routes through ``os.fspath``."""
    # Arrange
    locator = pg_target.locator

    # Act
    def act() -> None:
        os.fspath(locator)

    # Assert
    with pytest.raises(TypeError):
        act()


def test_passing_a_dsn_locator_to_open_raises(pg_target):
    """``open()`` is the other way a locator reaches the filesystem."""
    # Arrange
    locator = pg_target.locator

    # Act
    def act() -> None:
        open(locator)

    # Assert
    with pytest.raises(TypeError):
        act()


def test_the_path_error_names_the_measured_incident(path_error):
    """The message must teach, not just refuse. Constitution §2."""
    # Arrange
    expected = "runtime/todo.db"

    # Act
    message = path_error

    # Assert
    assert expected in message


def test_the_path_error_does_not_cite_the_retracted_count(path_error):
    """The inflated 13 must not survive anywhere a reader will trust it.

    scitex-db caught that the original count walked one directory through
    thirteen symlinks. A refuted number left in a permanent error message
    is worse than no number: the next reader checks, finds two, and stops
    believing the rest of the message.
    """
    # Arrange
    retracted = "13 directory trees"

    # Act
    message = path_error

    # Assert
    assert retracted not in message


def test_the_path_error_points_at_the_named_accessor(path_error):
    """It must say what to use INSTEAD, or the reader guesses."""
    # Arrange
    expected = "target.dsn"

    # Act
    message = path_error

    # Assert
    assert expected in message


def test_the_target_itself_is_not_path_like(pg_target):
    """``Path(target)`` must fail too — the wrapper is not an escape hatch."""
    # Arrange
    target = pg_target

    # Act
    def act() -> None:
        Path(target)

    # Assert
    with pytest.raises(TypeError):
        act()


def test_a_string_locator_is_refused_at_construction():
    """The old stringly-typed shape must not be constructible."""
    # Arrange
    kwargs = dict(backend=Backend.POSTGRES, locator=DSN, pkg="cards", name="store")

    # Act
    def act() -> None:
        StoreTarget(**kwargs)

    # Assert
    with pytest.raises(StoreTargetError):
        act()


def test_the_dsn_is_available_when_asked_for_by_name(pg_target):
    """Refusing path use must not make the DSN unreachable."""
    # Arrange
    expected = DSN

    # Act
    actual = pg_target.dsn

    # Assert
    assert actual == expected


def test_str_of_a_dsn_does_not_leak_the_password(pg_target):
    """A DSN interpolated into a log line must not carry credentials."""
    # Arrange
    secret = "hunter2"

    # Act
    rendered = str(pg_target.locator)

    # Assert
    assert secret not in rendered


def test_describe_does_not_leak_the_password(pg_target):
    """``describe()`` goes into card notes, so it must be safe too."""
    # Arrange
    secret = "hunter2"

    # Act
    rendered = pg_target.describe()

    # Assert
    assert secret not in rendered


def test_exists_is_unknown_rather_than_false_for_postgres(pg_target):
    """Three-valued: answering would require connecting, so say so."""
    # Arrange
    target = pg_target

    # Act
    actual = target.exists()

    # Assert
    assert actual is None


def test_a_dsn_without_a_scheme_is_refused():
    """A bare host would be read as a path by some drivers."""
    # Arrange
    bad = "127.0.0.1:5432/cards"

    # Act
    def act() -> None:
        PostgresDsn(bad)

    # Assert
    with pytest.raises(ValueError):
        act()

# EOF
