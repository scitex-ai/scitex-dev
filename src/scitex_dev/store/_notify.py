#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The push-notification CONTRACT: a doorbell, never a delivery mechanism.

``scitex_dev.store`` converges by RECONCILING SWEEP — each node pulls a peer's
oplog from its own cursor and :func:`scitex_dev.store._replication.replay`
refuses any batch that is not gapless. That is the only path by which data
arrives, and it is correct with no notifications at all.

This module adds a DOORBELL on top: a hint that says "there is something to
pull", so a sweep runs in seconds instead of at the next tick. It never carries
data, and nothing here can make the sweep unnecessary.

WHY A HINT AND NOT THE DATA — measured, not reasoned
-----------------------------------------------------
scitex-cards measured PostgreSQL ``LISTEN``/``NOTIFY`` on the live store,
2026-08-15::

    delivery latency                              0.38 ms
    notifications surviving a disconnected listener  0 of 3

**Notifications are lost, routinely, and nothing reports it.** So:

* a HINT payload means a lost notification costs LATENCY — the sweep still
  finds the ops by cursor;
* a DATA payload would mean a lost notification is LOST DATA.

Degrade to slow, never to wrong. The same rule decided the fleet's CI runner
default the same morning: hosted degrades to slower, self-hosted degrades to
never.

A data payload would also create a SECOND ingestion path — one that never
passes ``replay``'s ``first_seq == cursor + 1`` assertion. Two paths where only
one is checked is precisely the defect shape fixed in the audit gate that week
(``skip-rules`` masked on the strict path and not on the path CI ran).

And ``NOTIFY``'s payload ceiling is 8000 bytes, so a data payload that fits
today's rows truncates silently on the first large one.

WHY THE NOTIFY MUST BE INSIDE THE WRITING TRANSACTION
------------------------------------------------------
scitex-cards also measured that a ``NOTIFY`` issued in a transaction that ROLLS
BACK is **not delivered** (0 of N). That makes the doorbell transactional: a
hint can never be AHEAD of the data.

That property is load-bearing, not incidental. Without it a node could announce
``max_seq = N``, roll back, and leave every listener asking forever for an op
that does not exist. Because it holds, the emit can sit directly on the write
path and needs no outbox to keep it honest.

**So: emit inside the same transaction as the oplog append. Never in an
after-commit hook, never from a background drainer.** Moving it out reintroduces
the phantom-hint class, and this docstring is where the next reader learns why
the placement was not arbitrary.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
------------------------------------------
``LISTEN``/``NOTIFY`` is PER-DATABASE — it does not cross hosts. Under the
fleet's one-Postgres-per-host architecture (ADR-0006), a notify on one machine
is invisible to another unless something holds a connection between them. This
module defines the CHANNEL and PAYLOAD only; carrying a hint between hosts is a
relay's job and is deliberately absent here.

That distinction matters because the incident this work came from was
CROSS-HOST: a DM written on one machine, read on another, five minutes behind,
and the reader concluded the messaging rail was dead. An intra-host doorbell
would have been instant for readers who were not the ones complaining.
"""

from __future__ import annotations

from typing import Final, NamedTuple

#: Channel name prefix. The schema is appended, so one store == one channel.
#:
#: ONE CHANNEL PER STORE, NOT PER ORIGIN — and the difference is a real failure.
#: A per-origin channel requires a listener to know the origin set in ADVANCE in
#: order to subscribe, so a NEW peer's first write is heard by nobody. That
#: failure is silent and lands exactly on the case the doorbell exists for: a
#: host joining. The origin travels in the payload instead, where it costs
#: nothing.
_CHANNEL_PREFIX: Final[str] = "scitex_store_"

#: `NOTIFY`'s documented payload ceiling. Enforced here rather than discovered
#: in production, because the failure is a truncated hint that still looks like
#: a hint.
_MAX_PAYLOAD_BYTES: Final[int] = 8000


class Hint(NamedTuple):
    """A decoded doorbell payload: WHOSE oplog advanced, and HOW FAR.

    Deliberately not a dataclass carrying the ops themselves. A listener may
    use ``origin`` to prioritise which peer to sweep first and ``max_seq`` to
    skip a sweep it can prove is redundant — and nothing else. Applying
    anything from a hint is a contract violation, because hints are lost.
    """

    origin: str
    max_seq: int


def channel_for(schema_name: str) -> str:
    """Return the LISTEN/NOTIFY channel for a store.

    Parameters
    ----------
    schema_name : str
        The store's schema name, e.g. ``"public"``.
    """
    return f"{_CHANNEL_PREFIX}{schema_name}"


def encode_hint(origin: str, max_seq: int) -> str:
    """Render a hint payload, refusing anything ambiguous to decode.

    ``origin`` may not contain ``":"``: the payload is split on the FIRST colon,
    so an origin containing one would decode to a different origin and a
    mangled sequence rather than failing. A wrong-but-parseable hint is worse
    than a rejected one — it would send a listener sweeping a peer that does
    not exist while the real peer waits for the next tick.
    """
    if not origin:
        raise ValueError("hint origin must be a non-empty node id")
    if ":" in origin:
        raise ValueError(
            f"hint origin may not contain ':' (got {origin!r}) — the payload is "
            "split on the first colon, so such an origin decodes to a "
            "different node rather than failing"
        )
    if max_seq < 0:
        raise ValueError(f"hint max_seq must be >= 0 (got {max_seq})")
    payload = f"{origin}:{max_seq}"
    encoded = len(payload.encode("utf-8"))
    if encoded > _MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"hint payload is {encoded} bytes, over NOTIFY's "
            f"{_MAX_PAYLOAD_BYTES}-byte ceiling — a truncated hint still looks "
            "like a hint, so this refuses rather than sending one"
        )
    return payload


def decode_hint(payload: str) -> Hint | None:
    """Parse a payload, returning ``None`` for anything unrecognised.

    RETURNS ``None`` RATHER THAN RAISING, and that is deliberate. A listener
    receives whatever is on the channel, including payloads from a future
    version of this contract. Raising would kill the listener — and a dead
    listener stops sweeping, converting a cosmetic incompatibility into a
    convergence failure.

    ``None`` means "I could not read this hint", which a caller should treat
    exactly like a hint it never received: sweep anyway. Unreadable and absent
    are the same state here, and both are safe, because the sweep is what
    actually delivers.
    """
    origin, sep, raw_seq = payload.partition(":")
    if not sep or not origin:
        return None
    try:
        max_seq = int(raw_seq)
    except ValueError:
        return None
    if max_seq < 0:
        return None
    return Hint(origin=origin, max_seq=max_seq)


# EOF
