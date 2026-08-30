#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The host store — which Postgres this host uses, and how it is reached.

This module answers one question: *which store does this host use?* The
answer is a single PostgreSQL instance holding every record kind. As of
2026-08-30 the DEFAULT instance is the fleet's CENTRAL node, reached over
TCP on 55432; see :func:`host_store` for the measurement that forced that
and :data:`DEFAULT_CENTRAL_HOST` for the node.

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

The fleet DOES run a central writable primary
---------------------------------------------
This header used to carry a section titled "Why this is NOT a central
server", arguing that Postgres-by-default meant one Postgres PER HOST and
that a severed host must keep serving its own reads and writes. That is not
the fleet that exists. Measured 2026-08-30, every host's local 55432
answers ``pg_is_in_recovery() = TRUE`` — it is a streaming REPLICA of one
writable primary — and the operator's 2026-08-25 ruling
(「中央はいつもnas03であるべき」, "the centre should ALWAYS be nas-03")
settles the topology as decided rather than open.

ADR-0006 Decisions 3 and 4 still read "NO CENTRAL SERVER … no coordinator,
no quorum, NO PRIMARY" and therefore still contradict both the measurement
and the ruling. Rewriting that ADR is tracked separately on card
``fleet-runs-a-central-writable-primary-that-adr-0006-forbids-20260830``
and is deliberately not done here: this module must not keep asserting, in
its own header, the opposite of what its own code now returns.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from ._errors import StoreTargetError
from ._target import Backend, StoreTarget

