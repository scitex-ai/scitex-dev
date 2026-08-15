#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adoption: giving an existing dataset a history the primitive can replay.

The suite's centre of gravity is the pair
``test_a_shared_genesis_leaves_a_later_local_edit_intact`` /
``test_two_independent_genesis_logs_destroy_a_later_local_edit``. Together
they are the reason :func:`~scitex_dev.store._adopt.build_genesis` mints a
portable log under a shared origin instead of letting each host adopt its own
copy. The second asserts a DATA LOSS — the failure the design avoids, pinned
so nobody "simplifies" the shared origin away.

Errors are captured with :func:`_error_from` rather than ``pytest.raises`` so
each test keeps exactly one assertion and can name the message it checks.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Callable

import pytest

from scitex_dev.store import (
    NEW_RECORD,
    StoreError,
    build_genesis,
    genesis_origin,
    install_genesis,
    sync,
    verify_adoption,
)

_PAST_US = 1_000_000_000_000  # a fixed wall stamp, comfortably in the past


def _error_from(call: Callable[[], Any]) -> "StoreError | None":
    """Run ``call`` and hand back the store error it raised, or ``None``."""
    try:
        call()
    except StoreError as exc:
        return exc
    return None


@pytest.fixture
def legacy_records() -> list[dict]:
    """Three records as they would come out of a pre-primitive table."""
    return [
        {"id": "c2", "status": "open"},
        {"id": "c0", "status": "done"},
        {"id": "c1", "status": "open"},
    ]


@pytest.fixture
def origin() -> str:
    return genesis_origin("cards", "20260810")


@pytest.fixture
def genesis(card_schema, legacy_records, origin):
    return build_genesis(
        card_schema, legacy_records, origin=origin, at_us=_PAST_US
    )


# -- building ------------------------------------------------------------
def test_build_genesis_ignores_input_order(card_schema, legacy_records, origin):
    # Arrange
    reversed_records = list(reversed(legacy_records))
    # Act
    first = build_genesis(
        card_schema, legacy_records, origin=origin, at_us=_PAST_US
    )
    second = build_genesis(
        card_schema, reversed_records, origin=origin, at_us=_PAST_US
    )
    # Assert
    assert first == second


def test_build_genesis_numbers_from_one_without_gaps(genesis):
    # Arrange
    expected = [1, 2, 3]
    # Act
    seqs = [entry.seq for entry in genesis]
    # Assert
    assert seqs == expected


def test_build_genesis_names_an_undeclared_field(card_schema, origin):
    # Arrange
    record = {"id": "c0", "nope": 1}
    # Act
    error = _error_from(
        lambda: build_genesis(
            card_schema, [record], origin=origin, at_us=_PAST_US
        )
    )
    # Assert
    assert "nope" in str(error)


def test_build_genesis_refuses_duplicate_identity_keys(card_schema, origin):
    # Arrange
    clashing = [{"id": "c0", "status": "a"}, {"id": "c0", "status": "b"}]
    # Act
    error = _error_from(
        lambda: build_genesis(
            card_schema, clashing, origin=origin, at_us=_PAST_US
        )
    )
    # Assert
    assert "share the identity key" in str(error)


def test_build_genesis_refuses_a_non_positive_stamp(card_schema, origin):
    # Arrange
    bad_stamp = 0
    # Act
    error = _error_from(
        lambda: build_genesis(card_schema, [], origin=origin, at_us=bad_stamp)
    )
    # Assert
    assert "at_us" in str(error)


def test_genesis_origin_refuses_a_missing_stamp():
    # Arrange
    dataset = "cards"
    # Act
    error = _error_from(lambda: genesis_origin(dataset, ""))
    # Assert
    assert "unique per adoption" in str(error)


# -- installing ----------------------------------------------------------
def test_install_genesis_materialises_every_record(local, genesis):
    # Arrange
    expected = 3
    # Act
    install_genesis(local, genesis)
    # Assert
    assert len(local.rows()) == expected


def test_install_genesis_preserves_field_values(local, genesis):
    # Arrange
    expected = "done"
    # Act
    install_genesis(local, genesis)
    # Assert
    assert local.get(("c0",)).values["status"] == expected


