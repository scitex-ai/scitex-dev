#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The store-side plumbing behind :attr:`~._store.Store.identity`.

A mixin for the same reason :class:`~._peer_state.PeerState` is one: it
shares ``_connection``, ``_lock``, ``dialect`` and ``schema`` with the
record path, and threading a second object through every call site would be
a larger change than the seam it buys. It is a SEPARATE mixin from
``PeerState`` because the concerns do not overlap — peer state is *what this
node knows about other nodes*, and this is *who this store is*, which is
prior to having any peers at all.

The two halves are read from two different places, on purpose
-------------------------------------------------------------
``store_uuid`` is read from the store's own table. That is what makes it the
LINEAGE: it travels with the data, so every copy of a store agrees on it.

``system_identifier`` is asked of the dialect, which asks the serving
system. That is what makes it the INSTANCE: it does NOT travel with the
data, so a copy disagrees with its original.

Reading both from the same place would produce a pair that is really one
value twice, and it would be exactly as blind to a fork as ``store_uuid``
alone — which is the state the fleet was in on 2026-08-11, when two
Postgres instances both answered
``1d55dd6e-3d2a-4c24-a429-a78835ab988f`` while holding 404 and 146
records the other had never seen.
"""

from __future__ import annotations

import uuid
from typing import Any

from ._dialect import STORE_UUID_KEY
from ._identity import StoreIdentity
from ._policy import Schema

__all__ = ["IdentityState"]


class IdentityState:
    """Mixin: the "who is this store" surface of :class:`~._store.Store`."""

    # Provided by Store; declared for readers and type checkers.
    dialect: Any
    schema: Schema
    _connection: Any
    _lock: Any

    @property
    def identity(self) -> StoreIdentity:
        """Who this store is: ``(store_uuid, system_identifier)``.

        MINTS THE LINEAGE ON FIRST READ. A store that has never been asked
        has no uuid, and the alternative — minting in ``__init__`` — would
        write to every store merely opened for a read.

        The mint is a plain ``uuid4``. It is deliberately NOT derived from
        the path, the hostname, the time or a hash of the contents: a
        derived identity makes two independently-created stores on
        similar-looking hosts collide, and a collision here means two
        unrelated stores certify as one.

        The instance half is re-read on EVERY access rather than cached.
        It is one cheap call, and caching it would let a process that
        reconnected elsewhere keep reporting the instance it used to be on
        — a stale identity being the one thing an identity must never be.
        """
        with self._lock:
            store_uuid = self._read_store_uuid() or self._mint_store_uuid()
        identifier, source = self.dialect.system_identifier(
            self._connection, self.target  # type: ignore[attr-defined]
        )
        return StoreIdentity(
            store_uuid=store_uuid,
            system_identifier=identifier,
            system_source=source,
        )

    # -- internals --------------------------------------------------------
    def _read_store_uuid(self) -> "str | None":
        table = self.dialect.quote(self.dialect.identity_table(self.schema))
        sql = (
            f"SELECT {self.dialect.quote('value')} AS value FROM {table} "
            f"WHERE {self.dialect.quote('key')} = {self.dialect.placeholder(0)}"
        )
        found = self._connection.execute(sql, (STORE_UUID_KEY,)).fetchone()
        return str(found["value"]) if found is not None else None

    def _mint_store_uuid(self) -> str:
        """Write a fresh lineage uuid, and return whoever's won a race.

        The insert is a plain INSERT, not an upsert, and the value is
        re-read afterwards. Two processes opening a fresh store at the same
        instant would otherwise each overwrite the other's uuid and walk
        away believing different lineages for one database — a fork
        manufactured by the fork detector's own bootstrap.

        A no-op insert followed by a read gives both processes the same
        answer: whichever landed first.
        """
        table = self.dialect.identity_table(self.schema)
        minted = str(uuid.uuid4())
        sql = self.dialect.insert_ignore_sql(table, ["key", "value"], "key")
        self._connection.execute(sql, (STORE_UUID_KEY, minted))
        return self._read_store_uuid() or minted

# EOF
