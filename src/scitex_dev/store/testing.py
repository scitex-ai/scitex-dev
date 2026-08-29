#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""An ephemeral store, so a consumer can test the code that uses one.

WHY THIS MODULE EXISTS. Three packages hit the same wall on the same day —
2026-08-29 — and each diagnosed it independently before comparing notes:

  scitex-scholar  "No ephemeral/test target — the sharpest one. A package
                   whose CI runs off-fleet cannot test ANY store-touching
                   path." It shipped with its store round-trips verified by
                   hand rather than by the suite.
  scitex-writer   "No hermetic test backend. Each consumer must copy sac's
                   ~200-line pg_schema fixture."
  scitex-dev      Its own CI could not run the store suite at all: the runner
                   is refused by the primary with `fe_sendauth: no password
                   supplied`, and the instance on the runner's own host is a
                   read-only standby, so `CREATE SCHEMA` raises there.

Before the second engine was removed, a test could open a throwaway
file-backed store and that was the affordance. Removing the engine removed
the affordance, and nothing replaced it — so the honest reading is that this
module is part of that removal rather than a new feature.

WHAT IT DOES NOT DO. It does not weaken the rule it serves. There is still
one storage engine; this hands out a real PostgreSQL, either a throwaway
SCHEMA on a cluster you already have or a whole throwaway CLUSTER started for
the test session and thrown away after. Nothing here is a fake, a stub or an
in-memory shim: a test that passes against this passes against the engine
that ships.

THE ORDER OF PREFERENCE IS DELIBERATE:

  1. ``SCITEX_STORE_DSN`` if it names a WRITABLE cluster — reuse what the
     caller already configured, because the fewer moving parts a test starts,
     the fewer ways it can pass for the wrong reason.
  2. otherwise a private cluster via ``initdb``, if the binaries are present.
  3. otherwise SKIP, naming both routes and how to get either.

Step 1 checks ``pg_is_in_recovery()`` rather than assuming. A standby accepts
the connection and refuses the DDL, which is exactly the shape that made this
suite report green while running nothing.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Iterator

from ._host import STORE_DSN_ENV, host_store

__all__ = [
    "ephemeral_cluster_dsn",
    "ephemeral_schema",
    "writable_dsn",
]

#: How long to wait for a freshly started postmaster to accept connections.
_START_TIMEOUT_SECONDS = 30.0


def _writability(dsn: str) -> "tuple[bool, str]":
    """Whether ``dsn`` accepts writes, AND THE REASON IT DOES NOT.

    Returns the reason rather than a bare bool because the three ways this
    fails need three different repairs, and a caller that collapses them
    reports the wrong one. An earlier version of this module did exactly
    that: its refusal told the reader "a standby answers pg_is_in_recovery()
    = true" whenever any route failed — including when the connection had
    never been established. An error that states an unmeasured cause sends
    the next person to fix the wrong thing.

      unreachable  -> the address, the port, the firewall, the credential
      read-only    -> the address is right and points at the wrong ROLE
      no driver    -> the interpreter, not the database
    """
    try:
        import psycopg
    except ImportError:  # pragma: no cover - callers importorskip first
        return False, "the psycopg driver is not installed"
    try:
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
            in_recovery = conn.execute("SELECT pg_is_in_recovery()").fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - report it, do not guess at it
        return False, f"unreachable: {str(exc).splitlines()[0][:120]}"
    if in_recovery:
        return False, "reachable but READ-ONLY (pg_is_in_recovery() is true)"
    return True, "writable"


def _is_writable(dsn: str) -> bool:
    """Whether ``dsn`` accepts writes. See :func:`_writability` for why not."""
    return _writability(dsn)[0]


def _pg_bin(name: str) -> "str | None":
    """Locate a PostgreSQL binary, including the Debian versioned layout.

    Debian and Ubuntu keep ``initdb`` and ``pg_ctl`` out of PATH under
    ``/usr/lib/postgresql/<major>/bin``, so a plain ``which`` reports them
    absent on hosts that are in fact running PostgreSQL — which is every host
    in this fleet.
    """
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(
        Path("/usr/lib/postgresql").glob(f"*/bin/{name}"),
        key=lambda p: p.parts[-3],
        reverse=True,
    )
    return str(candidates[0]) if candidates else None


