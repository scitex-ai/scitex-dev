#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The host store — which Postgres this host uses, and how it is reached.

This module answers one question: *which store does this host use?* The
answer is a single PostgreSQL instance holding every record kind:
``SCITEX_STORE_DSN`` when the environment names one, otherwise the per-user
LOCAL store (:mod:`._local`). See :func:`host_store`.

No deployment's address is a code default (scitex-dev#1111). Until 0.66.x an
unset DSN resolved to one fleet's central node by its private hostname, so
every PyPI user outside that fleet failed on a host they had never heard of,
and a fresh project on a fleet host wrote into the shared central store. A
deployment names its store in its own environment; the library defaults to a
store the user owns.

Why Postgres, and why only Postgres
-----------------------------------
An earlier draft made a file-backed engine the default on a zero-setup
argument. It was reversed for a reason worth keeping in front of whoever
reads this next: **a database file has no concept of WHO.** Anyone who can
open it has every permission. Postgres has roles, and multi-user identity
cannot be retrofitted onto a file — it is a foundation or it is absent.
Handing a collaborator a database file is SHARING, not COLLABORATING.
ADR-0006 records the decision and the alternatives that were rejected.

Why the socket helper still exists
---------------------------------
:func:`socket_dsn` was once the default and is now the LOCAL-INSTANCE form:
the way to name the Postgres THIS host manages, for the code that manages
it. It keeps the hard-won details — the socket lives in ``PGDATA/run``, and
libpq names the socket FILE ``.s.PGSQL.<port>`` so the port is not optional
even without TCP.

Never 5432, on either transport. On 2026-08-09 ``127.0.0.1:5432`` on one
host looked like a local server and was in fact an SSH tunnel to a laptop.
Nothing about the address said so, and when the laptop rebooted every agent
on every host lost the board at the same instant. An address must be
unambiguous about which Postgres it names; 55432 is how this one is.

