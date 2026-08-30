#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Store identity — telling "you are me" from "you descend from me".

The question this answers
------------------------
Two processes each hold an open store. Both report the same ``store_uuid``.
Are they talking to the SAME database, or to two databases that were once
one?

Until this module the fleet could not tell, and answered wrong. On
2026-08-11 ``scitex-compute-04`` reached two Postgres instances — its own on
port 55432, and, through an SSH tunnel presented as ``127.0.0.1:5442``, the
NAS's. Both reported ``store_uuid 1d55dd6e-3d2a-4c24-a429-a78835ab988f``.
404 cards existed only on the first and 146 only on the second. Every
operation on both succeeded.

**A uuid stored inside a database cannot detect a fork of that database,**
because the fork copies the uuid along with everything else. Asking it
"who are you?" gets the honest answer of a thing that genuinely believes it
is the original — and so does the other one.

The fix: identity is a PAIR
---------------------------
:class:`StoreIdentity` is ``(store_uuid, system_identifier)``.

``store_uuid`` is the LINEAGE. It is minted once, lives in the store's own
tables, and survives copying, dumping, restoring and forking. Two stores
sharing it are related. That is all it can say, and it is worth saying:
a *different* uuid proves the two are unrelated, which is a real answer.

``system_identifier`` is the INSTANCE. It is asked of the serving system at
connect time and is deliberately NOT read back from the store's own rows —
that is the whole point. A value carried inside the data is copied with the
data; a value asked of the machine is not.

It names the instance DOWN TO THE CONTAINER holding the rows, not merely
the engine: ``pg:<cluster>/<database>``. The engine alone would be too
coarse and the gap is a real one — a
``pg_dump`` restored into a second database on the SAME cluster copies the
``store_uuid`` and shares the cluster id, so an engine-only pair certifies
SAME while the two halves diverge. What is added is a NAME asked of the
engine, never a route: see "Why not derive the instance id from the DSN"
below, which is the same distinction from the other side.

    same uuid + same system id      -> the same store
    same uuid + different system id -> a FORK. Related, diverging, and the
                                       exact 2026-08-11 shape.
    different uuid                  -> unrelated stores
    either system id unknown        -> NOT CERTIFIED. See below.

Unknown is a fourth answer, not a third
---------------------------------------
Some systems will not tell us. A Postgres role without rights to
``pg_control_system()`` is the common case, and the honest response is
``UNKNOWN_SYSTEM`` — never a fabricated discriminator and never a
best-effort guess.

:func:`assert_same_store` then REFUSES TO CERTIFY rather than passing. It
raises :class:`~._errors.StoreIdentityUnknownError`, which is a different
error from a detected fork because the remedies differ: a fork needs
reconciliation, an unknown needs a grant. What it must never do is return
quietly, because "we could not check" reported as "checked, fine" is the
class of failure this whole module exists to end — the operator's framing:
*every operation reports success.*

Why not derive the instance id from the DSN
-------------------------------------------
Tempting, and wrong in both directions. The 2026-08-11 case had two DSNs
(``:55432`` and ``:5442``) reaching two instances, so DSN-difference would
have been right there. But a tunnel, a socket path and a TCP port routinely
name the SAME instance — an agent reaching the host store over
``postgresql:///scitex?host=/home/me/.scitex/pg`` and another reaching it on
``127.0.0.1:55432`` are on one database. Keying identity on the address
would report a fork between two views of one store, every time.

A false fork alarm is worse than no alarm: it trains its readers to ignore
it, and then the true one goes unread too.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from ._errors import StoreIdentityMismatchError, StoreIdentityUnknownError

__all__ = [
    "IdentityVerdict",
    "StoreIdentity",
    "UNKNOWN_SYSTEM",
    "assert_same_store",
    "compare_identity",
]

#: The ``system_identifier`` of a system that would not tell us which
#: instance it is. NOT an empty string and not ``None``: both read as
#: falsey, and every falsey-check in the fleet would then treat "we could
#: not determine the instance" as "there is no instance", which is the
#: silent-success shape being removed here.
UNKNOWN_SYSTEM: Final[str] = "unknown"


class IdentityVerdict(str, Enum):
    """The four answers comparing two store identities can give.

    Four, not two. A boolean ``same/different`` would fold FORK together
    with UNRELATED — but a fork needs reconciling and an unrelated store
    needs the caller to stop pointing at it, and it would fold UNKNOWN in
    with one of them, which is how "we did not check" becomes "we checked".
    """

    #: Same lineage, same instance. One database, two connections.
    SAME = "same"
    #: Same lineage, DIFFERENT instance. Two databases that were once one.
    FORK = "fork"
    #: Different lineage. Nothing to reconcile; someone is misconfigured.
    UNRELATED = "unrelated"
    #: At least one side would not name its instance. Nothing is proven.
    UNKNOWN = "unknown"

    @property
    def is_certified_same(self) -> bool:
        """Whether this verdict PROVES the two are one store.

        Only :attr:`SAME` does. Written as a property rather than left to
        each caller's ``== SAME`` because ``!= FORK`` reads as if it means
        the same thing and does not: it admits UNKNOWN.
        """
        return self is IdentityVerdict.SAME


