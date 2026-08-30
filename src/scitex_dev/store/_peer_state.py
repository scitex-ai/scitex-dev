#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What this node knows about OTHER nodes.

Split out of `_store.py` (see the module docstring there for the record
path). The seam is not arbitrary: everything here touches the OPLOG and
CURSOR tables and nothing here touches the rows table's merge policies, so
the two halves share plumbing but never reasoning.

It is also the half that keeps growing. The cursor pair came first, the
fence pair arrived with the entitlement check, and a watermark is already
sketched on the replication card. Three pairs of the same shape in one file
with the record path was what pushed `_store.py` over its line limit.

THREE KINDS OF PEER KNOWLEDGE, and they answer different questions:

    cursor   how far have I applied from this peer?   -> gaps
    fence    which authority am I accepting from it?  -> entitlement
    origins  what does my own log contain?            -> what I can serve

The cursor and the fence live in ONE table because both are "what we know
about that peer". Two tables keyed identically would be two places to keep
consistent for no gain.
"""

from __future__ import annotations

from typing import Any, Mapping

from ._errors import StoreError
from ._oplog import FENCE_UNKNOWN, OpEntry
from ._policy import Schema


class PeerState:
    """Mixin: the peer-facing surface of :class:`~._store.Store`.

    A mixin rather than a collaborator object because every method here
    shares `_connection`, `_lock`, `dialect` and `schema` with the record
    path. Threading a second object through each call site would have been a
    larger change than the one it was extracted to enable.
    """

    # Provided by Store; declared for readers and type checkers.
    dialect: Any
    schema: Schema
    node: str
    _connection: Any
    _lock: Any

    # -- schema migration -------------------------------------------------
    def _schema_objects_missing(self, schema: Schema) -> bool:
        """Is anything ``create_sql`` would build not there yet?

        WHY THIS EXISTS. Every statement in ``create_sql`` carries IF NOT
        EXISTS, so re-running it on an existing store was believed free. On
        PostgreSQL it is not: ownership is checked BEFORE IF NOT EXISTS
        short-circuits, so ``CREATE INDEX IF NOT EXISTS`` naming an index that
        already exists still raises InsufficientPrivilege for a role that does
        not own the table. A role holding SELECT/INSERT/UPDATE/DELETE on every
        table of a store therefore could not OPEN that store at all.

        Measured 2026-08-28 against the fleet primary, as a member of the
        grant role that owns nothing:

            SELECT / INSERT                       OK
            CREATE INDEX IF NOT EXISTS (exists)   must be owner of table ...
            ALTER TABLE ADD COLUMN IF NOT EXISTS  must be owner of table ...

        So ownership had become a requirement for USING a store rather than
        for CREATING one, which is not what the grant model assumes and not
        what the DDL means.

        Reading before writing is what :meth:`_apply_additive_migrations`
        already does one method below, and its reasoning transfers verbatim:
        a swallowed error cannot tell "already present" from "failed for
        another reason", and this runs on every open.

        Conservative on purpose — ANY missing table or index returns True and
        the full ``create_sql`` runs, exactly as before. The probe only ever
        removes DDL that would have changed nothing.
        """
        for table in self.dialect.schema_tables(schema):
            if not self._first_column_values(self.dialect.columns_sql(table)):
                return True
        wanted: dict[str, set[str]] = {}
        for index, table, _column in self.dialect.index_specs(schema):
            wanted.setdefault(table, set()).add(index)
        # Full-text indexes are built by their own DDL rather than the
        # uniform CREATE INDEX above, but they are still objects create_sql
        # builds — so a store missing one must still be repaired, and a
        # store that has them must not have create_sql re-run for nothing.
        for index, table, _ddl in self.dialect.text_index_specs(schema):
            wanted.setdefault(table, set()).add(index)
        for table, names in wanted.items():
            if not names <= self._first_column_values(self.dialect.indexes_sql(table)):
                return True
        return False

    def _first_column_values(self, sql: str) -> set[str]:
        """Run ``sql`` and collect the FIRST column of every row.

        The catalogue queries do not agree on what that column is called,
        so it is taken positionally by key — the same trick, and the same
        precedent, as the column read below.
        """
        return {
            str(row[list(row.keys())[0]])
            for row in self._connection.execute(sql).fetchall()
        }

    def _apply_additive_migrations(self, schema: Schema) -> None:
        """Add columns that `create_sql` cannot add to an existing store.

        `CREATE TABLE IF NOT EXISTS` is inert on a table that already exists,
        so a column added to the schema reaches NEW stores only. Without
        this, the first INSERT naming that column fails on every deployed
        store — a change that is green on a fresh temp directory and broken
        in the fleet.

        Absence is established by READING the columns, not by attempting the
        ALTER and swallowing the error. A swallowed error cannot tell
        "already present" from "the ALTER failed for another reason", and
        this runs on every open.
        """
        for table, column, coltype, default in self.dialect.additive_columns(schema):
            # `information_schema` says `column_name`, and a catalogue
            # column name is not something to hard-code, so the shared helper
            # takes the first value via its key (precedent: system_identifier).
            existing = self._first_column_values(self.dialect.columns_sql(table))
            if not existing or column in existing:
                # No rows at all means create_sql just made the table with
                # the current shape — nothing to migrate.
                continue
            self._connection.execute(
                self.dialect.add_column_sql(table, column, coltype, default)
            )

    # -- what my log holds ------------------------------------------------
    def changes_since(
        self, origin: str, seq: int, *, limit: int = 1000
    ) -> list[OpEntry]:
        """Ops from ``origin`` after ``seq``, ordered and contiguous.

        What a peer calls to pull. Returns a prefix starting at ``seq + 1``;
        :func:`~._replication.replay` verifies that before applying any of
        it.
        """
        with self._lock:
            table = self.dialect.quote(self.dialect.oplog_table(self.schema))
            sql = (
                f"SELECT * FROM {table} WHERE "
                f"{self.dialect.quote('origin')} = {self.dialect.placeholder(0)} "
                f"AND {self.dialect.quote('seq')} > {self.dialect.placeholder(1)} "
                f"ORDER BY {self.dialect.quote('seq')} ASC LIMIT {int(limit)}"
            )
            found = self._connection.execute(sql, (origin, seq)).fetchall()
            return [OpEntry.from_row(record) for record in found]

    def origins(self) -> dict[str, int]:
        """Every origin in the log, mapped to its highest sequence."""
        with self._lock:
            table = self.dialect.quote(self.dialect.oplog_table(self.schema))
            sql = (
                f"SELECT {self.dialect.quote('origin')} AS origin, "
                f"MAX({self.dialect.quote('seq')}) AS max_seq FROM {table} "
                f"GROUP BY {self.dialect.quote('origin')}"
            )
            return {
                record["origin"]: int(record["max_seq"])
                for record in self._connection.execute(sql).fetchall()
            }

    def next_seq(self) -> int:
        """The sequence this node's next op will carry."""
        with self._lock:
            return self.origins().get(self.node, 0) + 1

    # -- how far I have applied -------------------------------------------
    def cursor(self, source: str) -> int:
        """The last sequence applied from ``source``; 0 when never applied."""
        with self._lock:
            table = self.dialect.quote(self.dialect.cursor_table(self.schema))
            sql = (
                f"SELECT {self.dialect.quote('seq')} AS seq FROM {table} "
                f"WHERE {self.dialect.quote('source')} = "
                f"{self.dialect.placeholder(0)}"
            )
            found = self._connection.execute(sql, (source,)).fetchone()
            return int(found["seq"]) if found is not None else 0

    def set_cursor(self, source: str, seq: int) -> None:
        """Advance the replay cursor. Never moves it backwards."""
        with self._lock:
            existing = self.cursor(source)
            if seq < existing:
                raise StoreError(
                    f"Refusing to move the replay cursor for {source!r} "
                    f"backwards from {existing} to {seq}. Rewinding re-applies "
                    "ops already applied, dragging field timestamps backwards. "
                    "For a genuine re-sync, rebuild from the log instead."
                )
            table = self.dialect.cursor_table(self.schema)
            sql = self.dialect.upsert_sql(
                table, ["source", "seq", "fence"], "source"
            )
            self._connection.execute(sql, (source, seq, self.fence(source)))

    # -- which authority I accept -----------------------------------------
    def fence(self, source: str) -> int:
        """The highest fence accepted from ``source``; 0 when never fenced."""
        with self._lock:
            table = self.dialect.quote(self.dialect.cursor_table(self.schema))
            sql = (
                f"SELECT {self.dialect.quote('fence')} AS fence FROM {table} "
                f"WHERE {self.dialect.quote('source')} = "
                f"{self.dialect.placeholder(0)}"
            )
            found = self._connection.execute(sql, (source,)).fetchone()
            return int(found["fence"]) if found is not None else FENCE_UNKNOWN

    def set_fence(self, source: str, fence: int) -> None:
        """Record a fence for ``source``. Never moves it backwards.

        The same refusal as :meth:`set_cursor`, for a sharper reason:
        lowering a fence RE-ADMITS the writer it was raised to exclude. If a
        demoted node's own ops could lower it, the fence would defend against
        precisely nothing.

        AN ADMINISTRATIVE VERB, NOT A REPLICATION ONE. Nothing on the data
        path calls this. :func:`~._replication.replay` reads the fence to
        judge a batch and never writes it, because a fence adopted from the
        batch it authorises is not a check — it is an instruction from
        whoever sent the batch. Call this from something that authenticated
        the peer and knows the promotion is real.

        The way back down is :meth:`rescind_fence`, which exists because the
        alternative to a supported reversal is an operator editing the cursor
        table by hand — the exact class of repair this primitive was written
        to make unnecessary.
        """
        with self._lock:
            existing = self.fence(source)
            if fence < existing:
                raise StoreError(
                    f"Refusing to lower the fence for {source!r} from "
                    f"{existing} to {fence}. A fence only ever rises; "
                    "lowering it re-admits the writer it was raised to "
                    "exclude, which is the whole failure it exists to "
                    "prevent.\n"
                    "If the higher fence was recorded in error — which is "
                    "recoverable, and used to require hand-editing the "
                    "cursor table — use rescind_fence(source, fence, "
                    "reason=...) instead. It performs exactly this lowering "
                    "and makes the caller say why."
                )
            if fence == existing:
                return
            self._write_fence(source, fence)

    def rescind_fence(self, source: str, fence: int, *, reason: str) -> None:
        """LOWER a fence that was recorded in error. The only way down.

        :meth:`set_fence` refuses to descend, and that refusal is right for
        the replication path: a fence that a peer's own traffic could lower
        would defend against nothing. But "the fence only rises" as an
        ABSOLUTE makes a mistaken fence permanent, and a mistaken fence
        excludes a healthy host from the fleet's view of itself. Before this
        verb existed the only remedy was raw SQL against the cursor table,
        which is precisely the repair this package exists to remove.

        ``reason`` is required and must be non-empty. It is NOT persisted —
        there is nowhere in this schema to persist it, and inventing a column
        to hold a string nobody reads would be worse than the honesty of
        saying so. It is required because it makes the call site state its
        justification in code, where review and ``rg rescind_fence`` can both
        find it. That is the same reason :data:`~._guards.ANY_REVISION` is a
        named sentinel rather than a boolean.

        Raises :class:`~._errors.StoreError` for an empty reason or a
        negative fence.
        """
        if not reason or not reason.strip():
            raise StoreError(
                f"rescind_fence({source!r}, {fence}) needs a reason. Lowering "
                "a fence re-admits a writer that something previously judged "
                "unentitled, so the justification belongs beside the call "
                "rather than in the memory of whoever ran it."
            )
        if fence < FENCE_UNKNOWN:
            raise StoreError(
                f"rescind_fence({source!r}, {fence}) is negative. "
                f"{FENCE_UNKNOWN} means 'unfenced' and is the floor; there is "
                "nothing below it to rescind to."
            )
        with self._lock:
            self._write_fence(source, fence)

    def _write_fence(self, source: str, fence: int) -> None:
        """Persist a fence, preserving the cursor that shares its row."""
        table = self.dialect.cursor_table(self.schema)
        sql = self.dialect.upsert_sql(table, ["source", "seq", "fence"], "source")
        self._connection.execute(sql, (source, self.cursor(source), fence))


# EOF