__all__ = [
    "DEFAULT_CENTRAL_HOST",
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

#: The fleet's ONE WRITABLE Postgres node — the default target of
#: :func:`host_store` when no override is set.
#:
#: A NAME, not an address, on purpose: the address is an overlay IP that the
#: operator may move, and a DSN that hardcodes one is a DSN that goes stale
#: silently. The name was verified to resolve on compute-01, compute-04,
#: nas-02 and inside an agent container.
#:
#: WHY A CENTRAL NODE AT ALL, given the "one Postgres per host" story this
#: module used to tell. Measured 2026-08-30 from a live container, one query
#: against each target::
#:
#:     scitex-primary:55432   pg_is_in_recovery()=FALSE  addr=100.64.0.5
#:     100.64.0.1:55432       pg_is_in_recovery()=TRUE   addr=100.64.0.1
#:
#: Both reported ``system_identifier=7672112238472680366``. An identical
#: system identifier means ONE cluster with streaming replication, not two
#: independent instances — so every host's local 55432 is a READ-ONLY
#: REPLICA of this node, and ``scitex-primary`` is the only node that can
#: accept a write.
DEFAULT_CENTRAL_HOST: Final[str] = "scitex-primary"

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


def _central_dsn(database: str = DEFAULT_DATABASE) -> str:
    """Build the TCP DSN for the fleet's one writable node.

    Deliberately carries no role: libpq resolves the user from ``PGUSER``
    else the OS user, and ``.pgpass`` matches on that user. Naming one here
    would override a correctly configured host with this module's guess.
    """
    return f"postgresql://{DEFAULT_CENTRAL_HOST}:{DEFAULT_TCP_PORT}/{database}"


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
    2. Otherwise the CENTRAL node, over TCP:
       ``postgresql://scitex-primary:55432/scitex``.

    Step 2 was "the per-host Postgres over its UNIX socket" until 2026-08-30.
    That wording is now FALSE, and it was false in the direction that hurts.

    WHY THE DEFAULT IS THE CENTRAL NODE. There is exactly ONE writable
    Postgres in this fleet. Measured 2026-08-30 from a live container,
    ``scitex-primary:55432`` answers ``pg_is_in_recovery() = FALSE`` while
    every other host's local 55432 answers ``TRUE``, and all of them report
    the SAME ``system_identifier`` — one cluster, streaming replication, one
    primary. The operator's 2026-08-25 ruling
    (「中央はいつもnas03であるべき」, "the centre should ALWAYS be nas-03")
    makes that topology decided rather than open.

    So the old step 2 handed back a READ-ONLY REPLICA. It did so SILENTLY:
    nothing failed at resolve time, nothing failed at connect time, and the
    first sign of trouble was either a write refused deep inside unrelated
    code or — worse — reads that were merely stale forever.

    **There is still deliberately no second tier to fall back to**, and this
    change is that rule applied rather than an exception to it. A fallback
    here would be the worst possible behaviour: a host whose Postgres is not
    reachable would silently start writing to a local file, accept every
    write, report success, and diverge from the fleet with nothing in any log
    to say so. That is the 2026-08-09 failure mode reproduced by design — a
    write that succeeds locally while reaching nobody. Refusing to connect is
    loud, immediate, and fixable; a silent private store is none of those.

    A LOCAL REPLICA IS THAT SAME PROHIBITED BEHAVIOUR wearing better clothes.
    It is a store that cannot keep what it is asked to keep, handed back with
    no error — a wrong answer that looks exactly like a right one. Refusing
    to silently degrade is the whole point of the no-fallback rule, so the
    default must name the node that can actually serve the request.

    Passing ``socket_dir`` explicitly still resolves to the LOCAL instance
    over its socket. That is for the code that MANAGES the local node
    (starting it, checking it, replicating from it), which legitimately wants
    the local instance and not the fleet's centre.

    There is nothing else to resolve to, and that is the design rather than
    an omission: one engine means an unconfigured host has no wrong answer
    available to it.
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
            "state lives in Postgres on 55432 and nowhere else. A path would "
            "be a silent downgrade to a private store that shares nothing.\n"
            "\n"
            f"The default shape is: {_central_dsn()}\n"
            f"For the LOCAL instance over its socket: {socket_dsn()}"
        )
    if socket_dir is not None:
        # THE INSTANCE THIS HOST MANAGES is guarded — not "the socket branch".
        # The criterion is OBSERVABILITY, not transport: check durability
        # exactly when this process can see the storage it is judging. An
        # explicit SCITEX_STORE_DSN may point at a Postgres elsewhere whose
        # storage this process cannot see, so checking OUR filesystem would
        # say nothing about ITS durability — a check that cannot observe the
        # thing it judges is the shape that was being fixed here.
        #
        # WORDED THIS WAY DELIBERATELY (ADR-0006 Decision 7, reversed
        # 2026-08-10). This guard was written when the socket WAS the local
        # instance, so "socket branch" and "instance we manage" were the same
        # set. Decision 7 makes TCP on 55432 the default and splits them. The
        # guard belongs to the SECOND set. Whoever changes the DSN this branch
        # returns must keep the call: a durability guard silently disarmed by
        # an unrelated transport decision is the exact failure this ADR keeps
        # cataloguing.
        #
        # ---- 2026-08-30, ANSWERING THE PARAGRAPH ABOVE ON ITS OWN TERMS ----
        # The DSN this function returns BY DEFAULT has now changed, and the
        # instruction above is honoured rather than dodged: the guard is kept,
        # and it is kept attached to the set it was declared to belong to —
        # THE INSTANCE THIS HOST MANAGES. What changed is that the DEFAULT no
        # longer RESOLVES to that instance, so the two sets, already split
        # conceptually by Decision 7, are now split in the code as well.
        #
        # An explicit `socket_dir` is the caller naming the local instance,
        # which this process CAN observe — the guard's own criterion is met,
        # so it runs, exactly as before, and every existing test of it fires
        # through this branch unchanged.
        #
        # The default branch below does NOT call it, and that is the same
        # criterion applied, not an exemption from it. This process cannot see
        # `scitex-primary`'s PGDATA, so judging OUR local filesystem would say
        # nothing whatsoever about the durability of the node we are about to
        # connect to — a check that cannot observe what it judges, which is
        # precisely what the paragraph above forbids. Worse, it would raise on
        # a host running no Postgres at all and block a perfectly valid
        # central connection: a guard that becomes the outage.
        #
        # WHERE THIS GUARD PROBABLY BELONGS, stated and NOT acted on here: in
        # the code that STARTS and MANAGES the local node, which is the only
        # code that both owns that PGDATA and can see it. `host_store()` is a
        # resolver; a resolver checking a filesystem is how the guard ended up
        # coupled to a transport in the first place. That refactor is out of
        # scope for this change and must not be smuggled into it.
        require_durable_pgdata(socket_dir)
        return StoreTarget.postgres(
            socket_dsn(database=database, socket_dir=socket_dir),
            pkg=pkg,
            name=name,
        )
    return StoreTarget.postgres(
        _central_dsn(database),
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
