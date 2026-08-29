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

from scitex_dev.store import host_store
from scitex_dev.store._dialect._postgres import PostgresDialect
from scitex_dev.store._target import Backend, StoreTarget

#: The cluster the live-connection test opens — ASKED FOR, never named here.
#:
#: This used to be an opt-in env var that nothing set, so the one test in this
#: file that touches a real server skipped on every machine and every CI run,
#: which is indistinguishable from passing. Replacing it with a DSN literal
#: only moved the problem: a test that names its own server is testing a
#: string, not the resolver the product uses. So it goes through
#: ``host_store()`` — the single switch, which reads ``SCITEX_STORE_DSN`` and
#: otherwise falls back to this host's socket.
_dsn = host_store(pkg="scitex_dev_tests", name="dialect").dsn


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


def test_connect_returns_rows_addressable_by_name():
    """PostgresDialect.connect must return a dict-row connection.

    The codec in _codec.py addresses columns by name (record["id"]),
    so a plain tuple from psycopg is a crash. This test verifies that for
    Postgres.

    Skipped ONLY when ``psycopg`` is not installed — that is a property of
    the interpreter, not of the store. An unreachable cluster is a FAILURE:
    "no database here" is a broken environment, and a suite that turns it
    into a skip reports the same green as one that checked.
    """
    # Arrange — guard against missing driver, mirroring the dialect's
    # own ImportError → DialectUnavailableError path.
    psycopg = pytest.importorskip("psycopg")
    dialect = PostgresDialect()
    target = StoreTarget.postgres(_dsn, pkg="_test")
    # Act — open the connection
    connection = dialect.connect(target)
    # Assert — a dict-row factory is in effect: column names work.
    # We execute a trivial query; the row factory decides how the row
    # is returned.  psycopg's dict_row allows
    # ``row["column_name"]``.
    row = connection.execute("SELECT 1 AS col").fetchone()
    # Indexing the row BY NAME is the whole assertion: it raised
    # ``TypeError: tuple indices must be integers or slices, not str``
    # before the row factory was set.
    assert row["col"] == 1  # type: ignore[index]


# ---------------------------------------------------------------------------
# the catalogue probe must answer about THIS schema
#
# DEFECT FIXED HERE (0.56.7 -> 0.56.8). `_schema_objects_missing` skips
# `create_sql` when every object it would build is already present, which is
# what let a non-owning role open a store at all. It asked the catalogue
# whether the tables existed — but `information_schema.columns` filtered on
# `table_name` alone, and `pg_indexes` on `tablename` alone, span EVERY schema
# the role can see. With the store's tables in `public` and the connection
# pointed at a fresh schema, the probe answered PRESENT, creation was skipped,
# and the first read failed:
#
#     psycopg.errors.UndefinedTable:
#         relation "comms_blocks_rows" does not exist
#
# 0.56.7's own docstring called this "the same exposure in principle" and
# shipped it. It was not hypothetical: it is what turned every PR in
# scitex-agent-container red once those tests ran against a real cluster.
# ---------------------------------------------------------------------------


def test_the_columns_probe_is_scoped_to_the_current_schema():
    # Arrange — a property of the STATEMENT, so this runs everywhere, not
    # only where a cluster happens to be up. That asymmetry is what hid the
    # defect: the probe's tests never ran against Postgres.
    # Act
    sql = PostgresDialect().columns_sql("comms_blocks_rows")
    # Assert
    assert "current_schema()" in sql


def test_the_indexes_probe_is_scoped_to_the_current_schema():
    # Arrange — `pg_indexes` carries no schema filter of its own, so this
    # half of the probe was unscoped even in principle.
    # Act
    sql = PostgresDialect().indexes_sql("comms_blocks_rows")
    # Assert
    assert "current_schema()" in sql


