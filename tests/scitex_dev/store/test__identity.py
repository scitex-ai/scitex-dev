#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for store identity — telling "you are me" from "you descend from me".

The verdict is FOUR-valued on purpose. A boolean same/different would fold
FORK together with UNRELATED — a fork needs reconciling, an unrelated store
needs the caller to stop pointing at it — and it would fold UNKNOWN in with
one of them, which is how "we did not check" becomes "we checked".
"""

from __future__ import annotations

import pytest

from scitex_dev.store import (
    UNKNOWN_SYSTEM,
    IdentityVerdict,
    StoreIdentity,
    StoreIdentityMismatchError,
    StoreIdentityUnknownError,
    assert_same_store,
    compare_identity,
)

LINEAGE = "1d55dd6e-3d2a-4c24-a429-a78835ab988f"


def _identity(uuid=LINEAGE, system="pg:7100/scitex"):
    return StoreIdentity(store_uuid=uuid, system_identifier=system)


def test_one_store_seen_twice_is_same():
    # Arrange
    left, right = _identity(), _identity()
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.SAME


def test_one_lineage_on_two_instances_is_a_fork():
    # Arrange — the 2026-08-11 shape: two Postgres instances both answering
    # to one store_uuid, each holding records the other never saw.
    left, right = _identity(), _identity(system="pg:7200/scitex")
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.FORK


def test_two_databases_on_one_cluster_are_a_fork():
    # Arrange — DEFECT FIX. The cluster id alone cannot separate these: a
    # pg_dump restored into a second database on the SAME cluster copies the
    # store_uuid and shares the cluster id, so an engine-only discriminator
    # certifies SAME while the two halves diverge independently.
    left = _identity(system="pg:7100/scitex")
    right = _identity(system="pg:7100/scitex_restored")
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.FORK


def test_different_lineages_are_unrelated():
    # Arrange
    left, right = _identity(), _identity(uuid="00000000-0000-4000-8000-000000000000")
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.UNRELATED


def test_unrelated_wins_over_a_differing_instance():
    # Arrange — ordering matters: two stores with different lineages are not
    # a fork however their instances compare, and reporting one would send
    # the reader looking for a reconciliation that must not happen.
    left = _identity(system="pg:7100/scitex")
    right = _identity(uuid="00000000-0000-4000-8000-000000000000", system="pg:7200/x")
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.UNRELATED


def test_two_unknown_instances_do_not_certify_sameness():
    # Arrange — both sides agree on every field while both say "unknown".
    # Calling that SAME would certify from two absences of evidence.
    left, right = _identity(system=UNKNOWN_SYSTEM), _identity(system=UNKNOWN_SYSTEM)
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.UNKNOWN


def test_one_unknown_instance_is_enough_to_refuse():
    # Arrange
    left, right = _identity(), _identity(system=UNKNOWN_SYSTEM)
    # Act
    verdict = compare_identity(left, right)
    # Assert
    assert verdict is IdentityVerdict.UNKNOWN


def test_only_same_is_certified():
    # Arrange — `!= FORK` reads as if it means this and does not: it admits
    # UNKNOWN.
    verdicts = [v for v in IdentityVerdict if v.is_certified_same]
    # Act
    got = verdicts
    # Assert
    assert got == [IdentityVerdict.SAME]


def test_assert_same_store_passes_for_one_store():
    # Arrange
    left, right = _identity(), _identity()
    # Act
    result = assert_same_store(left, right)
    # Assert
    assert result is None


def test_a_fork_raises_mismatch():
    # Arrange
    left, right = _identity(), _identity(system="pg:7200/scitex")
    # Act
    # Assert
    with pytest.raises(StoreIdentityMismatchError, match="FORK"):
        assert_same_store(left, right)


def test_unrelated_stores_raise_mismatch():
    # Arrange
    left, right = _identity(), _identity(uuid="00000000-0000-4000-8000-000000000000")
    # Act
    # Assert
    with pytest.raises(StoreIdentityMismatchError, match="UNRELATED"):
        assert_same_store(left, right)


def test_an_unknown_instance_raises_its_own_error():
    # Arrange — a DIFFERENT error from a detected fork, because the remedies
    # differ: a fork needs reconciliation, an unknown needs a grant.
    left, right = _identity(), _identity(system=UNKNOWN_SYSTEM)
    # Act
    # Assert
    with pytest.raises(StoreIdentityUnknownError, match="cannot certify"):
        assert_same_store(left, right)


def test_the_caller_context_reaches_the_traceback():
    # Arrange — "these are two stores" is far less useful than "acking
    # notification n-83 for agent X: these are two stores".
    left, right = _identity(), _identity(system="pg:7200/scitex")
    # Act
    # Assert
    with pytest.raises(StoreIdentityMismatchError, match="acking n-83"):
        assert_same_store(left, right, context="acking n-83")


def test_an_empty_lineage_is_refused():
    # Arrange — an empty lineage makes every store look unrelated to every
    # other, so nothing would ever be reconciled and no fork reported.
    # Act
    # Assert
    with pytest.raises(StoreIdentityUnknownError, match="requires a store_uuid"):
        StoreIdentity(store_uuid="", system_identifier="pg:7100/scitex")


def test_an_empty_instance_is_refused_in_favour_of_unknown():
    # Arrange — an empty string is falsey, and every truthiness check in the
    # fleet would then read "could not determine the instance" as "there is
    # no instance". UNKNOWN_SYSTEM is a value; "" is an absence.
    # Act
    # Assert
    with pytest.raises(StoreIdentityUnknownError, match="requires a system_identifier"):
        StoreIdentity(store_uuid=LINEAGE, system_identifier="")


def test_describe_says_when_the_instance_would_not_identify_itself():
    # Arrange — an empty read must be able to say WHY it is empty.
    identity = _identity(system=UNKNOWN_SYSTEM)
    # Act
    line = identity.describe()
    # Assert
    assert "would not identify itself" in line

# EOF
