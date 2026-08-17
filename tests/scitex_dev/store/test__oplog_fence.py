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

from scitex_dev.store._errors import StoreError, SupersededFenceError
from scitex_dev.store._hlc import HLC
from scitex_dev.store._oplog import (
    FENCE_UNKNOWN,
    OpEntry,
    OpKind,
    assert_not_superseded,
)
from scitex_dev.store._replication import replay


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


def test_a_fence_survives_a_round_trip(local):
    """The fence PERSISTS — this replaces the boundary test that pinned the gap.

    Its predecessor, `test_a_fence_does_not_survive_a_round_trip_yet`,
    asserted the opposite on purpose: the field existed but `_store_op` did
    not write it, and a field that silently fails to persist is a trap rather
    than a feature. That test was written to FAIL the moment persistence
    landed, forcing whoever added it back here. It did exactly that, and this
    is the replacement.
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
    assert read_back.fence == 3


def test_a_store_starts_with_no_fence_for_an_unknown_peer(local):
    """An unheard-of peer is unfenced, not fenced at some arbitrary value."""
    # Arrange
    source = "never-seen"

    # Act
    fence = local.fence(source)

    # Assert
    assert fence == FENCE_UNKNOWN


def test_a_recorded_fence_is_read_back(local):
    """set_fence / fence round-trip through the cursor table."""
    # Arrange
    local.set_fence("peer", 4)

    # Act
    fence = local.fence("peer")

    # Assert
    assert fence == 4


def test_lowering_a_fence_is_refused(local):
    """Lowering re-admits the writer the fence was raised to exclude."""
    # Arrange
    local.set_fence("peer", 4)

    # Act
    error = None
    try:
        local.set_fence("peer", 3)
    except StoreError as exc:
        error = exc

    # Assert
    assert error is not None


def test_recording_a_fence_leaves_the_cursor_untouched(local):
    """The two share a table; they must not overwrite one another."""
    # Arrange
    local.set_cursor("peer", 7)

    # Act
    local.set_fence("peer", 2)

    # Assert
    assert local.cursor("peer") == 7


def test_advancing_the_cursor_leaves_the_fence_untouched(local):
    """The same invariant from the other direction."""
    # Arrange
    local.set_fence("peer", 2)

    # Act
    local.set_cursor("peer", 7)

    # Assert
    assert local.fence("peer") == 2


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


# -- END TO END through replay(), which is the claim that matters ------------
#
# Everything above tests the pure function and the persistence separately.
# Neither proves the two are CONNECTED. A guard that is implemented, stored
# and never called is the failure this whole card has been about, so the
# acceptance test is the INVERSION run through the real entry point.


def _remote_entry(seq: int, *, fence: int, origin: str = "peer") -> OpEntry:
    """An op as it would arrive from a peer."""
    return OpEntry(
        origin=origin,
        seq=seq,
        record=f"card-{seq}",
        op=OpKind.UPSERT,
        payload={"id": f"card-{seq}", "status": "open"},
        hlc=HLC(wall_us=seq, logical=0, node=origin),
        fence=fence,
    )


def test_replay_rejects_a_batch_from_a_superseded_writer(local):
    """THE ACCEPTANCE TEST: a demoted peer's ops do not get applied.

    This is the one that would have failed before the wiring, and the reason
    the pure-function tests were not enough on their own.
    """
    # Arrange
    local.set_fence("peer", 5)

    # Act
    error = None
    try:
        replay(local, "peer", [_remote_entry(1, fence=2)])
    except SupersededFenceError as exc:
        error = exc

    # Assert
    assert error is not None


def test_replay_applies_a_batch_from_the_current_writer(local):
    """The control pole: the wiring must not reject everything."""
    # Arrange
    local.set_fence("peer", 5)

    # Act
    result = replay(local, "peer", [_remote_entry(1, fence=5)])

    # Assert
    assert result.applied == 1


def test_replay_does_not_adopt_the_fence_it_accepted(local):
    """THE EVICTION REGRESSION. Replay reads the fence; it must not write it.

    This test is the INVERSION of its predecessor,
    `test_replay_adopts_the_fence_it_accepted`, which asserted
    `local.fence("peer") == 4` after replaying an entry carrying `fence=4`.
    That assertion pinned a bug as a requirement.

    Adoption made the fence self-asserting: the batch being authorised
    carried the authority that authorised it. Since `set_fence` refuses to
    descend, one accepted batch naming an origin and a large fence excluded
    that origin PERMANENTLY, with no way back through the public API. No
    attacker is needed — a genesis log minted with a fence, or any peer
    relaying ops it received, reaches the same place.

    Data replays transitively; authority does not. See ADR-0011.
    """
    # Arrange
    local.set_fence("peer", 1)

    # Act
    replay(local, "peer", [_remote_entry(1, fence=4)])

    # Assert
    assert local.fence("peer") == 1


def test_a_batch_cannot_evict_the_origin_it_names(local):
    """The whole hazard in one test: an honest peer must survive a big claim.

    A batch arrives claiming origin "peer" under a large fence. "peer" then
    writes normally — every local write carries the fence that node holds,
    which for an unpromoted node is 0. Before the fix the first batch left
    fence(peer)=999 and every later op from the real peer was rejected
    forever.
    """
    # Arrange
    replay(local, "peer", [_remote_entry(1, fence=999)])

    # Act
    result = replay(local, "peer", [_remote_entry(2, fence=FENCE_UNKNOWN)])

    # Assert
    assert result.applied == 1


def test_a_later_batch_below_the_administered_fence_is_rejected(local):
    """The sequence the fence exists for, played out in order.

    A peer is promoted to fence 4 by something that authenticated it, is
    demoted, and its stale process sends more ops under fence 2. Those ops
    are contiguous and well-clocked; only the fence stops them.

    The promotion is now an explicit `set_fence` rather than a side effect of
    the first batch — which is the only change, and the point.
    """
    # Arrange
    local.set_fence("peer", 4)

    # Act
    error = None
    try:
        replay(local, "peer", [_remote_entry(1, fence=2)])
    except SupersededFenceError as exc:
        error = exc

    # Assert
    assert error is not None


def test_an_unfenced_peer_still_replays(local):
    """Nothing that worked before the fence existed may stop working.

    Every op in the fleet today carries FENCE_UNKNOWN, so if this regressed
    the feature would break all replication the moment it shipped.
    """
    # Arrange
    entries = [_remote_entry(1, fence=FENCE_UNKNOWN)]

    # Act
    result = replay(local, "peer", entries)

    # Assert
    assert result.applied == 1


# -- a node writes under the authority it HOLDS -------------------------------
#
# The other half of the fix. Judging peers by a fence while stamping your own
# ops with "no authority at all" is a suicide pact: the first real promotion
# anywhere makes every honest node's own writes fail their peers' checks.


def test_a_local_write_carries_the_nodes_own_fence(local):
    """A promoted node's ops must claim the promotion."""
    # Arrange
    local.set_fence(local.node, 3)

    # Act
    result = local.put({"id": "c1", "status": "open"}, expected_revision=None)

    # Assert
    assert result.op.fence == 3