@dataclass(frozen=True, slots=True)
class StoreIdentity:
    """Who a store is: its lineage, and the instance serving it.

    ``system_source`` records HOW the instance id was obtained — a control
    file, a socket directory, a device/inode pair. It is carried because
    two identities are only comparable when they were measured the same
    way, and because an operator reading a fork report needs to know what
    the claim rests on.
    """

    store_uuid: str
    system_identifier: str
    system_source: str = ""

    def __post_init__(self) -> None:
        if not self.store_uuid:
            raise StoreIdentityUnknownError(
                "StoreIdentity requires a store_uuid. An empty lineage makes "
                "every store look unrelated to every other, so nothing would "
                "ever be reconciled and no fork could ever be reported."
            )
        if not self.system_identifier:
            raise StoreIdentityUnknownError(
                "StoreIdentity requires a system_identifier; pass "
                f"UNKNOWN_SYSTEM ({UNKNOWN_SYSTEM!r}) when the serving system "
                "would not name itself. An empty string is falsey and would "
                "let 'we could not determine the instance' be read as 'there "
                "is no instance' by any truthiness check that sees it."
            )

    @property
    def system_known(self) -> bool:
        """Whether the serving instance named itself."""
        return self.system_identifier != UNKNOWN_SYSTEM

    def describe(self) -> str:
        """One line for logs, card notes and error messages."""
        instance = (
            self.system_identifier
            if self.system_known
            else f"{UNKNOWN_SYSTEM} (instance would not identify itself)"
        )
        source = f" via {self.system_source}" if self.system_source else ""
        return f"store {self.store_uuid} on instance {instance}{source}"


def compare_identity(left: StoreIdentity, right: StoreIdentity) -> IdentityVerdict:
    """Classify two identities. Pure — reads nothing, raises nothing.

    The ordering of the checks matters. UNRELATED is decided FIRST, because
    two stores with different lineages are not a fork however their
    instances compare, and reporting a fork there would send the reader
    looking for a reconciliation that must not happen.

    UNKNOWN is decided SECOND, before SAME. Two identities can agree on
    every field while both fields say ``unknown``, and calling that SAME
    would certify sameness from two absences of evidence.
    """
    if left.store_uuid != right.store_uuid:
        return IdentityVerdict.UNRELATED
    if not (left.system_known and right.system_known):
        return IdentityVerdict.UNKNOWN
    if left.system_identifier == right.system_identifier:
        return IdentityVerdict.SAME
    return IdentityVerdict.FORK


def assert_same_store(
    left: StoreIdentity,
    right: StoreIdentity,
    *,
    context: str = "",
) -> None:
    """Refuse to continue unless ``left`` and ``right`` are ONE store.

    This is the loud half. Everything else in this module answers a
    question; this one stops a caller that was about to act on a wrong
    answer — an ack written to the store the poll did not read, a card
    closed where nobody will see it.

    ``context`` is the caller's own description of what it was about to do.
    It is prepended verbatim, because "these are two stores" is far less
    useful to whoever reads the traceback than "acking notification n-83
    for agent X: these are two stores".

    Raises :class:`~._errors.StoreIdentityMismatchError` for FORK and
    UNRELATED, and :class:`~._errors.StoreIdentityUnknownError` for UNKNOWN.
    Distinct types, because the remedies are distinct: reconcile,
    reconfigure, and grant respectively.
    """
    verdict = compare_identity(left, right)
    if verdict.is_certified_same:
        return

    prefix = f"{context}: " if context else ""

    if verdict is IdentityVerdict.UNKNOWN:
        raise StoreIdentityUnknownError(
            f"{prefix}cannot certify that these are the same store.\n"
            f"  here:  {left.describe()}\n"
            f"  there: {right.describe()}\n"
            "\n"
            "They share a lineage, but at least one instance would not name "
            "itself, so 'same store' is unproven rather than false. This "
            "refuses instead of passing, because a check that reports "
            "'could not verify' as 'verified' is the failure being removed: "
            "the 2026-08-11 split was invisible precisely because every "
            "operation on both halves reported success.\n"
            "\n"
            "Remedy (Postgres): grant the connecting role permission to read "
            "the cluster identity — GRANT EXECUTE ON FUNCTION "
            "pg_control_system() TO <role>, or add it to pg_monitor. "
            "Verify by re-reading Store.identity: system_identifier must "
            "stop being 'unknown'."
        )

    if verdict is IdentityVerdict.UNRELATED:
        raise StoreIdentityMismatchError(
            f"{prefix}these are UNRELATED stores, not two views of one.\n"
            f"  here:  {left.describe()}\n"
            f"  there: {right.describe()}\n"
            "\n"
            "The lineages differ, so there is no shared history and nothing "
            "to reconcile. Replaying one into the other would fold two "
            "unrelated datasets together on recency and report success.\n"
            "\n"
            "Remedy: one of the two targets is wrong. Check which store each "
            "side resolved to — the target is reported by "
            "StoreTarget.describe() — and point the misconfigured one at the "
            "store it was meant to use."
        )

    raise StoreIdentityMismatchError(
        f"{prefix}these are a FORK of one store: same lineage, different "
        "instances.\n"
        f"  here:  {left.describe()}\n"
        f"  there: {right.describe()}\n"
        "\n"
        "Both descend from one store and both have been accepting writes, "
        "so each holds records the other has never seen. Nothing errors on "
        "either side — this is the 2026-08-11 shape, where one host reached "
        "its own Postgres and, through a tunnel, another host's, and 404 "
        "cards existed on only one of them while every read, write and ack "
        "reported success.\n"
        "\n"
        "Remedy: do NOT copy rows between them and do NOT reconcile by "
        "comparing what each side HAS — absence in one is not deletion in "
        "the other, and acting as if it were destroyed 2,159 rows on "
        "2026-07-19/21. Reconcile by replaying the oplogs in both directions "
        "(scitex_dev.store.sync), which converges them without ever "
        "inferring anything from absence."
    )

# EOF
