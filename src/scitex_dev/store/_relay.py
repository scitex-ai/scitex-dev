#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carrying a doorbell hint ACROSS HOSTS, which ``LISTEN``/``NOTIFY`` cannot.

:mod:`._notify` defines the doorbell; it is per-DATABASE, so a hint rung on
one machine is inaudible on every other. That gap is not academic — the
incident this work came from was cross-host, and the operator named the
requirement in one line (2026-08-15)::

    エージェントがカードで私にdmしたら即座に私に届かないといけないし逆もそう

A DM written by an agent on ``scitex-compute-04`` must reach the operator's
laptop AT ONCE, and the reverse. This module is what carries it.

THE SHAPE, AND THE MEASUREMENT THAT FORCED IT
----------------------------------------------
Measured 2026-08-15 between ``scitex-compute-04`` and ``ywata-note-win``::

    laptop postgres bind      127.0.0.1 only, on all of 5432/15432/55432
    ssh, both directions      works, key-based, no prompt

**The laptop's database is unreachable from any other machine.** So a relay
that opens a connection to a peer's Postgres cannot work for the one
destination the operator actually asked about. Nor for ``scitex-nas-03``,
which has no overlay membership at all and only LAN ssh.

So the fan-out inverts. Each host:

1. LISTENs on its OWN store — local credentials, which every host already has;
2. rings each PEER over ssh, executing ``pg_notify`` in the peer's OWN
   database, with the peer's OWN local credentials.

**No database credential ever crosses a host boundary**, which is a security
property obtained for free by taking the only route that works at all. And the
receiving side needs NO new daemon: the ring lands on the peer's normal
channel, where its existing listeners already wait.

HOLD THE SSH CHANNEL OPEN
--------------------------
Measured the same day, same pair, three rings each::

    fresh ssh connection per ring     425-485 ms
    multiplexed (ControlPersist)       79-91 ms

Five times. A relay that spawns a bare ``ssh`` per hint spends its whole
budget on key exchange, so :class:`~._relay_ssh.SshPsqlTransport` multiplexes
by default and this docstring is why.

(One-way latency is deliberately NOT quoted anywhere in this package. The two
clocks differ by ~0.57 s, measured — larger than the quantity itself, so any
one-way figure would be reporting the skew. Delivery is proven by payload
identity and order instead; speed is quoted as the ring cost, which is timed
on a single clock.)

WHAT THIS IS NOT
-----------------
NOT a delivery guarantee, exactly as :mod:`._notify` is not. Hints are lost
routinely; a relayed hint adds ssh, a second host and a second Postgres to the
list of things that can drop it. **The reconciling sweep remains the only path
by which data arrives**, and removing it because the relay "works" would turn
every relay outage into silent divergence rather than into slowness.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, Sequence

from ._notify import Hint, channel_for, encode_hint


class TransportError(RuntimeError):
    """A peer could not be rung. Carries WHY, because the reason is the point.

    A relay that cannot reach a peer must say which peer and what happened.
    The failure this guards against is a fan-out that quietly drops an
    unreachable host and reports success for the rest — an instrument that
    stops measuring and reports quiet.
    """


class Transport(Protocol):
    """How a hint reaches ONE peer.

    Deliberately minimal and deliberately pluggable: ``scitex-nas-03`` cannot
    join the overlay, the operator's laptop binds Postgres to loopback, and a
    same-process fleet needs no network at all. One transport cannot serve all
    three, and a relay that assumed one would simply skip the hosts it could
    not reach.
    """

    def deliver(self, peer: str, channel: str, payload: str) -> None:
        """Cause ``NOTIFY <channel>, '<payload>'`` in ``peer``'s database.

        Raises :class:`TransportError` if the peer could not be rung.
        """
        ...  # pragma: no cover - protocol


class RelayOutcome(NamedTuple):
    """What happened for ONE peer. ``detail`` is populated on failure."""

    peer: str
    delivered: bool
    detail: str = ""