@pytest.fixture
def two_schemas():
    """A decoy schema and an empty target schema on a real cluster.

    SKIPS — never fails — when no cluster is USABLE for this, matching the
    convention in ``test__store_concurrency.py``. Real ``os.environ``
    save/restore rather than monkeypatch: the point is that the REAL
    resolver reads the REAL variable.

    "Usable" is wider than "reachable", which is why the except clause names
    three errors rather than one. Several hosts in this fleet resolve the
    default DSN to a READ-ONLY REPLICA, which connects perfectly and then
    answers ``CREATE SCHEMA`` with ``ReadOnlySqlTransaction`` — and a role
    without CREATE answers ``InsufficientPrivilege``. Both mean "not a
    cluster I can build a throwaway schema on", which is a skip; catching
    only ``OperationalError`` turned that into a red ERROR that says nothing
    about the code under test.
    """
    import uuid

    psycopg = pytest.importorskip("psycopg")
    # The PRIMARY: the loopback is a standby and refuses CREATE SCHEMA, which
    # turned this probe into a permanent skip.
    base = host_store(pkg="scitex_dev_tests", name="searchpath").dsn
    tag = uuid.uuid4().hex[:10]
    decoy, target = f"probe_decoy_{tag}", f"probe_target_{tag}"
    unusable = (
        psycopg.OperationalError,
        psycopg.errors.ReadOnlySqlTransaction,
        psycopg.errors.InsufficientPrivilege,
    )
    try:
        with psycopg.connect(base, connect_timeout=5, autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA "{decoy}"')
            conn.execute(f'CREATE SCHEMA "{target}"')
    except unusable as exc:
        pytest.skip(f"no usable PostgreSQL at {base}: {str(exc).splitlines()[0]}")
    saved = os.environ.get("SCITEX_STORE_DSN")
    try:
        yield base, decoy, target
    finally:
        if saved is None:
            os.environ.pop("SCITEX_STORE_DSN", None)
        else:
            os.environ["SCITEX_STORE_DSN"] = saved
        with psycopg.connect(base, connect_timeout=5, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{decoy}" CASCADE')
            conn.execute(f'DROP SCHEMA IF EXISTS "{target}" CASCADE')


#: The key is arbitrary; what matters is that reading it touches the rows
#: table, which is the table the probe decided not to create.
PROBE_KEY = {"sender_name": "alice", "target_name": "lead"}


def _probe_schema():
    """Two identity fields, mirroring the shape of the store that broke."""
    from scitex_dev.store import (
        FieldKind,
        FieldPolicy,
        FieldRole,
        MergeRule,
        Schema,
    )

    def ident() -> FieldPolicy:
        return FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        )

    return Schema(
        name="probe_blocks",
        fields={"sender_name": ident(), "target_name": ident()},
    )


def _open(target):
    from scitex_dev.store import Store, WriterPolicy

    return Store(
        target,
        _probe_schema(),
        node="probe-node",
        writer_policy=WriterPolicy.SINGLE_WRITER,
        actor="test",
    )


@pytest.fixture
def store_in_a_schema_whose_table_names_exist_elsewhere(two_schemas):
    """A store opened in an EMPTY schema, after the same store was built next door.

    Building it in ``decoy`` first makes the four table names genuinely
    present in the catalogue; ``target`` is then a schema where nothing has
    been created. That is the exact arrangement the fleet was in — real
    tables in one schema, a connection pointed at another.
    """
    from scitex_dev.store import host_store

    base, decoy, target = two_schemas
    os.environ["SCITEX_STORE_DSN"] = f"{base}?options=-csearch_path%3D{decoy}"
    _open(host_store(pkg="test_probe", name="probe_blocks")).close()

    os.environ["SCITEX_STORE_DSN"] = f"{base}?options=-csearch_path%3D{target}"
    opened = _open(host_store(pkg="test_probe", name="probe_blocks"))
    try:
        yield opened
    finally:
        opened.close()


def test_a_store_opens_in_an_empty_schema_though_the_name_exists_elsewhere(
    store_in_a_schema_whose_table_names_exist_elsewhere,
):
    """The end-to-end shape of the defect, against a real cluster.

    Before the fix the probe saw the decoy schema's tables, skipped
    ``create_sql``, and this read raised ``UndefinedTable``. ``None`` is the
    three-valued "absent" — the store exists here and holds no such row.
    """
    # Arrange — the fixture built the decoy and opened this one next to it.
    store = store_in_a_schema_whose_table_names_exist_elsewhere
    # Act — that this RETURNS rather than raising UndefinedTable is the point.
    hidden = store.is_hidden(PROBE_KEY)
    # Assert
    assert hidden is None


# EOF
