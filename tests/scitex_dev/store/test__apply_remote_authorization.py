#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``apply_remote`` must enforce the same writer policy the front door does.

The local write path refuses a write to a record the actor does not own when
the store runs under ``SINGLE_WRITER`` (``put``, ``hide``, ``unhide``,
``handover`` all call ``check_owner``). The replication path did not, so the
rule was enforceable only against callers who came in through the front door.

A rule the front door enforces and the back door does not is not a rule; it
is a detour. Under ``SINGLE_WRITER`` that detour is the whole policy: the
mode exists to make ownership the write gate, and a peer could set any field
of any record regardless of who owned it.

Under ``MULTI_WRITER`` there is nothing to enforce — ownership is an ordinary
domain field anyone may change, which is what a card reassignment is — so
these tests pin BOTH poles. A check that fires in the mode that does not want
it would break the fleet's first consumer.
"""

from __future__ import annotations

from scitex_dev.store import NEW_RECORD, WriterPolicy
from scitex_dev.store._errors import WriterConflictError
from scitex_dev.store._hlc import HLC
from scitex_dev.store._oplog import OpEntry, OpKind


def _later_than(store) -> HLC:
    """An HLC just after ``store``'s own clock.

    Not a literal. A fixed small `wall_us` puts the remote op at the epoch,
    LAST_WRITER_WINS correctly keeps the newer local value, and the test then
    fails for a reason that has nothing to do with authorization — which is
    exactly what the first draft of this file did. The offset is 1 ms, small
    enough that `clock.observe` reads it as a peer marginally ahead rather
    than as clock drift.
    """
    return HLC(wall_us=store.clock.now().wall_us + 1_000, logical=0, node="peer")


def _remote_op(store, *, actor: str, seq: int = 1, record: str = "c1") -> OpEntry:
    """An op as it would arrive from a peer, varying only who wrote it."""
    return OpEntry(
        origin="peer",
        seq=seq,
        record=record,
        op=OpKind.UPSERT,
        payload={"id": record, "status": "closed"},
        hlc=_later_than(store),
        actor=actor,
    )


def _owned_by(store, owner: str, record: str = "c1"):
    """Seed one record whose domain owner is ``owner``."""
    store.put(
        {"id": record, "status": "open"},
        expected_revision=NEW_RECORD,
        owner=owner,
    )
    return store


def _refusal(store, entry):
    """Apply and return the refusal, or None.

    Returned rather than asserted inside a `raises` block so each test keeps
    to one assertion.
    """
    try:
        store.apply_remote(entry)
    except WriterConflictError as exc:
        return exc
    return None


# -- SINGLE_WRITER: the mode whose entire point is the ownership gate ---------


def test_a_remote_op_from_a_non_owner_is_refused(make_store):
    """The hole: replication used to bypass the ownership gate entirely."""
    # Arrange
    store = _owned_by(make_store("local", policy=WriterPolicy.SINGLE_WRITER), "alice")

    # Act
    error = _refusal(store, _remote_op(store, actor="mallory"))

    # Assert
    assert error is not None


def test_a_remote_op_from_the_owner_is_applied(make_store):
    """The control pole: the gate must not reject the legitimate writer."""
    # Arrange
    store = _owned_by(make_store("local", policy=WriterPolicy.SINGLE_WRITER), "alice")

    # Act
    result = store.apply_remote(_remote_op(store, actor="alice"))

    # Assert
    assert result.row.values["status"] == "closed"


def test_a_remote_op_for_a_new_record_is_applied(make_store):
    """Nothing to own yet, so nothing to check — mirrors `put`'s own rule."""
    # Arrange
    store = make_store("local", policy=WriterPolicy.SINGLE_WRITER)

    # Act
    result = store.apply_remote(_remote_op(store, actor="mallory", record="brand-new"))

    # Assert
    assert result.created is True


def test_the_refusal_names_the_actual_owner(make_store):
    """An operator's next move is to find who owns it, so say so."""
    # Arrange
    store = _owned_by(make_store("local", policy=WriterPolicy.SINGLE_WRITER), "alice")

    # Act
    error = _refusal(store, _remote_op(store, actor="mallory"))

    # Assert
    assert "alice" in str(error)


def test_a_remote_handover_from_a_non_owner_is_refused(make_store):
    """Ownership must not be transferable by whoever asks loudest.

    HANDOVER is the one op that rewrites the owner field, so an unchecked
    remote handover would let any peer take any record and then write it
    legitimately forever after.
    """
    # Arrange
    store = _owned_by(make_store("local", policy=WriterPolicy.SINGLE_WRITER), "alice")
    entry = OpEntry(
        origin="peer",
        seq=1,
        record="c1",
        op=OpKind.HANDOVER,
        payload={"to": "mallory"},
        hlc=_later_than(store),
        actor="mallory",
    )

    # Act
    error = _refusal(store, entry)

    # Assert
    assert error is not None


# -- MULTI_WRITER: the mode the fleet's first consumer actually runs ----------


def test_multi_writer_applies_a_remote_op_from_anyone(make_store):
    """Cards are reassigned by whoever is looking at the board.

    If the new check fired here it would break the only consumer this
    primitive has been designed for, so this pole is pinned deliberately.
    """
    # Arrange
    store = _owned_by(make_store("local", policy=WriterPolicy.MULTI_WRITER), "alice")

    # Act
    result = store.apply_remote(_remote_op(store, actor="mallory"))

    # Assert
    assert result.row.values["status"] == "closed"


def test_multi_writer_applies_a_remote_handover_from_anyone(make_store):
    """Reassigning someone else's card is the normal case, not an attack."""
    # Arrange
    store = _owned_by(make_store("local", policy=WriterPolicy.MULTI_WRITER), "alice")
    entry = OpEntry(
        origin="peer",
        seq=1,
        record="c1",
        op=OpKind.HANDOVER,
        payload={"to": "bob"},
        hlc=_later_than(store),
        actor="mallory",
    )

    # Act
    result = store.apply_remote(entry)

    # Assert
    assert result.row.owner == "bob"

# EOF