@contextlib.contextmanager
def ephemeral_cluster_dsn() -> Iterator[str]:
    """Start a private PostgreSQL, yield its DSN, and destroy it after.

    The cluster lives in a temporary directory, listens on a UNIX socket in
    that same directory (so it cannot collide with a real instance on a port,
    and needs no password because peer auth applies), and is removed on exit
    whether or not the test passed.

    Raises ``RuntimeError`` when the binaries are absent — the caller decides
    whether that is a skip or a failure, because the answer differs by
    package. Do not turn it into a skip here.
    """
    initdb, pg_ctl = _pg_bin("initdb"), _pg_bin("pg_ctl")
    if not initdb or not pg_ctl:
        raise RuntimeError(
            "PostgreSQL server binaries (initdb, pg_ctl) are not installed, so "
            "no throwaway cluster can be started. Install the server package "
            "(Debian/Ubuntu: `postgresql`), or point "
            f"{STORE_DSN_ENV} at a writable cluster."
        )

    root = Path(tempfile.mkdtemp(prefix="scitex-store-test-"))
    data, sock = root / "data", root / "run"
    sock.mkdir()
    try:
        subprocess.run(
            [initdb, "-D", str(data), "-A", "trust", "--encoding=UTF8", "-U", "postgres"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            [pg_ctl, "-D", str(data), "-o", f"-k {sock} -h ''", "-w",
             "-t", str(int(_START_TIMEOUT_SECONDS)), "start"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        dsn = f"postgresql://postgres@/postgres?host={sock}"
        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while not _is_writable(dsn):
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"a throwaway cluster started under {root} but never "
                    "accepted a writable connection"
                )
            time.sleep(0.2)
        yield dsn
    finally:
        with contextlib.suppress(Exception):
            subprocess.run([pg_ctl, "-D", str(data), "-m", "immediate", "stop"],
                           capture_output=True, timeout=60)
        shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def writable_dsn() -> Iterator[str]:
    """A DSN that is known to accept writes, by whichever route works.

    Prefers whatever the caller already configured; falls back to a private
    cluster. Raises ``RuntimeError`` if neither is available, naming both
    routes — the caller turns that into a skip or a failure.
    """
    tried: list[str] = []

    configured = os.environ.get(STORE_DSN_ENV)
    if configured:
        ok, why = _writability(configured)
        if ok:
            yield configured
            return
        tried.append(f"  {STORE_DSN_ENV}={configured} — {why}")
    else:
        tried.append(f"  {STORE_DSN_ENV} is unset")

    resolved = host_store(pkg="scitex_dev", name="testing").dsn
    # Only a SECOND route if the override did not already decide it —
    # host_store returns the override verbatim when one is set, and listing
    # one DSN twice reads as two independent checks having failed.
    if resolved != configured:
        ok, why = _writability(resolved)
        if ok:
            yield resolved
            return
        tried.append(f"  this host's store {resolved} — {why}")

    try:
        with ephemeral_cluster_dsn() as dsn:
            yield dsn
    except RuntimeError as exc:
        tried.append(f"  a throwaway cluster — {exc}")
        raise RuntimeError(
            "No writable PostgreSQL is available for tests. Every route was "
            "tried and each is reported with the reason it was measured to "
            "fail, not a presumed one:\n" + "\n".join(tried)
        ) from None


@contextlib.contextmanager
def ephemeral_schema(dsn: str, *, prefix: str = "test") -> Iterator[str]:
    """Create a uniquely named schema on ``dsn``, yield a DSN scoped to it.

    The yielded DSN carries ``search_path``, so an unqualified ``CREATE
    TABLE`` lands inside the schema and the whole thing is removed by one
    ``DROP SCHEMA ... CASCADE``. That is what keeps a test off the live store
    without needing a second database.
    """
    import psycopg

    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{name}"')
    try:
        joiner = "&" if "?" in dsn else "?"
        yield f"{dsn}{joiner}options=-csearch_path%3D{name}"
    finally:
        with contextlib.suppress(Exception):
            with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
                conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')

# EOF
