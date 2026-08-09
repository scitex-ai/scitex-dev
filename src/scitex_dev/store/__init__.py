#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-host database replicas that reconcile by DIRECTED REPLAY of an oplog.

A host that cannot reach its peers keeps accepting writes, and a new host
can join by replaying from seq 0. Reconciliation is never a comparison of
two stores -- see :mod:`._replay` for why that alternative is not merely
slower but structurally unsafe.

This module is intentionally a thin re-export list so that PR 1's
``StoreTarget`` / ``TableSpec`` / ``FieldPolicy`` / ``discover_stores`` /
``Row`` exports can be added here with a one-line merge. See
:mod:`._oplog_dialect` for the seam between the two.
"""

from __future__ import annotations

from ._oplog_dialect import POSTGRES, SQLITE, OplogTarget
from ._oplog_model import (
    OP_DELETE,
    OP_UPSERT,
    Op,
    OplogGapError,
    SingleWriterViolationError,
    StoreReplayError,
    SupersededFenceError,
    UnknownOpKindError,
)
from ._oplog_store import OpLogStore
from ._reading import HostSilence, Reading, Watermark
from ._replay import ReplayOutcome, heal, replay, replay_all

__all__ = [
    "OP_DELETE",
    "OP_UPSERT",
    "POSTGRES",
    "SQLITE",
    "HostSilence",
    "Op",
    "OpLogStore",
    "OplogGapError",
    "OplogTarget",
    "Reading",
    "ReplayOutcome",
    "SingleWriterViolationError",
    "StoreReplayError",
    "SupersededFenceError",
    "UnknownOpKindError",
    "Watermark",
    "heal",
    "replay",
    "replay_all",
]

# EOF
