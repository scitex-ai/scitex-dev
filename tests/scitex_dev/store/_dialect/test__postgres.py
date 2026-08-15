#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Postgres instance discriminator — what it is made of, and why.

DEFECT FIXED HERE. The pair was ``(store_uuid, cluster system_identifier)``,
and it cannot separate two stores on the same engine at different paths: a
``pg_dump`` restored into a second database on the SAME cluster copies the
``store_uuid`` and shares the cluster id, so the pair certifies SAME while
the two databases accept writes independently and diverge. That is the
2026-08-11 failure with a shorter blast radius, and certifying it would be
worse than not checking, because the check would be believed.

These tests do not need a live cluster, deliberately. The defect was a
MISSING COLUMN in one statement and a missing component in one identifier —
both are properties of the code, and a test that only ran where Postgres
happened to be up would not have caught it on the machine where it was
written.

WHY THE LIVE-CONNECTION TEST IS `skipif` DECORATED. The test function
``test_connect_returns_rows_addressable_by_name`` opens a real connection to
Postgres, so it needs the driver AND a DSN pointing at a reachable instance.
Declaring the preconditions as module-level ``pytest.mark.skipif`` decorators
keeps them visible at collection time as properties of the test, which is
what they are — rather than burying a runtime ``pytest.skip`` inside the body
where a reader finds it only after the setup.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev.store._dialect._postgres import PostgresDialect
from scitex_dev.store._target import Backend, StoreTarget

#: Guard for ``test_connect_returns_rows_addressable_by_name``.
#: Both the driver and a reachable DSN are required; the test is skipped
#: when either is missing.
_needs_dsn = os.environ.get("SCITEX_STORE_TEST_DSN")
needs_dsn = pytest.mark.skipif(
    _needs_dsn is None,
    reason=(
        "SCITEX_STORE_TEST_DSN is not set — no Postgres DSN "
        "pointing at a reachable instance to connect to"
    ),
)


def test_the_identity_statement_asks_which_cluster():
    # Arrange — the cluster id is minted at initdb and identifies the
    # INSTALLATION, so it survives a pg_dump into a different cluster.
    # Act
    sql = PostgresDialect.IDENTITY_SQL
    # Assert
    assert "pg_control_system()" in sql


def test_the_identity_statement_asks_which_database():
    # Arrange — THE FIX. Without this column the discriminator is
    # cluster-wide and two databases on one cluster are indistinguishable.
    # Act
    sql = PostgresDialect.IDENTITY_SQL
    # Assert
    assert "current_database()" in sql


def test_the_instance_id_carries_both_parts():
    # Arrange
    # Act
    got = PostgresDialect.format_instance_id("7100", "scitex")
    # Assert
    assert got == "pg:7100/scitex"


def test_two_databases_on_one_cluster_get_different_instance_ids():
    # Arrange — the measured case: one cluster, one store_uuid copied into
    # a second database. This is the comparison that used to say SAME.
    original = PostgresDialect.format_instance_id("7100", "scitex")
    # Act
    restored = PostgresDialect.format_instance_id("7100", "scitex_restored")
    # Assert
    assert original != restored


def test_two_clusters_hosting_the_same_database_name_differ():
    # Arrange — the database name ALONE would not have been enough either;
    # every host in this fleet calls its database `scitex`.
    here = PostgresDialect.format_instance_id("7100", "scitex")
    # Act
    there = PostgresDialect.format_instance_id("7200", "scitex")
    # Assert
    assert here != there


def test_two_routes_into_one_database_agree():
    # Arrange — the property that keeps this usable. A socket, a TCP port
    # and an SSH tunnel are ROUTES; keying identity on the address would
    # report a fork between two views of one store every time. Neither
    # component here is derived from the connection string.
    socket_route = PostgresDialect.format_instance_id("7100", "scitex")
    # Act
    tunnel_route = PostgresDialect.format_instance_id("7100", "scitex")
    # Assert
    assert socket_route == tunnel_route


@needs_dsn
def test_connect_returns_rows_addressable_by_name():
    """PostgresDialect.connect must return a dict-row connection.

    The codec in _codec.py addresses columns by name (record["id"]),
    so a plain tuple from psycopg is a crash. The SQLite dialect
    guarantees this via sqlite3.Row; this test verifies the same for
    Postgres.

    Skipped when ``psycopg`` is not installed — the driver is required
    for this test to run, just as it is for the dialect itself.
    Also skipped when ``SCITEX_STORE_TEST_DSN`` is not set — the test
    connects to a real Postgres instance, and neither CI nor a generic
    developer machine has one reachable.
    """
    # Arrange — guard against missing driver, mirroring the dialect's
    # own ImportError → DialectUnavailableError path.
    psycopg = pytest.importorskip("psycopg")
    dialect = PostgresDialect()
    # skipif above guarantees _needs_dsn is not None here
    target = StoreTarget.postgres(
        _needs_dsn,  # type: ignore[arg-type]
        pkg="_test",
    )
    # Act — open the connection
    connection = dialect.connect(target)
    # Assert — a dict-row factory is in effect: column names work.
    # We execute a trivial query; the row factory decides how the row
    # is returned.  sqlite3.Row and psycopg's dict_row both allow
    # ``row["column_name"]``.
    row = connection.execute("SELECT 1 AS col").fetchone()
    # Indexing the row BY NAME is the whole assertion: it raised
    # ``TypeError: tuple indices must be integers or slices, not str``
    # before the row factory was set.
    assert row["col"] == 1  # type: ignore[index]


# EOF
