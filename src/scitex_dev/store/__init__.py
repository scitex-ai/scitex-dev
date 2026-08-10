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
from ._discovery import DiscoveredStore, StoreStatus, discover_stores
from ._errors import (
    AdoptionRefusedError,
    ClockDriftError,
    DialectUnavailableError,
    FieldPolicyError,
    OplogGapError,
    RecordNotFoundError,
    RevisionMismatchError,
    SchemaError,
    StoreError,
    StoreTargetError,
    WriterConflictError,
)
from ._guards import ANY_REVISION, NEW_RECORD
from ._hlc import HLC, HybridLogicalClock
from ._host import host_store, socket_dsn
from ._merge import MergeConflict, MergeOutcome, merge_field
from ._oplog import OpEntry, OpKind, assert_contiguous
from ._policy import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    RESERVED_COLUMNS,
    Schema,
    WriterPolicy,
)
from ._replication import ReplayResult, outstanding, pull, replay, sync
from ._row import Row
from ._store import PutResult, Store
from ._target import Backend, StoreTarget

__all__ = [
    "ANY_REVISION",
    "AdoptionRefusedError",
    "Backend",
    "ClockDriftError",
    "DialectUnavailableError",
    "DiscoveredStore",
    "FieldKind",
    "FieldPolicy",
    "FieldPolicyError",
    "FieldRole",
    "GENESIS_ACTOR",
    "HLC",
    "HybridLogicalClock",
    "MergeConflict",
    "MergeOutcome",
    "MergeRule",
    "NEW_RECORD",
    "OpEntry",
    "OpKind",
    "OplogGapError",
    "PutResult",
    "RESERVED_COLUMNS",
    "RecordNotFoundError",
    "ReplayResult",
    "RevisionMismatchError",
    "Row",
    "Schema",
    "SchemaError",
    "Store",
    "StoreError",
    "StoreStatus",
    "StoreTarget",
    "StoreTargetError",
    "WriterConflictError",
    "WriterPolicy",
    "apply_entry",
    "assert_contiguous",
    "build_genesis",
    "discover_stores",
    "genesis_origin",
    "host_store",
    "install_genesis",
    "merge_field",
    "outstanding",
    "pull",
    "replay",
    "socket_dsn",
    "sync",
    "verify_adoption",
]

# EOF