def test_a_local_write_is_unfenced_until_the_node_is_promoted(local):
    """The default must not change for a fleet that never fences."""
    # Arrange
    # (nothing — a fresh store has been promoted by nobody)

    # Act
    result = local.put({"id": "c1", "status": "open"}, expected_revision=None)

    # Assert
    assert result.op.fence == FENCE_UNKNOWN


# -- the way back down --------------------------------------------------------
#
# `set_fence` refuses to descend, which is right for the replication path and
# wrong as an absolute: a fence recorded in error excludes a healthy host, and
# before `rescind_fence` the only remedy was hand-editing the cursor table.


def test_a_fence_can_be_rescinded(local):
    """The recovery that did not exist."""
    # Arrange
    local.set_fence("peer", 9)

    # Act
    local.rescind_fence("peer", 0, reason="recorded from an unauthenticated batch")

    # Assert
    assert local.fence("peer") == 0


def test_rescinding_readmits_the_evicted_origin(local):
    """Recovery is judged by the peer replicating again, not by an integer."""
    # Arrange
    local.set_fence("peer", 9)
    local.rescind_fence("peer", 0, reason="recorded in error")

    # Act
    result = replay(local, "peer", [_remote_entry(1, fence=FENCE_UNKNOWN)])

    # Assert
    assert result.applied == 1


def test_rescinding_without_a_reason_is_refused(local):
    """Re-admitting an excluded writer must state its justification in code."""
    # Arrange
    local.set_fence("peer", 9)

    # Act
    error = None
    try:
        local.rescind_fence("peer", 0, reason="   ")
    except StoreError as exc:
        error = exc

    # Assert
    assert error is not None


def test_rescinding_leaves_the_cursor_untouched(local):
    """The fence and the cursor share a row; lowering one must not reset the
    other, or recovery would silently re-request applied ops."""
    # Arrange
    local.set_cursor("peer", 7)
    local.set_fence("peer", 9)

    # Act
    local.rescind_fence("peer", 0, reason="recorded in error")

    # Assert
    assert local.cursor("peer") == 7


# EOF
