#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Partition, heal, and the three ways replay is required to REFUSE.

The partition scenario is the point of the whole layer, so it is tested
as a scenario and not only as units: two live hosts, cut off, both still
writing, then healed in both directions -- and the two replicas must end
byte-identical with nothing dropped from either side.

The refusals matter just as much. A gap that warned, a superseded
writer's op that applied, or a re-applied batch that double-counted would
each produce a replica that looks fine and is not, which is the failure
class this design exists to make impossible.

No mocks (NM001-003): real SQLite files and a real PostgreSQL schema via
the ``dialect`` fixture; the "partition" is simply not calling replay.
Refusals are captured through :func:`_refusal` rather than
``pytest.raises`` so that each test still lands on exactly one assertion.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scitex_dev.store import _replay as replay_module
from scitex_dev.store._oplog_model import (
    Op,
    OplogGapError,
    StoreReplayError,
    SupersededFenceError,
)
from scitex_dev.store._replay import heal, replay, replay_all

from .conftest import TABLE, drop_op, inject_op, live_payloads


def _partitioned_writes(pair):
    """Both hosts write, to records each OWNS, with no contact between them."""
    alpha, beta = pair
    for index in range(1, 4):
        alpha.append(TABLE, "a{0}".format(index), "alpha-{0}".format(index))
    for index in range(1, 3):
        beta.append(TABLE, "b{0}".format(index), "beta-{0}".format(index))
    return alpha, beta


def _refusal(source, target, origin="alpha", **kwargs):
    """Run a replay expected to REFUSE and hand back the exception.

    Returning the exception (instead of ``pytest.raises``) keeps every
    test at one assertion while still letting a test inspect the message
    -- and a replay that wrongly SUCCEEDS returns ``None``, which fails
    the isinstance assertion rather than passing quietly.
    """
    try:
        replay(source, target, origin, **kwargs)
    except StoreReplayError as exc:
        return exc
    return None


def _supersede_alpha(alpha, beta):
    """Beta learns alpha is on fence 2; the old writer's op is now stale."""
    replay(alpha, beta, "alpha")
    alpha.bump_fence()
    alpha.append(TABLE, "a4", "written-under-fence-2")
    replay(alpha, beta, "alpha")
    inject_op(
        alpha,
        Op(
            origin="alpha",
            seq=alpha.max_seq("alpha") + 1,
            table_name=TABLE,
            record_key="a5",
            op="upsert",
            payload="from-the-demoted-writer",
            fence=1,
            ts="2026-08-09T00:00:00+00:00",
        ),
    )


# --- the partition scenario ------------------------------------------------


def test_alpha_accepts_writes_while_partitioned(pair):
    # Arrange
    alpha, _beta = pair
    # Act
    alpha.append(TABLE, "a1", "written-offline")
    # Assert
    assert alpha.read(TABLE, "a1").payload == "written-offline"


def test_beta_accepts_writes_while_partitioned(pair):
    # Arrange
    _alpha, beta = pair
    # Act
    beta.append(TABLE, "b1", "also-written-offline")
    # Assert
    assert beta.read(TABLE, "b1").payload == "also-written-offline"


