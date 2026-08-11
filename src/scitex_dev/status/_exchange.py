#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The exchange id — one per A->B, issued by B, returned immediately.

    「A -> B という通信が起こるたびに id を発行すればよいのでは？」
    — the operator, 2026-08-11

This is what makes the immediate-ack pattern actually work. B answers at once
with ``202 Accepted`` and this id; A quotes the id whenever it wants to know
what happened. Without an id, "poll for status" has nothing to point at, and a
caller whose deadline expires can only guess.

Measured 2026-08-11: a spawn client gave up at 30 s and reported a peer
failure. The server had accepted the request and worked it for 5 min 12 s. The
client held no handle with which to re-ask, so the guess was the only output
available to it.

Format::

    xch_<YYYYMMDD>T<HHMMSS>Z_<origin-host>_<6 hex>
    xch_20260811T061508Z_scitex-compute-04_a1b2c3

Time-ordered when sorted as TEXT, attributable to the host that issued it, and
unique without coordination. The origin host is in the string on purpose: an
agent on compute-04 asking the laptop about an exchange quotes the same value,
so the id must not depend on local context to be meaningful.
"""

from __future__ import annotations

import re
import secrets
import socket
from datetime import datetime, timezone

__all__ = ["EXCHANGE_ID_PATTERN", "is_exchange_id", "new_exchange_id"]

EXCHANGE_ID_PATTERN = re.compile(
    r"^xch_[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9][A-Za-z0-9._-]*_[0-9a-f]{6}$"
)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def new_exchange_id(host: str | None = None) -> str:
    """Mint an id for one exchange.

    ``host`` defaults to this machine's hostname. Characters outside the id
    alphabet are replaced rather than dropped, so two hosts whose names differ
    only in punctuation cannot collapse to the same prefix.
    """
    origin = _UNSAFE.sub("-", host or socket.gethostname()) or "unknown"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"xch_{stamp}_{origin}_{secrets.token_hex(3)}"


def is_exchange_id(value: object) -> bool:
    """Is ``value`` a well-formed exchange id?"""
    return isinstance(value, str) and EXCHANGE_ID_PATTERN.match(value) is not None


# EOF
