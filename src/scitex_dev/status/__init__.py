#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev.status`` — the SciTeX status primitive.

    StatusCode(kind, code, message)

Three fields. ``kind`` says HOW TO READ ``code``; ``code`` is the NATIVE code
from that vocabulary, verbatim; ``message`` is a HINT that says what the
sender is doing and hands the receiver the means to verify and to ask.

::

    from scitex_dev.status import StatusCode, new_exchange_id

    xid = new_exchange_id()
    StatusCode(
        kind="http", code=202,
        message=f"accepted as {xid}; phase=container_creation since "
                f"06:15:08Z; retry in 10s or poll `sac agents list web-01`",
    )

There is NO SciTeX vocabulary above these codes and nothing translates. ``http
503`` is a real HTTP 503; ``process 137`` is a real SIGKILL exit. Borrowing a
mature vocabulary is lossless and already understood; the canonical vocabulary
this replaced would have folded 137 into some "resource exhausted" and thrown
away the one fact usually worth knowing.

Each call boundary DECLARES which kind it borrows — see
``spec/boundaries.yaml``. That per-boundary declaration is the entire
coordination cost of the design.

The source of truth
-------------------
``spec/`` is language-independent and normative: ``kinds.yaml``,
``scitex-codes.yaml``, ``boundaries.yaml``, ``schema/*.json``, and the
specification itself in ``status-codes.md``. This Python is DERIVED from those
files and ``tests/scitex_dev/status/test__spec.py`` fails when it
drifts. See ADR-0007.

Import cost
-----------
Constructing a :class:`StatusCode` reads the packaged YAML once (cached) and
imports the standard library. It does NOT import :mod:`scitex_dev.store`;
:func:`ledger_schema` does that on call, so a leaf that only reports statuses
never pays for the store machinery.

What is deliberately absent
---------------------------
No canonical status enum, no translation layer, no ``retryable`` field, no
stored ``ok``, no error taxonomy. ``ok`` and ``final`` are read-only derived
properties and are never serialised: two fields that can disagree eventually
will. Thin gets adopted; thick gets bypassed.
"""

from __future__ import annotations

from ._errors import (
    InferredCauseError,
    MissingProbeError,
    StatusError,
    UnknownCodeError,
    UnknownKindError,
)
from ._exchange import EXCHANGE_ID_PATTERN, is_exchange_id, new_exchange_id
from ._kinds import (
    KIND_DNS,
    KIND_ERRNO,
    KIND_GRPC,
    KIND_HTTP,
    KIND_PROCESS,
    KIND_SCITEX,
    RESERVED_PROCESS_CODES,
    kinds,
    requires_probe,
    validate_code,
    validate_kind,
)
from ._ledger import LEDGER_TABLE, ledger_record, ledger_schema
from ._message import forbidden_markers, names_a_probe, validate_message
from ._spec import (
    SPEC_DIR,
    SPEC_VERSION,
    load_boundaries,
    load_kinds,
    load_schema,
    load_scitex_codes,
    spec_path,
)
from ._status_code import StatusCode

__all__ = [
    "EXCHANGE_ID_PATTERN",
    "InferredCauseError",
    "KIND_DNS",
    "KIND_ERRNO",
    "KIND_GRPC",
    "KIND_HTTP",
    "KIND_PROCESS",
    "KIND_SCITEX",
    "LEDGER_TABLE",
    "MissingProbeError",
    "RESERVED_PROCESS_CODES",
    "SPEC_DIR",
    "SPEC_VERSION",
    "StatusCode",
    "StatusError",
    "UnknownCodeError",
    "UnknownKindError",
    "forbidden_markers",
    "is_exchange_id",
    "kinds",
    "ledger_record",
    "ledger_schema",
    "load_boundaries",
    "load_kinds",
    "load_schema",
    "load_scitex_codes",
    "names_a_probe",
    "new_exchange_id",
    "requires_probe",
    "spec_path",
    "validate_code",
    "validate_kind",
    "validate_message",
]

# EOF
