#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The host store — one Postgres per host, reached over a UNIX socket.

This module answers one question: *which store does this host use?* Per
ADR-0006, the answer is a single PostgreSQL instance belonging to this host,
holding every record kind, reached over a UNIX socket rather than a TCP port.

Why Postgres is the default
---------------------------
The earlier draft made SQLite the default on a zero-setup argument. It was
reversed for a reason worth keeping in front of whoever reads this next:
**SQLite has no concept of WHO.** Anyone who can open the file has every
permission. Postgres has roles, and multi-user identity cannot be retrofitted
onto a file — it is a foundation or it is absent. Handing a collaborator a
database file is SHARING, not COLLABORATING.

Why a socket, not a port
------------------------
Hosts never connect to each other's Postgres. Replication exchanges oplogs at
the application layer (see :mod:`._replication`), so each instance is only
ever reached from its own host and a TCP port buys nothing. Dropping it means
port collisions cannot happen, an address cannot be ambiguous about which
Postgres it names, and the instance is not exposed to the network at all.

That ambiguity was live on 2026-08-09: ``127.0.0.1:5432`` on one host looked
like a local server and was in fact an SSH tunnel to a laptop. Nothing about
the address said so, and when the laptop rebooted every agent on every host
lost the board at the same instant.

Why this is NOT a central server
--------------------------------
"Postgres by default" means one Postgres PER HOST. It does not mean one
Postgres that every host connects to. Centralisation caused the outage above;
choosing Postgres prevents no repeat of it. A severed host must keep serving
reads and writes from its own instance, and reconcile later.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from ._errors import StoreTargetError
from ._target import Backend, StoreTarget

__all__ = [
    "DEFAULT_SOCKET_DIR",
    "DEFAULT_TCP_PORT",
    "STORE_DSN_ENV",
    "host_store",
    "socket_dsn",
]

#: Explicit override. An operator or test sets this and it wins outright —
#: no merging with the defaults below, because a half-honoured override is
#: harder to reason about than either extreme.
STORE_DSN_ENV: Final[str] = "SCITEX_STORE_DSN"

#: Where the per-host instance keeps PGDATA and its socket. Bind-mounted
#: OUTSIDE any container, so rebuilding the container destroys no data.
DEFAULT_SOCKET_DIR: Final[Path] = Path("~/.scitex/pg")

#: Used ONLY when someone opts into TCP (a GUI client, debugging). Never
#: 5432: that buys an omittable port in a connection string and costs a
#: collision with any system Postgres. It confers no auto-start benefit —
#: that comes from the service manager, not from the port number.
DEFAULT_TCP_PORT: Final[int] = 55432

#: The one database every record kind lives in on this host.
DEFAULT_DATABASE: Final[str] = "scitex"


def socket_dsn(
    *,
    database: str = DEFAULT_DATABASE,
    socket_dir: "Path | str | None" = None,
) -> str:
    """Build a UNIX-socket DSN for the per-host instance.

    libpq spells a socket connection as a ``host=`` query parameter holding a
    DIRECTORY (it appends ``.s.PGSQL.<port>`` itself). The authority section
    stays empty, which is what makes this a socket rather than a TCP DSN::

        postgresql:///scitex?host=/home/me/.scitex/pg

    The directory is expanded here rather than at connect time so that a
    misconfigured ``~`` fails while the DSN is being built, naming the value,
    instead of surfacing later as a connection refusal that says nothing
    about why.
    """
    directory = Path(socket_dir) if socket_dir is not None else DEFAULT_SOCKET_DIR
    resolved = directory.expanduser()
    if not resolved.is_absolute():
        raise StoreTargetError(
            f"The Postgres socket directory must be absolute, got {directory!s} "
            f"(expanded to {resolved!s}). libpq resolves a relative host= "
            "against the process CWD, so the same configuration would connect "
            "to different sockets depending on where the process was started."
        )
    return f"postgresql:///{database}?host={resolved}"


def host_store(
    *,
    pkg: str,
    name: str = "store",
    database: str = DEFAULT_DATABASE,
    socket_dir: "Path | str | None" = None,
) -> StoreTarget:
    """Resolve THE store for this host.

    Resolution order, and there are only two steps because a third would be a
    place for a wrong answer to hide:

    1. ``SCITEX_STORE_DSN`` if set — an explicit override wins outright.
    2. Otherwise the per-host Postgres over its UNIX socket.

    **There is deliberately no SQLite fallback.** A fallback here would be the
    worst possible behaviour: a host whose Postgres is not running would
    silently start writing to a local file, accept every write, report success,
    and diverge from the fleet with nothing in any log to say so. That is the
    2026-08-09 failure mode reproduced by design — a write that succeeds
    locally while reaching nobody. Refusing to connect is loud, immediate, and
    fixable; a silent private store is none of those.

    SQLite remains fully implemented behind the dialect layer and is reachable
    with an explicit :meth:`StoreTarget.sqlite`. It is simply not what an
    unconfigured host resolves to.
    """
    override = os.environ.get(STORE_DSN_ENV)
    if override:
        if override.startswith(("postgres://", "postgresql://")):
            return StoreTarget.postgres(override, pkg=pkg, name=name)
        raise StoreTargetError(
            f"{STORE_DSN_ENV}={override!r} is not a Postgres DSN. It must "
            "start with 'postgres://' or 'postgresql://'.\n"
            "\n"
            "If you meant a SQLite file, this variable is not the way to ask "
            "for one — an unconfigured host resolves to Postgres by design, "
            "and a path here would be a silent downgrade to a private store. "
            "Construct it explicitly instead: "
            "StoreTarget.sqlite(<path>, pkg=...).\n"
            "\n"
            f"For a socket connection the shape is: {socket_dsn()}"
        )
    return StoreTarget.postgres(
        socket_dsn(database=database, socket_dir=socket_dir),
        pkg=pkg,
        name=name,
    )


def is_socket_dsn(target: StoreTarget) -> bool:
    """Whether ``target`` reaches Postgres over a UNIX socket.

    True when the DSN carries a ``host=`` pointing at a directory and no TCP
    authority. Useful for a diagnostic that wants to say *how* a store is
    reached, not merely which one it is.
    """
    if target.backend is not Backend.POSTGRES:
        return False
    dsn = target.dsn or ""
    return "host=/" in dsn


# EOF
