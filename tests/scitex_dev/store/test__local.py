#!/usr/bin/env python3
"""The per-user local store really comes up, holds records, and says why not.

scitex-dev#1111: an unconfigured machine must record provenance with no
configuration. These run the REAL path — ``initdb``, ``pg_ctl``, a Store
round-trip through :func:`host_store` — in a throwaway ``SCITEX_DIR``, and
skip only where no PostgreSQL server binaries exist at all.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from scitex_dev.store import (
    NEW_RECORD,
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    WriterPolicy,
    host_store,
)
from scitex_dev.store._errors import StoreTargetError
from scitex_dev.store._host import STORE_DSN_ENV
from scitex_dev.store._local import (
    _no_binaries_error,
    ensure_local_store,
    local_store_dir,
    pg_bin,
)

_ISOLATED_VARS = (STORE_DSN_ENV, "HOME", "SCITEX_DIR")


@pytest.fixture
def fresh_machine(tmp_path) -> Iterator[Path]:
    """No DSN, an empty HOME and SCITEX_DIR; the cluster is stopped after."""
    saved = {key: os.environ.get(key) for key in _ISOLATED_VARS}
    os.environ.pop(STORE_DSN_ENV, None)
    os.environ["HOME"] = str(tmp_path / "home")
    os.environ["SCITEX_DIR"] = str(tmp_path / "home" / ".scitex")
    try:
        yield tmp_path
    finally:
        pg_ctl = pg_bin("pg_ctl")
        pgdata = local_store_dir() / "pgdata"
        if pg_ctl and pgdata.exists():
            subprocess.run(
                [pg_ctl, "-D", str(pgdata), "-m", "immediate", "stop"],
                check=False,
                capture_output=True,
                timeout=60,
            )
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def server_binaries() -> None:
    if not (pg_bin("initdb") and pg_bin("pg_ctl")):
        pytest.skip("no PostgreSQL server binaries on this machine")
    pytest.importorskip("psycopg")


def _schema() -> Schema:
    return Schema.build(
        "localprobe",
        {
            "id": FieldPolicy(
                kind=FieldKind.TEXT,
                role=FieldRole.IDENTITY,
                required=True,
                merge=MergeRule.IMMUTABLE,
                indexed=False,
            ),
            "status": FieldPolicy(
                kind=FieldKind.TEXT,
                role=FieldRole.DATA,
                required=True,
                merge=MergeRule.LAST_WRITER_WINS,
                indexed=True,
            ),
        },
    )


class TestTheLocalStoreComesUpOnFirstConnect:
    def test_a_record_written_through_the_default_reads_back(
        self, fresh_machine, server_binaries
    ):
        # Arrange
        store = Store(
            host_store(pkg="localprobe"),
            _schema(),
            node="test-node",
            writer_policy=WriterPolicy.MULTI_WRITER,
        )
        store.put({"id": "c1", "status": "open"}, expected_revision=NEW_RECORD)
        # Act
        try:
            values = store.get({"id": "c1"}).values
        finally:
            store.close()
        # Assert
        assert values == {"id": "c1", "status": "open"}

    def test_a_second_ensure_is_idempotent(self, fresh_machine, server_binaries):
        # Arrange
        first = ensure_local_store()
        # Act
        second = ensure_local_store()
        # Assert
        assert first == second

    def test_the_store_directory_is_private_to_its_user(
        self, fresh_machine, server_binaries
    ):
        # Arrange
        ensure_local_store()
        # Act
        mode = local_store_dir().stat().st_mode & 0o777
        # Assert
        assert mode == 0o700


class TestAStoreThatCannotBeMadeFailsLoudly:
    def test_the_refusal_names_every_way_to_get_binaries(self):
        # Arrange
        message = str(_no_binaries_error())
        # Act
        named = all(
            hint in message
            for hint in (
                "scitex-dev[local-store]",
                "apt install postgresql",
                "brew install",
                "conda install",
                "SCITEX_STORE_DSN",
            )
        )
        # Assert
        assert named

    def test_a_managed_node_is_refused_at_connect_too(self, fresh_machine):
        # Arrange
        (fresh_machine / "home" / ".scitex" / "pg").mkdir(parents=True)
        # Act
        # Assert
        with pytest.raises(StoreTargetError, match="SCITEX_STORE_DSN"):
            ensure_local_store()


# EOF
