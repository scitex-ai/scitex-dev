#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The exchange ledger — one table, one row per A->B exchange.

    「~/.scitex/scitex.db に通信の製本としてまとめられる気がします」
    「毎回同じ datatype なので、見ればよいだけ」
    — the operator, 2026-08-11

Every exchange yields the SAME shape, so they all go in ONE table and "what
happened to request X" becomes a LOOKUP rather than an investigation.

STORAGE IS :mod:`scitex_dev.store`, NOT A FILE
----------------------------------------------
This module declares a :class:`~scitex_dev.store.Schema` and nothing else. It
opens no path, and ADR-0006 Decision 6 is why: "anything deriving a filesystem
location from the store target is the defect, not a workaround for it."

Consuming the primitive buys, for free, the properties this ledger actually
needs — one store per host, oplog-based DIRECTED REPLAY between hosts, HLC
ordering, field-level merge, and no delete verb. That is not theoretical: the
fleet is consolidating onto compute-04, so an exchange opened on the laptop
must be answerable from compute-04, and a row must not be lost to a
reconciliation that mistook absence for deletion.

WHY ``final`` IS WORTH A COLUMN
-------------------------------
It is what makes an unanswered exchange FINDABLE::

    final = false AND updated_at < <threshold>

— work that was ACCEPTED and never CONCLUDED. On 2026-08-11 that state was
invisible and had to be reconstructed by hand: a client gave up at 30 s, the
server worked the request for 5 min 12 s, and nothing anywhere held both
halves of the exchange.

It is DERIVED from the status code (:attr:`StatusCode.final`), never supplied
by a caller, and :func:`ledger_record` is the only thing that computes it —
so the column cannot come to disagree with the code beside it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ._exchange import is_exchange_id
from ._status_code import StatusCode

__all__ = ["LEDGER_TABLE", "ledger_record", "ledger_schema"]

LEDGER_TABLE = "status_exchanges"


def ledger_schema() -> Any:
    """Build the ledger's :class:`~scitex_dev.store.Schema`.

    Built on call rather than at import so that importing
    :mod:`scitex_dev.status` does not drag in the store machinery for callers
    that only want to construct a :class:`StatusCode`.

    Identity fields are ``IMMUTABLE`` because an exchange's participants
    cannot change. Status fields are ``LAST_WRITER_WINS`` because a row holds
    the exchange's CURRENT state — its history is not lost, because the store
    keeps an oplog and never deletes, so the 202 and the completion are both
    still readable afterwards.
    """
    from scitex_dev.store import FieldKind, FieldPolicy, FieldRole, MergeRule, Schema

    def _policy(kind, role, merge, *, indexed: bool):
        return FieldPolicy(
            kind=kind, role=role, required=True, merge=merge, indexed=indexed
        )

    identity = FieldRole.IDENTITY
    data = FieldRole.DATA
    immutable = MergeRule.IMMUTABLE
    lww = MergeRule.LAST_WRITER_WINS

    return Schema.build(
        LEDGER_TABLE,
        {
            "exchange_id": _policy(FieldKind.TEXT, identity, immutable, indexed=False),
            "initiator": _policy(FieldKind.TEXT, data, immutable, indexed=True),
            "responder": _policy(FieldKind.TEXT, data, immutable, indexed=True),
            "operation": _policy(FieldKind.TEXT, data, immutable, indexed=True),
            "opened_at": _policy(FieldKind.TEXT, data, immutable, indexed=False),
            # `code` is JSON because it is int for http/process and str for
            # grpc/dns/errno/scitex, and the spec says VERBATIM. Coercing it
            # to text would quietly turn 503 into "503" and lose the one
            # guarantee the design is built on.
            "kind": _policy(FieldKind.TEXT, data, lww, indexed=True),
            "code": _policy(FieldKind.JSON, data, lww, indexed=False),
            "message": _policy(FieldKind.TEXT, data, lww, indexed=False),
            "updated_at": _policy(FieldKind.TEXT, data, MergeRule.MAX, indexed=True),
            "final": _policy(FieldKind.BOOL, data, lww, indexed=True),
        },
    )


def ledger_record(
    *,
    exchange_id: str,
    initiator: str,
    responder: str,
    operation: str,
    status: StatusCode,
    opened_at: str,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Build one ledger row from a validated exchange and its latest status.

    The ONLY constructor for a row. ``final`` is computed here from ``status``
    rather than accepted from the caller, so the stored flag and the stored
    code always agree.
    """
    if not is_exchange_id(exchange_id):
        raise ValueError(
            f"{exchange_id!r} is not a well-formed exchange id. Expected "
            f"xch_<YYYYMMDD>T<HHMMSS>Z_<host>_<6 hex>, e.g. "
            f"xch_20260811T061508Z_scitex-compute-04_a1b2c3. Mint one with "
            f"scitex_dev.status.new_exchange_id(); the format carries its "
            f"origin host and time so the id means the same thing on the "
            f"machine that asks about it later."
        )
    return {
        "exchange_id": exchange_id,
        "initiator": initiator,
        "responder": responder,
        "operation": operation,
        "opened_at": opened_at,
        "kind": status.kind,
        "code": status.code,
        "message": status.message,
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
        "final": status.final,
    }


# EOF
