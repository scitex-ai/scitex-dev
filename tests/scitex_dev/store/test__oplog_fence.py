#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the oplog FENCE — the "was this writer still entitled?" check.

Ported from the closed PR #520, which is the one piece of that branch that
survives ADR-0006 Decision 9. Everything else there rested on a
single-writer-per-record model the ADR rejected; fencing does not. Under
multi-writer the hazard is if anything sharper: field-level merge resolves
who wrote LAST and has no opinion on who was ALLOWED to, so a demoted
writer's field simply wins on recency.

Contiguity proves nothing was missed. Ordering proves what came first.
Neither notices a writer that was demoted, partitioned away or replaced and
kept running — its ops are contiguous, well-clocked and well-formed.
"""

from __future__ import annotations

import pytest

from scitex_dev.store._errors import SupersededFenceError
from scitex_dev.store._hlc import HLC
from scitex_dev.store._oplog import (
    FENCE_UNKNOWN,
    OpEntry,
    OpKind,
    assert_not_superseded,
)


def _entry(seq: int, *, fence: int = FENCE_UNKNOWN, origin: str = "node-a") -> OpEntry:
    """One well-formed op, varying only the fence under test."""
    return OpEntry(
        origin=origin,
        seq=seq,
        record="card-1",
        op=OpKind.UPSERT,
        payload={"status": "open"},
        hlc=HLC(wall_us=1, logical=0, node=origin),
        fence=fence,
    )


def _rejection(entries, *, fence: int, source: str = "node-a"):
    """Run the check and return the error it raised, or None.

    Returning the exception rather than asserting inside a `raises` block
    keeps each test to ONE assertion while still letting a test inspect the
    message — the alternative is a `raises` block plus asserts, which is the
    two-assertion shape TQ007 exists to prevent.
    """
    try:
        assert_not_superseded(entries, fence=fence, source=source)
    except SupersededFenceError as exc:
        return exc
    return None


# -- the rule -----------------------------------------------------------------


def test_an_op_below_the_accepted_fence_is_rejected():
    """A demoted writer's op must not replicate as legitimate."""
    # Arrange
    entries = [_entry(1, fence=1)]

    # Act
    error = _rejection(entries, fence=2)

    # Assert
    assert error is not None


def test_an_op_at_the_accepted_fence_is_allowed():
    """The current authority is still the authority."""
    # Arrange
    entries = [_entry(1, fence=2)]

    # Act
    error = _rejection(entries, fence=2)

    # Assert
    assert error is None


def test_an_op_above_the_accepted_fence_is_allowed():
    """A newly promoted writer must not be rejected by a stale local fence."""
    # Arrange
    entries = [_entry(1, fence=5)]

    # Act
    error = _rejection(entries, fence=2)

    # Assert
    assert error is None


def test_a_later_entry_in_the_batch_is_also_checked():
    """The check must not stop at the first entry.

    A batch whose head is current and whose tail is stale is exactly what a
    relayed batch from a partitioned peer looks like.
    """
    # Arrange
    entries = [_entry(1, fence=3), _entry(2, fence=1)]

    # Act
    error = _rejection(entries, fence=3)

    # Assert
    assert error is not None


# -- the unfenced transition, which is where this starts to bite --------------


def test_unfenced_ops_pass_while_the_origin_has_never_been_fenced():
    """An origin is not judged by an authority it never had."""
    # Arrange
    entries = [_entry(1, fence=FENCE_UNKNOWN)]

    # Act
    error = _rejection(entries, fence=FENCE_UNKNOWN)

    # Assert
    assert error is None


def test_unfenced_ops_are_rejected_once_a_real_fence_is_accepted():
    """After an origin issues a fence, its unfenced ops ARE stale."""
    # Arrange
    entries = [_entry(1, fence=FENCE_UNKNOWN)]

    # Act
    error = _rejection(entries, fence=1)

    # Assert
    assert error is not None


# -- degenerate input ---------------------------------------------------------


def test_an_empty_batch_is_not_an_error():
    """Nothing to judge. Mirrors assert_contiguous's handling."""
    # Arrange
    entries: list[OpEntry] = []

    # Act
    error = _rejection(entries, fence=7)

    # Assert
    assert error is None


# -- the message has to be actionable ----------------------------------------


def test_the_error_names_the_ops_own_fence():
    """Which authority wrote it — half of what an operator needs."""
    # Arrange
    entries = [_entry(1, fence=1)]

    # Act
    error = _rejection(entries, fence=4)

    # Assert
    assert "fence 1" in str(error)


def test_the_error_names_the_accepted_fence():
    """Which authority is current — the other half."""
    # Arrange
    entries = [_entry(1, fence=1)]

    # Act
    error = _rejection(entries, fence=4)

    # Assert
    assert "fence 4" in str(error)


def test_the_error_names_the_offending_origin():
    """The remedy is to stop a specific writer, so name it."""
    # Arrange
    entries = [_entry(1, fence=1, origin="node-b")]

    # Act
    error = _rejection(entries, fence=4, source="node-b")

    # Assert
    assert "node-b" in str(error)


# -- the field itself ---------------------------------------------------------


def test_an_entry_defaults_to_unfenced():
    """Existing callers must keep working without naming a fence."""
    # Arrange
    entry = OpEntry(
        origin="node-a",
        seq=1,
        record="card-1",
        op=OpKind.UPSERT,
        payload={},
        hlc=HLC(wall_us=1, logical=0, node="node-a"),
    )

    # Act
    fence = entry.fence

    # Assert
    assert fence == FENCE_UNKNOWN


def test_a_fence_does_not_survive_a_round_trip_yet(local):
    """PINS A KNOWN GAP: the fence is in-memory only, and that is deliberate.

    `Store._store_op` writes the seven columns of `_OPLOG_COLUMNS`, and
    `fence` is not among them. A fence set on an entry is therefore DROPPED
    on write and reads back as FENCE_UNKNOWN.

    This test exists because a field that silently fails to persist is a
    trap: every signature accepts it, nothing rejects it, and the loss shows
    up as "the fence was never set" rather than as an error. Asserting the
    CURRENT behaviour converts a hidden trap into a stated boundary — and it
    FAILS the moment persistence is added, which is exactly when someone
    should be forced to come back and delete it.

    Adding the column is a migration: `CREATE TABLE IF NOT EXISTS` will not
    add it to stores that already exist. That migration lands together with
    the replay wiring, not before it.
    """
    # Arrange
    entry = OpEntry(
        origin=local.node,
        seq=1,
        record="card-1",
        op=OpKind.UPSERT,
        payload={"id": "card-1", "status": "open"},
        hlc=HLC(wall_us=1, logical=0, node=local.node),
        fence=3,
    )
    local._store_op(entry)

    # Act
    read_back = local.changes_since(local.node, 0)[0]

    # Assert
    assert read_back.fence == FENCE_UNKNOWN


def test_a_negative_fence_is_refused_at_construction():
    """A negative fence would sort below "no authority at all"."""
    # Arrange
    kwargs = dict(
        origin="node-a",
        seq=1,
        record="card-1",
        op=OpKind.UPSERT,
        payload={},
        hlc=HLC(wall_us=1, logical=0, node="node-a"),
        fence=-1,
    )

    # Act
    # Assert
    with pytest.raises(ValueError):
        OpEntry(**kwargs)


# EOF
