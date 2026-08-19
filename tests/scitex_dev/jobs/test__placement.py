#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev.jobs._placement.

Pure functions — no I/O, no mocks. One assertion per test.

The UNSTATED tests are the load-bearing ones. If a later edit collapses
UNSTATED into EXCLUDED, every host that has not yet declared placement
is silently disarmed the moment the change ships — the rollout of the
safety feature becomes the outage. sac measured their equivalent
host-side surface as UNSTATED on 4 of 4 hosts, so that is not a
hypothetical population.
"""

from __future__ import annotations

from scitex_dev.jobs._placement import (
    EXCLUDED,
    PLACED,
    UNSTATED,
    PlacementRecord,
    PlacementUnresolvable,
    decide,
    discover_placement,
)

_HOST = "scitex-compute-04"


# --------------------------------------------------------------------------- #
# UNSTATED — the third state, and the reason this module exists                #
# --------------------------------------------------------------------------- #


def test_a_job_nobody_placed_is_unstated():
    # Arrange
    records: list[PlacementRecord] = []
    # Act
    decision = decide("some.job", records, host=_HOST)
    # Assert
    assert decision.state == UNSTATED


def test_an_unstated_job_is_armed():
    # Arrange — the safety property: absence means "no opinion yet".
    records: list[PlacementRecord] = []
    # Act
    decision = decide("some.job", records, host=_HOST)
    # Assert
    assert decision.armed is True


def test_unstated_is_not_excluded():
    # Arrange — collapsing these two is the outage this guards against.
    records: list[PlacementRecord] = []
    # Act
    decision = decide("some.job", records, host=_HOST)
    # Assert
    assert decision.state != EXCLUDED


def test_a_job_is_unstated_even_when_its_neighbours_are_placed():
    # Arrange — the state is per-JOB, not per-fleet. A fleet that has
    # begun declaring placement must not disarm the jobs it has not
    # reached yet.
    records = [PlacementRecord(job="other.job", hosts=(_HOST,))]
    # Act
    decision = decide("undeclared.job", records, host=_HOST)
    # Assert
    assert decision.state == UNSTATED


# --------------------------------------------------------------------------- #
# PLACED / EXCLUDED                                                            #
# --------------------------------------------------------------------------- #


def test_an_explicitly_named_host_is_placed():
    # Arrange
    records = [PlacementRecord(job="j", hosts=(_HOST, "other-host"))]
    # Act
    decision = decide("j", records, host=_HOST)
    # Assert
    assert decision.state == PLACED


def test_a_host_not_named_is_excluded():
    # Arrange
    records = [PlacementRecord(job="j", hosts=("some-other-host",))]
    # Act
    decision = decide("j", records, host=_HOST)
    # Assert
    assert decision.state == EXCLUDED


def test_an_excluded_job_is_not_armed():
    # Arrange
    records = [PlacementRecord(job="j", hosts=("some-other-host",))]
    # Act
    decision = decide("j", records, host=_HOST)
    # Assert
    assert decision.armed is False


def test_star_places_the_job_everywhere():
    # Arrange
    records = [PlacementRecord(job="j", hosts="*")]
    # Act
    decision = decide("j", records, host="any-host-at-all")
    # Assert
    assert decision.state == PLACED


def test_two_providers_placing_the_same_job_both_count():
    # Arrange — one provider places it on 02, another on 03.
    records = [
        PlacementRecord(job="j", hosts=("scitex-compute-02",)),
        PlacementRecord(job="j", hosts=("scitex-compute-03",)),
    ]
    # Act
    decision = decide("j", records, host="scitex-compute-03")
    # Assert
    assert decision.state == PLACED


# --------------------------------------------------------------------------- #
# groups — matched when declared, REFUSED when unknowable                      #
# --------------------------------------------------------------------------- #


def test_a_matching_group_places_the_job():
    # Arrange
    records = [PlacementRecord(job="j", groups=("infra",))]
    # Act
    decision = decide("j", records, host=_HOST, host_groups=("infra", "app"))
    # Assert
    assert decision.state == PLACED


def test_a_non_matching_group_excludes_the_job():
    # Arrange — the host declares groups, just not this one.
    records = [PlacementRecord(job="j", groups=("research",))]
    # Act
    decision = decide("j", records, host=_HOST, host_groups=("infra",))
    # Assert
    assert decision.state == EXCLUDED


def _group_refusal():
    """Run the unresolvable-group case and return the raised exception.

    sac measured that no host declares groups today, so this branch
    would otherwise fall through to UNSTATED and arm the job everywhere
    while appearing to have restricted it. Returning the exception keeps
    each test below at exactly one assertion (STX-TQ007) while letting
    them interrogate different facets of it.
    """
    records = [PlacementRecord(job="j", groups=("infra",))]
    try:
        decide("j", records, host=_HOST, host_groups=())
    except PlacementUnresolvable as exc:
        return exc
    return None


def test_a_group_placement_refuses_when_the_host_declares_no_groups():
    # Arrange
    raised = _group_refusal()
    # Act
    refused = isinstance(raised, PlacementUnresolvable)
    # Assert
    assert refused


def test_the_refusal_names_the_job():
    # Arrange
    raised = _group_refusal()
    # Act
    named = raised.job_name
    # Assert
    assert named == "j"


def test_the_refusal_explains_that_ignoring_it_would_arm_the_job():
    # Arrange
    raised = _group_refusal()
    # Act
    message = str(raised)
    # Assert
    assert "would ARM" in message


def test_explicit_hosts_win_over_groups():
    # Arrange — both given; the host matches by name but not by group.
    records = [
        PlacementRecord(job="j", hosts=(_HOST,), groups=("research",))
    ]
    # Act
    decision = decide("j", records, host=_HOST, host_groups=("infra",))
    # Assert
    assert decision.state == PLACED


# --------------------------------------------------------------------------- #
# The decision carries a REASON, not just a verdict                            #
# --------------------------------------------------------------------------- #


def test_the_unstated_reason_says_nobody_declared_it():
    # Arrange
    records: list[PlacementRecord] = []
    # Act
    decision = decide("j", records, host=_HOST)
    # Assert
    assert "no placement declared" in decision.reason


def test_the_excluded_reason_distinguishes_itself_from_unstated():
    # Arrange — an operator asking "why did this not start" needs to
    # tell a deliberate exclusion from an absent declaration; the two
    # have opposite fixes.
    records = [PlacementRecord(job="j", hosts=("elsewhere",))]
    # Act
    decision = decide("j", records, host=_HOST)
    # Assert
    assert "is declared for this job" in decision.reason


# --------------------------------------------------------------------------- #
# discovery federation                                                         #
# --------------------------------------------------------------------------- #


# These filter to the job names they inject rather than asserting on the
# whole discovery output. `discover_placement` also loads every INSTALLED
# `scitex_dev.host_placement` entry point, and scitex-dev registers its
# own — so an exact-equality assertion here passes only where the package
# is NOT installed, which is precisely the difference between a local
# PYTHONPATH run and CI. Measured: these four passed locally and failed on
# all three matrix legs, because PYTHONPATH does not register entry-point
# metadata. A test that asserts on global discovery output is coupled to
# whatever the environment happens to have installed.


def _mine(records, *names: str) -> list[str]:
    """Job names from ``records`` limited to ``names``. Pure."""
    wanted = set(names)
    return [r.job for r in records if r.job in wanted]


def test_discovery_collects_from_an_extra_provider():
    # Arrange
    def _provider() -> list[PlacementRecord]:
        return [PlacementRecord(job="j", hosts=(_HOST,))]

    # Act
    records = discover_placement(extra_providers=[_provider])
    # Assert
    assert _mine(records, "j") == ["j"]


def test_discovery_does_not_dedupe_by_job_name():
    # Arrange — unlike discover_jobs, two providers may each place the
    # same job on different hosts; first-wins would drop the second.
    def _a() -> list[PlacementRecord]:
        return [PlacementRecord(job="j", hosts=("h1",))]

    def _b() -> list[PlacementRecord]:
        return [PlacementRecord(job="j", hosts=("h2",))]

    # Act
    records = discover_placement(extra_providers=[_a, _b])
    # Assert
    assert _mine(records, "j") == ["j", "j"]


def test_a_broken_provider_does_not_wedge_discovery():
    # Arrange
    def _broken() -> list[PlacementRecord]:
        raise RuntimeError("provider exploded")

    def _good() -> list[PlacementRecord]:
        return [PlacementRecord(job="survivor", hosts=(_HOST,))]

    # Act
    records = discover_placement(extra_providers=[_broken, _good])
    # Assert
    assert _mine(records, "survivor") == ["survivor"]


def test_a_non_record_object_is_skipped():
    # Arrange
    def _junk():
        return ["not a placement record"]

    # Act
    records = discover_placement(extra_providers=[_junk])
    # Assert
    assert _mine(records, "not a placement record") == []

# EOF
