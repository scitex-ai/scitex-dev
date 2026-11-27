"""The throwaway cluster must not flush to the shared disk.

These start a real PostgreSQL through ``ephemeral_cluster_dsn`` and ask the
running server for its settings, so they verify what the server actually runs
with, not the argv we meant to pass. The CI image installs the server binaries
(see ``ci/runner/containers/ci-cpu.def``); on a host without them the helper
raises ``RuntimeError`` and these tests fail loudly rather than skip.
"""

import pytest
from scitex_dev.store.testing import ephemeral_cluster_dsn

psycopg = pytest.importorskip("psycopg")


def _setting(dsn: str, name: str) -> str:
    with psycopg.connect(dsn) as conn:
        return conn.execute(f"SHOW {name}").fetchone()[0]


@pytest.mark.parametrize("name", ["fsync", "synchronous_commit", "full_page_writes"])
def test_server_runs_non_durable(name):
    # Arrange
    cluster = ephemeral_cluster_dsn()
    # Act
    with cluster as dsn:
        value = _setting(dsn, name)
    # Assert
    assert value == "off"


def test_cluster_still_accepts_writes():
    # Arrange
    with ephemeral_cluster_dsn() as dsn, psycopg.connect(dsn) as conn:
        conn.execute("CREATE TABLE t (x int)")
        conn.execute("INSERT INTO t VALUES (42)")
        # Act
        got = conn.execute("SELECT x FROM t").fetchone()[0]
    # Assert
    assert got == 42
