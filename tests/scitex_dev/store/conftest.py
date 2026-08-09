#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real replicas on real engines. Nothing here is mocked.

Every test in this package runs TWICE: once against a real SQLite file
and once against a real PostgreSQL schema. That is not thoroughness for
its own sake -- two fatal defects in this house passed 196 tests and
appeared only against a live driver, because a stand-in answers the
question you thought you asked instead of the one the engine answers.

PostgreSQL is addressed by DSN in ``$SCITEX_DEV_STORE_TEST_DSN``. When it
is absent the PostgreSQL half SKIPS, and a skip is a hole in the
evidence, not a pass -- so ``$SCITEX_DEV_STORE_REQUIRE_PG=1`` turns that
skip into a FAILURE for any environment that is supposed to have one.
Each replica gets its own throwaway schema (dropped afterwards), so two
"hosts" can share one server without sharing any state.
"""

from __future__ import annotations

import os
import uuid

import pytest

from scitex_dev.store._oplog_dialect import POSTGRES, SQLITE, OplogTarget, connect
from scitex_dev.store._oplog_store import OpLogStore

#: libpq DSN of a REAL PostgreSQL the suite may create throwaway schemas in.
PG_DSN_ENV = "SCITEX_DEV_STORE_TEST_DSN"

#: Set to 1 where a PostgreSQL is guaranteed; turns "skipped" into "failed"
#: so the suite cannot go green by never having run half of itself.
PG_REQUIRED_ENV = "SCITEX_DEV_STORE_REQUIRE_PG"

TABLE = "notes"


def pg_dsn() -> str:
    return os.environ.get(PG_DSN_ENV, "").strip()


def require_pg_or_skip() -> str:
    dsn = pg_dsn()
    if dsn:
        return dsn
    message = (
        "no real PostgreSQL configured: set {0} to a libpq DSN. "
        "This half of the evidence did NOT run.".format(PG_DSN_ENV)
    )
    if os.environ.get(PG_REQUIRED_ENV, "").strip() in ("1", "true", "yes"):
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(params=[SQLITE, POSTGRES])
def dialect(request):
    """Run every test against both engines."""
    yield request.param


@pytest.fixture
def make_store(dialect, tmp_path):
    """Factory for independent replicas that share nothing but the engine."""
    run_id = uuid.uuid4().hex[:10]
    stores = []
    schemas = []

    def _make(origin: str, **kwargs) -> OpLogStore:
        if dialect == SQLITE:
            target = OplogTarget(SQLITE, str(tmp_path / (origin + ".sqlite3")))
        else:
            schema = "stx_t_{0}_{1}".format(run_id, origin)
            schemas.append(schema)
            target = OplogTarget(POSTGRES, require_pg_or_skip(), namespace=schema)
        store = OpLogStore(target, origin, **kwargs)
        stores.append(store)
        return store

    yield _make

    for store in stores:
        try:
            store.close()
        except Exception:
            pass
    if schemas:
        conn = connect(OplogTarget(POSTGRES, pg_dsn()))
        for schema in schemas:
            conn.execute("DROP SCHEMA IF EXISTS {0} CASCADE".format(schema))
        conn.commit()
        conn.close()


@pytest.fixture
def store(make_store):
    """A single replica named ``alpha``."""
    yield make_store("alpha")


@pytest.fixture
def pair(make_store):
    """Two live replicas, ``alpha`` and ``beta``, that have never talked."""
    yield make_store("alpha"), make_store("beta")


def drop_op(store: OpLogStore, origin: str, seq: int) -> None:
    """Delete one op from a log to simulate LOSS in transit or on disk.

    Surgery, deliberately available only to tests: the production surface
    has no way to remove an op, because the log is append-only.
    """
    store._exec(
        "DELETE FROM stx_oplog WHERE origin = ? AND seq = ?", (origin, int(seq))
    )
    store._conn.commit()


def inject_op(store: OpLogStore, entry) -> None:
    """Write an op straight into a log, bypassing the fence check.

    Models the one thing the API cannot produce on purpose: a DEMOTED
    writer whose ops are still sitting in a log somewhere, waiting to be
    replayed as though they were current.
    """
    store._exec(
        "INSERT INTO stx_oplog "
        "(origin, seq, table_name, record_key, op, payload, fence, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        entry.as_row(),
    )
    store._conn.commit()


def live_payloads(store: OpLogStore) -> dict:
    """``{record_key: payload}`` for the records that are not tombstoned."""
    return {row[1]: row[2] for row in store.snapshot() if row[3] == 0}


# EOF