def test_install_genesis_applies_nothing_on_a_second_run(local, genesis):
    # Arrange
    install_genesis(local, genesis)
    # Act
    again = install_genesis(local, genesis)
    # Assert
    assert again.applied == 0


def test_install_genesis_resumes_a_partial_install(local, genesis):
    # Arrange — apply only the first two of three
    install_genesis(local, genesis[:2])
    # Act
    rest = install_genesis(local, genesis)
    # Assert
    assert rest.applied == 1


def test_install_genesis_refuses_a_store_that_already_holds_rows(local, genesis):
    # Arrange — data arrived by some other route
    local.put({"id": "x0", "status": "open"}, expected_revision=NEW_RECORD)
    # Act
    error = _error_from(lambda: install_genesis(local, genesis))
    # Assert
    assert "already holds rows" in str(error)


def test_install_genesis_refuses_a_different_genesis_over_a_partial_one(
    local, card_schema, legacy_records, genesis, origin
):
    # Arrange — a second adoption of the same data, same origin, later stamp
    install_genesis(local, genesis[:2])
    other = build_genesis(
        card_schema, legacy_records, origin=origin, at_us=_PAST_US + 5_000_000
    )
    # Act
    error = _error_from(lambda: install_genesis(local, other))
    # Assert
    assert "does not match" in str(error)


def test_install_genesis_refuses_a_batch_mixing_origins(local, genesis):
    # Arrange
    mixed = [genesis[0], dataclasses.replace(genesis[1], origin="somewhere-else")]
    # Act
    error = _error_from(lambda: install_genesis(local, mixed))
    # Assert
    assert "ONE origin" in str(error)


# -- verification --------------------------------------------------------
def test_verify_adoption_is_silent_on_a_faithful_adoption(
    local, genesis, legacy_records
):
    # Arrange
    install_genesis(local, genesis)
    # Act
    problems = verify_adoption(local, legacy_records)
    # Assert
    assert problems == []


def test_verify_adoption_reports_a_changed_field(local, genesis, legacy_records):
    # Arrange
    install_genesis(local, genesis)
    local.put({"id": "c0", "status": "reopened"}, expected_revision=1)
    # Act
    problems = verify_adoption(local, legacy_records)
    # Assert
    assert "c0.status" in problems[0]


def test_verify_adoption_reports_a_record_that_never_arrived(
    local, genesis, legacy_records
):
    # Arrange — install only two of the three
    install_genesis(local, genesis[:2])
    # Act
    problems = verify_adoption(local, legacy_records)
    # Assert
    assert any("absent from the store" in problem for problem in problems)


# -- the reason genesis is shared ----------------------------------------
def test_a_shared_genesis_leaves_a_later_local_edit_intact(local, peer, genesis):
    """Both hosts install the SAME artefact, so replay has nothing to redo."""
    # Arrange
    install_genesis(local, genesis)
    install_genesis(peer, genesis)
    local.put({"id": "c0", "status": "in_progress"}, expected_revision=1)
    # Act
    sync(local, peer)
    # Assert
    assert local.get(("c0",)).values["status"] == "in_progress"


def test_two_independent_genesis_logs_destroy_a_later_local_edit(
    local, peer, card_schema, legacy_records
):
    """The failure a shared genesis avoids. Asserted, so it stays avoided.

    ``peer`` adopts the same data under its OWN origin, stamped after
    ``local``'s real edit. Every check in the replication layer passes —
    contiguous sequence, honest clock, valid payload — and last-writer-wins
    compares stamps rather than provenance, so the peer's SNAPSHOT of the old
    value silently overwrites a NEWER real edit.
    """
    # Arrange
    install_genesis(
        local,
        build_genesis(
            card_schema,
            legacy_records,
            origin=genesis_origin("cards", "local-run"),
            at_us=_PAST_US,
        ),
    )
    local.put({"id": "c0", "status": "in_progress"}, expected_revision=1)
    later = int(time.time() * 1_000_000) + 60_000_000  # inside the drift guard
    install_genesis(
        peer,
        build_genesis(
            card_schema,
            legacy_records,
            origin=genesis_origin("cards", "peer-run"),
            at_us=later,
        ),
    )
    # Act
    sync(local, peer)
    # Assert — the edit is gone, and nothing raised to say so
    assert local.get(("c0",)).values["status"] == "done"

# EOF