def test_healing_makes_both_replicas_identical(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    # Act
    heal(alpha, beta)
    # Assert
    assert alpha.snapshot() == beta.snapshot()


def test_healing_keeps_every_write_from_both_sides(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    # Act
    heal(alpha, beta)
    # Assert
    assert live_payloads(beta) == {
        "a1": "alpha-1",
        "a2": "alpha-2",
        "a3": "alpha-3",
        "b1": "beta-1",
        "b2": "beta-2",
    }


def test_healing_carries_alpha_writes_to_beta(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    # Act
    heal(alpha, beta)
    # Assert
    assert beta.cursor_for("alpha") == alpha.max_seq("alpha")


def test_healing_carries_beta_writes_to_alpha(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    # Act
    heal(alpha, beta)
    # Assert
    assert alpha.cursor_for("beta") == beta.max_seq("beta")


def test_new_host_joins_by_replaying_from_zero(pair, make_store):
    # Arrange
    alpha, _beta = _partitioned_writes(pair)
    gamma = make_store("gamma")
    # Act
    replay_all(alpha, gamma)
    # Assert
    assert live_payloads(gamma) == {
        "a1": "alpha-1",
        "a2": "alpha-2",
        "a3": "alpha-3",
    }


# --- absence is never an input to a decision -------------------------------


def test_replay_never_deletes_records_target_owns(pair):
    """The 2026-07-30 shape: 2,159 rows died because absence read as delete.

    Alpha's log says nothing whatsoever about beta's records. A
    comparison-based sync would see them missing on alpha and delete them
    on beta. Directed replay cannot: it only ever applies ops that exist.
    """
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    # Act
    replay_all(alpha, beta)
    # Assert
    assert live_payloads(beta)["b1"] == "beta-1"


def test_replay_module_never_reads_materialised_state(pair):
    """Structural: the replay engine cannot even NAME the record table.

    Behaviour tests show it does not delete today. This shows it has no
    way to start, because its decision inputs are the log and one integer.
    """
    # Arrange
    source = Path(replay_module.__file__).read_text(encoding="utf-8")
    # Act
    literals = [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    # Assert
    assert not [text for text in literals if "stx_record" in text]


def test_explicit_deletion_replicates_to_the_peer(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    heal(alpha, beta)
    # Act
    alpha.delete(TABLE, "a2")
    replay(alpha, beta, "alpha")
    # Assert
    assert "a2" not in live_payloads(beta)


# --- refusal 1: a gap in the log ------------------------------------------


def test_replay_with_a_gap_refuses(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    drop_op(alpha, "alpha", 1)
    # Act
    error = _refusal(alpha, beta)
    # Assert
    assert isinstance(error, OplogGapError)


def test_gap_error_names_the_expected_sequence_number(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    drop_op(alpha, "alpha", 1)
    # Act
    error = _refusal(alpha, beta)
    # Assert
    assert "expects seq 1" in str(error)


def test_gap_error_counts_the_lost_ops(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    drop_op(alpha, "alpha", 1)
    # Act
    error = _refusal(alpha, beta)
    # Assert
    assert "1 op(s) lost" in str(error)


def test_gap_leaves_the_cursor_where_it_was(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    drop_op(alpha, "alpha", 1)
    # Act
    _refusal(alpha, beta)
    # Assert
    assert beta.cursor_for("alpha") == 0


def test_gap_inside_a_batch_refuses(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    drop_op(alpha, "alpha", 2)
    # Act
    error = _refusal(alpha, beta)
    # Assert
    assert isinstance(error, OplogGapError)


def test_batching_does_not_hide_a_gap(pair):
    """A hole straddling a batch boundary must refuse like any other."""
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    drop_op(alpha, "alpha", 2)
    # Act
    error = _refusal(alpha, beta, batch_size=1)
    # Assert
    assert isinstance(error, OplogGapError)


# --- refusal 2: a superseded fence ----------------------------------------


def test_op_from_a_superseded_fence_refuses(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    _supersede_alpha(alpha, beta)
    # Act
    error = _refusal(alpha, beta)
    # Assert
    assert isinstance(error, SupersededFenceError)


def test_superseded_fence_error_names_the_current_fence(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    _supersede_alpha(alpha, beta)
    # Act
    error = _refusal(alpha, beta)
    # Assert
    assert "superseded by fence 2" in str(error)


def test_superseded_op_never_reaches_state(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    _supersede_alpha(alpha, beta)
    # Act
    _refusal(alpha, beta)
    # Assert
    assert "a5" not in live_payloads(beta)


def test_ops_under_the_current_fence_still_apply(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    _supersede_alpha(alpha, beta)
    # Act
    _refusal(alpha, beta)
    # Assert
    assert live_payloads(beta)["a4"] == "written-under-fence-2"


# --- refusal 3 (a no-op, not an error): replaying the same batch twice -----


def test_replaying_the_same_batch_twice_changes_nothing(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    batch = alpha.read_since("alpha", 0)
    for entry in batch:
        beta.apply(entry)
    before = beta.snapshot()
    # Act
    for entry in batch:
        beta.apply(entry)
    # Assert
    assert beta.snapshot() == before


def test_second_replay_pass_applies_nothing(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    replay(alpha, beta, "alpha")
    # Act
    outcome = replay(alpha, beta, "alpha")
    # Assert
    assert outcome.applied == 0


def test_repeated_heal_is_stable(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    heal(alpha, beta)
    before = beta.snapshot()
    # Act
    heal(alpha, beta)
    # Assert
    assert beta.snapshot() == before


def test_replay_reports_how_many_ops_applied(pair):
    # Arrange
    alpha, beta = _partitioned_writes(pair)
    # Act
    outcome = replay(alpha, beta, "alpha")
    # Assert
    assert outcome.applied == 3


# EOF
