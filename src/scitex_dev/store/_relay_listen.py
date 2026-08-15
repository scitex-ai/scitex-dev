#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The half that runs: hear a local hint, ring every peer.

:mod:`._notify` says what a hint IS, :mod:`._relay` says who to ring and how a
failure is reported, :mod:`._relay_ssh` gets it across. This is the loop body
that joins them — and it is a body, not a daemon, on purpose: the decisions
live in :meth:`RelayListener.handle` and :meth:`RelayListener.announce`, which
are ordinary functions a test can call, while the ``LISTEN`` socket and the
retry policy belong to whatever supervises the process.

THE RECONNECT RULE, WHICH IS THE WHOLE REASON THIS CLASS EXISTS
----------------------------------------------------------------
scitex-cards measured that **0 of 3** notifications survive a disconnected
listener. PostgreSQL does not retain them; a listener that was away simply
never learns what it missed, and nothing anywhere reports the loss.

So a reconnecting relay MUST announce unconditionally — never "only if
something changed", because it cannot know whether something changed, and the
state it would consult was itself updated by the notifications it missed. The
one moment a relay is most likely to be stale is the moment it comes back, and
that is exactly when a cleverness check would suppress the announcement.

:meth:`announce` therefore takes no "has anything changed" argument. There is
nowhere to put one, which is the point.
"""

from __future__ import annotations

from typing import Sequence

from ._notify import Hint, decode_hint
from ._relay import RelayReport, Transport, fan_out

#: Returned when a payload arrived that this contract cannot read.
#:
#: A listener hears everything on the channel, including payloads written by a
#: future version. It must keep listening: a relay that died on an unreadable
#: payload would stop carrying every readable one after it, turning a cosmetic
#: incompatibility into a fleet-wide convergence failure.
_UNREADABLE = "undecodable-payload"


class RelayListener:
    """Turn hints heard on the LOCAL channel into rings on every peer.

    Holds no connection. The caller owns the socket, decides the retry policy,
    and calls :meth:`announce` after every successful (re)connect.
    """

    def __init__(
        self,
        *,
        node_id: str,
        peers: Sequence[str],
        transport: Transport,
        schema_name: str = "public",
    ) -> None:
        self.node_id = node_id
        self.peers = tuple(peers)
        self.transport = transport
        self.schema_name = schema_name

    def handle(self, payload: str) -> RelayReport:
        """Process one payload heard on the local channel.

        Never raises for a bad payload. The relay's job is to keep carrying
        hints, and an unreadable one is indistinguishable from a hint that was
        never sent — a state the sweep already handles.
        """
        hint = decode_hint(payload)
        if hint is None:
            return RelayReport(forwarded=False, reason=_UNREADABLE)
        return self._fan_out(hint)

    def announce(self, max_seq: int) -> RelayReport:
        """Ring every peer with THIS node's current position.

        Call after every successful connect and reconnect, unconditionally.
        See this module's docstring: notifications do not survive a listener's
        absence, so a relay that just reconnected is precisely the one whose
        peers are most likely to be behind.
        """
        return self._fan_out(Hint(origin=self.node_id, max_seq=max_seq))

    def _fan_out(self, hint: Hint) -> RelayReport:
        return fan_out(
            hint,
            node_id=self.node_id,
            peers=self.peers,
            transport=self.transport,
            schema_name=self.schema_name,
        )


# EOF