class RelayReport(NamedTuple):
    """The result of one fan-out, including the case where nothing was sent.

    ``forwarded`` is False for the two SILENT non-events — a hint that was not
    ours to forward, and a relay with no peers. Both would otherwise look
    identical to "fanned out to everyone successfully": an empty outcome list
    and no error. Naming them is the whole reason this is a report and not a
    ``list``.
    """

    forwarded: bool
    reason: str
    outcomes: tuple[RelayOutcome, ...] = ()

    @property
    def undelivered(self) -> tuple[RelayOutcome, ...]:
        """Peers that could NOT be rung — what a caller should log or alert on."""
        return tuple(o for o in self.outcomes if not o.delivered)


#: Returned when the hint did not originate here.
#:
#: LOOP SUPPRESSION, and it needs no seen-set and no TTL. Every host rings
#: every peer directly, so a hint reaches each host exactly once from its
#: source; a host that re-forwarded what it received would multiply that by the
#: fleet size on every write. The origin is already in the payload, so the test
#: is one comparison and cannot drift out of sync with a separate table.
_NOT_MINE = "origin-is-not-this-node"

#: Returned when this relay has no peers to ring.
#:
#: A LOUD name for the quietest failure here. On 2026-08-15 the host registry
#: declared ``ywata-note-win`` with ``ssh_alias: null`` — no route — while ssh
#: to it worked in both directions and had for months. A relay that trusted
#: that record would drop the operator's own laptop and report a clean run.
_NO_PEERS = "no-peers-declared"


def fan_out(
    hint: Hint,
    *,
    node_id: str,
    peers: Sequence[str],
    transport: Transport,
    schema_name: str = "public",
) -> RelayReport:
    """Ring every peer with ``hint``, reporting each one's fate.

    Parameters
    ----------
    hint : Hint
        The doorbell payload, as decoded from this node's own channel.
    node_id : str
        This node's origin id. A hint whose origin differs is NOT forwarded.
    peers : Sequence[str]
        Peer names the transport understands. Empty is reported, never
        treated as success.
    transport : Transport
        How to reach one peer.
    schema_name : str
        The store whose channel is rung on the far side. The peer is rung on
        the SAME channel, because a peer's listeners subscribe to their own
        store's channel and a renamed one would be heard by nobody.

    Notes
    -----
    A peer that raises does NOT abort the fan-out. Partial reachability is the
    normal state of this fleet — nas-03 is off the overlay, the laptop sleeps —
    and a fan-out that stopped at the first failure would make one unreachable
    host silence every reachable one.
    """
    if hint.origin != node_id:
        return RelayReport(forwarded=False, reason=_NOT_MINE)
    if not peers:
        return RelayReport(forwarded=False, reason=_NO_PEERS)

    channel = channel_for(schema_name)
    payload = encode_hint(hint.origin, hint.max_seq)

    outcomes: list[RelayOutcome] = []
    for peer in peers:
        try:
            transport.deliver(peer, channel, payload)
        except Exception as exc:  # noqa: BLE001 - see below
            # BROAD ON PURPOSE. A transport is pluggable, so the exception
            # types are open-ended — ssh raises OSError, a DB transport raises
            # a driver error, a future one raises something unnamed here. A
            # narrow catch would let an unforeseen type abort the loop and take
            # every REACHABLE peer down with the unreachable one. The exception
            # is not swallowed: its type and message become the outcome.
            outcomes.append(
                RelayOutcome(peer=peer, delivered=False, detail=f"{type(exc).__name__}: {exc}")
            )
        else:
            outcomes.append(RelayOutcome(peer=peer, delivered=True))
    return RelayReport(forwarded=True, reason="fanned-out", outcomes=tuple(outcomes))


class InMemoryTransport:
    """A real transport for peers inside THIS process.

    Not a test double. A single-process fleet (one host, several stores) has
    no network to cross, and paying ssh for a hint that never leaves the
    process would be absurd. It also makes :func:`fan_out`'s contract testable
    without infrastructure, which is a consequence of it being real, not its
    purpose.

    ``unreachable`` names peers that raise, so the report-do-not-skip path is
    exercisable — a fleet where every peer always answers would never test the
    branch that matters.
    """

    def __init__(self, *, unreachable: Sequence[str] = ()) -> None:
        self.rung: list[tuple[str, str, str]] = []
        self._unreachable = frozenset(unreachable)

    def deliver(self, peer: str, channel: str, payload: str) -> None:
        if peer in self._unreachable:
            raise TransportError(f"{peer} is not reachable from here")
        self.rung.append((peer, channel, payload))


# EOF
