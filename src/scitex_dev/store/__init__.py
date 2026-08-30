#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev.store`` — the backend-agnostic store primitive.

Every leaf package that stores anything builds on this instead of rolling
its own schema, dialect and reconciler. Not for tidiness: each hand-rolled
reconciler is another chance to re-derive the same data-loss bug, and this
fleet has already paid for that one.

Import cost
-----------
This subpackage imports the standard library and nothing else. It does NOT
pull in the linter, CI, jobs, release or ecosystem machinery, so depending
on it does not drag the ecosystem toolchain into a leaf package's runtime.
``scitex_config`` is touched lazily, and only to resolve a conventional
path. ``psycopg`` is imported only if a Postgres store is opened. There is
a test that enforces this in a subprocess — see
``tests/scitex_dev/store/test_import_cost.py``. That is a promise made to
scitex-cards as the condition of adopting this, and it is checked rather
than asserted.

The two guarantees
------------------
**Nothing is ever deleted.** There is no delete verb. :meth:`Store.hide`
sets a flag; the row, its history and every value it held stay readable.

**Reconciliation is directed replay, never set-difference.** Two stores
converge by replaying each other's ordered operation logs, with a hard
``first_seq == cursor + 1`` assertion. Absence from a log is not evidence
of anything, so the inference that destroyed 2,159 rows on 2026-07-19/21
is not merely discouraged here — it is unavailable.

Quick start
-----------
::

    from scitex_dev.store import (
        FieldKind, FieldPolicy, FieldRole, MergeRule,
        NEW_RECORD, Schema, Store, StoreTarget, WriterPolicy,
    )

    schema = Schema.build("cards", {
        "id": FieldPolicy(
            kind=FieldKind.TEXT, role=FieldRole.IDENTITY,
            required=True, merge=MergeRule.IMMUTABLE, indexed=False,
        ),
        "status": FieldPolicy(
            kind=FieldKind.TEXT, role=FieldRole.DATA,
            required=True, merge=MergeRule.LAST_WRITER_WINS, indexed=True,
        ),
    })

    store = Store(
        StoreTarget.for_package("cards"),
        schema,
        node="scitex-compute-04",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    store.put({"id": "c1", "status": "open"}, expected_revision=NEW_RECORD)

Reading is by key (:meth:`Store.get`), by everything (:meth:`Store.rows`)
or by CRITERION::

    from scitex_dev.store import Query, eq

    store.search(Query().where(eq("status", "open")).ordered_by("id"))

A query names fields, never SQL, and a field the schema does not declare
raises rather than returning nothing. Full text is opt-in per schema —
``Schema.build(..., text_search=("title", "body"))`` — and the index and the
match expression are built from that one declaration. See :mod:`._query`.

Note there is no default :class:`FieldPolicy` and no default
``expected_revision``. Both omissions are deliberate: a wrong default merge
rule loses data silently, and an implicit unlocked write loses updates
silently. See :mod:`._policy` and :mod:`._guards`.
"""

from __future__ import annotations

from ._adopt import (
    GENESIS_ACTOR,
    build_genesis,
    genesis_origin,
    install_genesis,
    verify_adoption,
)
from ._apply import apply_entry
from ._divergence import DivergenceReport, ForkPoint, detect_divergence
from ._errors import (
    AdoptionRefusedError,
    ClockDriftError,
    DialectUnavailableError,
    FieldPolicyError,
    OplogGapError,
    RecordNotFoundError,
    RevisionMismatchError,
    SchemaError,
    StoreDivergedError,
    StoreError,
    StoreIdentityMismatchError,
    StoreIdentityUnknownError,
    StoreTargetError,
    SupersededFenceError,
    WriterConflictError,
)
from .federation import (
    ENTRY_POINT_GROUP,
    StorePlugin,
    StorePluginProvider,
    discover_store_plugins,
    plugin_for,
    resolve_target,
)
from ._guards import ANY_REVISION, NEW_RECORD
from ._identity import (
    IdentityVerdict,
    StoreIdentity,
    UNKNOWN_SYSTEM,
    assert_same_store,
    compare_identity,
)
from ._hlc import HLC, HybridLogicalClock
from ._host import host_store, socket_dsn
from ._merge import MergeConflict, MergeOutcome, merge_field
from ._notify import Hint, channel_for, decode_hint, encode_hint
from ._oplog import OpEntry, OpKind, assert_contiguous, assert_not_superseded
from ._policy import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    RESERVED_COLUMNS,
    Schema,
    WriterPolicy,
)
from ._query import (
    Condition,
    Either,
    Op,
    Order,
    Query,
    contains,
    either,
    eq,
    gt,
    gte,
    is_in,
    is_null,
    lt,
    lte,
    ne,
    nonempty,
)
from ._read_door import ReadDoor
from ._relay import (
    InMemoryTransport,
    RelayOutcome,
    RelayReport,
    Transport,
    TransportError,
    fan_out,
)
from ._relay_ssh import SshPsqlTransport, aliases_for, ring_argv
from ._replication import ReplayResult, outstanding, pull, replay, sync
from ._row import Row
from ._store import PutResult, Store
from ._target import Backend, StoreTarget

__all__ = [
    "ANY_REVISION",
    "AdoptionRefusedError",
    "Backend",
    "ClockDriftError",
    "Condition",
    "DialectUnavailableError",
    "DivergenceReport",
    "ENTRY_POINT_GROUP",
    "Either",
    "FieldKind",
    "FieldPolicy",
    "FieldPolicyError",
    "FieldRole",
    "ForkPoint",
    "GENESIS_ACTOR",
    "HLC",
    "Hint",
    "HybridLogicalClock",
    "IdentityVerdict",
    "InMemoryTransport",
    "MergeConflict",
    "MergeOutcome",
    "MergeRule",
    "NEW_RECORD",
    "Op",
    "OpEntry",
    "OpKind",
    "OplogGapError",
    "Order",
    "PutResult",
    "Query",
    "RESERVED_COLUMNS",
    "ReadDoor",
    "RecordNotFoundError",
    "RelayOutcome",
    "RelayReport",
    "ReplayResult",
    "RevisionMismatchError",
    "Row",
    "Schema",
    "SchemaError",
    "SshPsqlTransport",
    "Store",
    "StoreDivergedError",
    "StoreError",
    "StoreIdentity",
    "StoreIdentityMismatchError",
    "StoreIdentityUnknownError",
    "StorePlugin",
    "StorePluginProvider",
    "StoreTarget",
    "StoreTargetError",
    "SupersededFenceError",
    "Transport",
    "TransportError",
    "UNKNOWN_SYSTEM",
    "WriterConflictError",
    "WriterPolicy",
    "aliases_for",
    "apply_entry",
    "assert_contiguous",
    "assert_not_superseded",
    "assert_same_store",
    "build_genesis",
    "channel_for",
    "compare_identity",
    "contains",
    "decode_hint",
    "detect_divergence",
    "discover_store_plugins",
    "either",
    "encode_hint",
    "eq",
    "fan_out",
    "genesis_origin",
    "gt",
    "gte",
    "host_store",
    "install_genesis",
    "is_in",
    "is_null",
    "lt",
    "lte",
    "merge_field",
    "ne",
    "nonempty",
    "outstanding",
    "plugin_for",
    "pull",
    "replay",
    "resolve_target",
    "ring_argv",
    "socket_dsn",
    "sync",
    "verify_adoption",
]

# EOF
