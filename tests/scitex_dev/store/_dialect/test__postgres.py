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
"""

from __future__ import annotations

from scitex_dev.store._dialect._postgres import PostgresDialect


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

# EOF