A deployment that runs a central writable primary (one cluster with
streaming replicas, where every host's local node is read-only) MUST export
``SCITEX_STORE_DSN`` naming that primary in every process environment. That
is configuration of the deployment, kept in the deployment's environment —
never compiled into this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from ._errors import StoreTargetError
from ._local import local_store_dsn, refuse_if_managed_node
from ._target import Backend, StoreTarget

__all__ = [
    "DEFAULT_PGDATA_DIR",
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

#: Where the per-host instance keeps PGDATA. Bind-mounted OUTSIDE any
#: container, so rebuilding the container destroys no data.
DEFAULT_PGDATA_DIR: Final[Path] = Path("~/.scitex/pg")

#: Where that instance puts its UNIX socket — a SUBDIRECTORY of PGDATA,
#: matching the live `unix_socket_directories` setting.
#:
#: These were one constant until 2026-08-20, and the single name was used
#: for both meanings. The socket is not in PGDATA, it is in PGDATA/run, so
#: every socket DSN this module built pointed one level too shallow and no
#: connection through it ever succeeded. Measured on compute-04: the DSN
#: named `~/.scitex/pg` while the only socket on disk was
#: `~/.scitex/pg/run/.s.PGSQL.55432`.
DEFAULT_SOCKET_DIR: Final[Path] = DEFAULT_PGDATA_DIR / "run"

#: The port this instance listens on. NOT only a TCP concern, which is what
#: the previous comment here claimed: libpq names the socket FILE
#: `.s.PGSQL.<port>`, so a socket DSN that omits the port looks for
#: `.s.PGSQL.5432` and misses a server listening on 55432. That omission was
#: the second of the three faults that kept this path from ever connecting.
#:
#: Never 5432: that buys an omittable port in a connection string and costs
#: a collision with any system Postgres. It confers no auto-start benefit —
#: that comes from the service manager, not from the port number.
DEFAULT_TCP_PORT: Final[int] = 55432

#: The one database every record kind lives in.
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
    a comment, that ``DEFAULT_PGDATA_DIR`` is "bind-mounted OUTSIDE any
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
    directory = Path(pgdata_dir) if pgdata_dir is not None else DEFAULT_PGDATA_DIR
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
    port: int = DEFAULT_TCP_PORT,
    user: "str | None" = None,
) -> str:
    """Build a UNIX-socket DSN for the per-host instance.

    libpq spells a socket connection as a ``host=`` query parameter holding a
    DIRECTORY (it appends ``.s.PGSQL.<port>`` itself). The authority section
    holds the ROLE, or stays empty, which is what makes this a socket rather
    than a TCP DSN::

        postgresql://scitex_cards@/scitex?host=/home/me/.scitex/pg/run&port=55432

    THIS PATH HAD NEVER CONNECTED. It was the step-2 default until
    2026-08-30, reached only where ``SCITEX_STORE_DSN`` is unset, and every
    host that works has step 1 set — so three separate faults sat here
    undetected until sac isolated them one at a time on 2026-08-20:

    ======================  ============================  ================
    DSN as it was built     socket libpq then looked for  result
    ======================  ============================  ================
    (original)              ``pg/.s.PGSQL.5432``          no such file
    directory fixed         ``pg/run/.s.PGSQL.5432``      no such file
    port fixed              ``pg/.s.PGSQL.55432``         no such file
    both + user             ``pg/run/.s.PGSQL.55432``     CONNECTED
    ======================  ============================  ================

    A fallback nobody exercises is not a fallback; it is a branch that has
    never been asked whether it works. Every host reaching step 2 today would
    have failed, and the failure would have read as "Postgres is down".

    ``user`` defaults to ``None``, which lets libpq resolve it (``PGUSER``,
    else the OS user). Passing it explicitly is what the fleet needs when the
    OS user has no role: without one the server answers ``fe_sendauth: no
    password supplied``, which names a password problem for what is really a
    missing role.

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
    authority = f"{user}@" if user else ""
    return f"postgresql://{authority}/{database}?host={resolved}&port={port}"


def host_store(
    *,
    pkg: str,
    name: str = "store",
    database: str = DEFAULT_DATABASE,
    socket_dir: "Path | str | None" = None,
) -> StoreTarget:
    """Resolve THE store for this host. Inert: opens and starts nothing.

    Resolution order — two steps, and no remote host in either:

    1. ``SCITEX_STORE_DSN`` if set — an explicit override wins outright.
       A deployment (a lab server, SciTeX Cloud, a fleet with a central
       primary) names its store HERE, in its own environment.
    2. Otherwise the per-user LOCAL store (:mod:`._local`): a PostgreSQL
       cluster under ``$SCITEX_DIR/store/local`` reached over a 0700 UNIX
       socket. It is initialised and started on the first connect, so a
       researcher who installs from PyPI records provenance with no
       configuration at all.

    Step 2 resolved to one fleet's central node by its private hostname until
    0.66.x (scitex-dev#1111). That made a deployment's address a library
    default: every user outside the fleet failed on a host they had never
    heard of, and a fresh project inside it wrote into the shared store
    without ever naming it.

    **Still no silent fallback.** Step 2 is the DEFAULT, not a degraded mode
    reached when a configured store is unreachable: a set but unreachable
    ``SCITEX_STORE_DSN`` fails at connect time and never falls through. And a
    host that manages a deployment node (``~/.scitex/pg`` exists) is refused
    the local default outright — a process there that lost its DSN would
    otherwise write into a private store that reaches nobody. When the local
    store cannot be created (no server binaries, no UNIX sockets) the connect
    raises :class:`StoreTargetError` naming every way to provide one.

    Passing ``socket_dir`` explicitly resolves to the instance THIS HOST
    MANAGES over its socket (port 55432, ``~/.scitex/pg/run`` by default) —
    for the code that starts, checks or replicates that node. That branch,
    and only that branch, runs the PGDATA durability guard: it is the one
    target whose storage this process can observe.
    """
    override = os.environ.get(STORE_DSN_ENV)
    if override:
        if override.startswith(("postgres://", "postgresql://")):
            return StoreTarget.postgres(override, pkg=pkg, name=name)
        raise StoreTargetError(
            f"{STORE_DSN_ENV}={override!r} is not a Postgres DSN. It must "
            "start with 'postgres://' or 'postgresql://'.\n"
            "\n"
            "A filesystem path is not accepted here, or anywhere: runtime "
            "state lives in PostgreSQL and nowhere else. A path would be a "
            "silent downgrade to a private store that shares nothing.\n"
            "\n"
            "The shape is: postgresql://user@host:port/scitex\n"
            f"Unset it to use your per-user local store: {local_store_dsn()}"
        )
    if socket_dir is not None:
        # Durability is checked exactly where this process can SEE the
        # storage it judges: the instance this host manages (ADR-0006
        # Decision 7). An explicit DSN may name a server elsewhere, and the
        # local default guards its own directory when it initialises it.
        require_durable_pgdata(socket_dir)
        return StoreTarget.postgres(
            socket_dsn(database=database, socket_dir=socket_dir),
            pkg=pkg,
            name=name,
        )
    refuse_if_managed_node()
    return StoreTarget.postgres(
        local_store_dsn(database=database),
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
