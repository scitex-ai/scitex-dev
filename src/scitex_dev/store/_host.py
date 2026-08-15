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
    "require_durable_pgdata",
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

#: Filesystem types that DO NOT SURVIVE a container rebuild. A store whose
#: PGDATA sits on one of these accepts every write, reports success, and
#: loses all of it the moment the image is rebuilt.
#:
#: Measured on scitex-compute-04, 2026-08-10:
#:     /home/ywatanabe   ext4                  <- host bind, survives
#:     /                 fuse.fuse-overlayfs   <- container-local, does not
_EPHEMERAL_FSTYPES: Final[frozenset[str]] = frozenset(
    {"overlay", "overlayfs", "fuse.fuse-overlayfs", "fuse-overlayfs", "tmpfs"}
)


def _fstype_from_mountinfo(table: str, probe: Path) -> "str | None":
    """Filesystem type covering ``probe``, read out of a mountinfo ``table``.

    Split out of ``_fstype_of`` so the longest-match rule can be exercised
    against a CONSTRUCTED mount table. Asked of the host's own table, the
    rule is only testable where the host happens to have a nested mount:
    on a machine whose ``$HOME`` shares the root filesystem there is
    nothing to discriminate, and a test written that way reports the
    machine's layout rather than this function's behaviour (measured
    2026-08-12, when CI moved from Spartan to the scitex-compute nodes and
    exactly that test failed while the rule below was perfectly correct).

    Returns None when nothing matches; the caller treats that as "cannot
    determine" rather than as either verdict.
    """
    best_len = -1
    best_type: "str | None" = None
    for line in table.splitlines():
        # ... <mount-point> ... - <fstype> <source> <opts>
        head, sep, tail = line.partition(" - ")
        if not sep:
            continue
        fields = head.split()
        rest = tail.split()
        if len(fields) < 5 or not rest:
            continue
        mount_point, fstype = fields[4], rest[0]
        try:
            probe.relative_to(mount_point)
        except ValueError:
            continue
        # Longest matching mount point wins: /home/x beats / for /home/x/y.
        if len(mount_point) > best_len:
            best_len, best_type = len(mount_point), fstype
    return best_type


def _fstype_of(path: Path) -> "str | None":
    """Filesystem type of the mount covering ``path``, or None if unknown.

    Reads ``/proc/self/mountinfo`` rather than shelling out to ``findmnt``:
    this runs on the store's startup path, and a subprocess there is both
    slower and one more thing that can be absent from a container image —
    which would be an ironic way for a container-detection check to fail.

    Returns None when the mount table is unreadable or nothing matches, and
    the caller treats that as "cannot determine" rather than as either
    verdict. A durability check that guesses is worse than one that abstains
    and says so.
    """
    try:
        raw = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError:
        return None

    # Walk up until we hit a directory that exists — PGDATA may not have
    # been created yet, and the question is about the filesystem it WOULD
    # land on, not about the leaf.
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent

    return _fstype_from_mountinfo(raw, probe)


def require_durable_pgdata(pgdata_dir: "Path | str | None" = None) -> None:
    """Refuse a store whose PGDATA would not survive a container rebuild.

    The parameter is ``pgdata_dir``, NOT ``socket_dir``, and the difference
    is deliberate (ADR-0006 Decision 7, reversed 2026-08-10). This guard was
    written when the socket directory and PGDATA were the same path, so
    naming it after the socket cost nothing. Decision 7 makes TCP on 55432
    the default and separates the two concepts: PGDATA is where the data
    lives, the socket is one way to reach it, and a transport change must not
    be able to take the durability check with it.

    A guard whose input is named after a transport is a guard that disappears
    when the transport does — silently, and with nothing failing to say so.

    WHY THIS RAISES RATHER THAN WARNS. Until 2026-08-10 the module said, in
    a comment, that ``DEFAULT_SOCKET_DIR`` is "bind-mounted OUTSIDE any
    container, so rebuilding the container destroys no data". Nothing
    verified it. The operator caught that in review and was right to: a
    comment states an intention and cannot notice when the intention fails.

    If the path resolves container-local — and ``$HOME`` is ``/home/agent``
    inside these containers while the bind lives under the host's home —
    the store comes up, works perfectly, and every write is destroyed at the
    next image rebuild, with no error and no warning at any point.

    A warning would be the wrong instrument. The same night this was found,
    four days of Telegram silence had gone unnoticed because every check
    available was advisory and every one of them said healthy. For a
    data-durability property the only honest response is to refuse to start:
    a store that cannot keep what it accepts must not accept it.

    Abstains when the filesystem cannot be determined. "Cannot tell" is not
    "unsafe", and blocking every host whose mount table is unreadable would
    make the guard the outage.
    """
    directory = Path(pgdata_dir) if pgdata_dir is not None else DEFAULT_SOCKET_DIR
    resolved = directory.expanduser()
    fstype = _fstype_of(resolved)
    if fstype is None or fstype not in _EPHEMERAL_FSTYPES:
        return
    raise StoreTargetError(
        f"PGDATA would live on a {fstype!r} filesystem at {resolved!s}, which "
        "DOES NOT SURVIVE a container rebuild. Every write would succeed and "
        "then be destroyed with the image.\n"
        "\n"
        f"Resolved from: {directory!s}  (HOME={os.environ.get('HOME', '?')})\n"
        "\n"
        "Both halves are shown because this fails when $HOME differs between "
        "the host and the container: the path is right for the author's "
        "machine and container-local everywhere else.\n"
        "\n"
        "FIX: bind-mount the host directory into the container so the store "
        "outlives it, e.g. the host's ~/.scitex mounted at the same path. "
        "Verify with `findmnt -T <path>` — a host bind reports ext4 or "
        "similar; a container-local path reports an overlay.\n"
        "\n"
        "This refuses rather than warns on purpose. A warning on a durability "
        "property is the instrument that lets silent data loss look healthy."
    )


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
    # THE INSTANCE THIS HOST MANAGES is guarded — not "the socket branch".
    # The criterion is OBSERVABILITY, not transport: check durability exactly
    # when this process can see the storage it is judging. An explicit
    # SCITEX_STORE_DSN may point at a Postgres elsewhere whose storage this
    # process cannot see, so checking OUR filesystem would say nothing about
    # ITS durability — a check that cannot observe the thing it judges is the
    # shape being fixed here.
    #
    # WORDED THIS WAY DELIBERATELY (ADR-0006 Decision 7, reversed 2026-08-10).
    # This guard was written when the socket WAS the local instance, so
    # "socket branch" and "instance we manage" were the same set. Decision 7
    # makes TCP on 55432 the default and splits them. The guard belongs to the
    # SECOND set. Whoever changes the DSN this branch returns must keep the
    # call: a durability guard silently disarmed by an unrelated transport
    # decision is the exact failure this ADR keeps cataloguing.
    require_durable_pgdata(socket_dir)
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
