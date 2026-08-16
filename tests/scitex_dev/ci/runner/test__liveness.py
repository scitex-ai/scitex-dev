#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The gap PS-224 cannot see: registered is not the same as ONLINE.

The case these are written from is real. On 2026-08-15 every org runner
carrying `spartan-cpu` and `scitex-ci` was offline, 49 repositories pinned one
of them, and PS-224 reported nothing — correctly, because both labels ARE in
the machine registry. The auditor was satisfied while no job could start.
"""

from __future__ import annotations

import pytest

from scitex_dev.ci.runner._liveness import (
    Liveness,
    Runner,
    classify_label,
    parse_runners,
    probe,
    render,
)

SPARTAN = frozenset({"self-hosted", "Linux", "X64", "spartan-cpu", "scitex-ci"})
ORG_CPU = frozenset({"self-hosted", "Linux", "X64", "scitex-org-cpu"})

ONLINE_ORG = Runner("scitex-01-org-cpu-01", "online", ORG_CPU)
OFFLINE_SPARTAN = Runner("spartan-cpu-org-01", "offline", SPARTAN)


def test_an_online_carrier_serves_the_destination() -> None:
    # Arrange
    wanted = ["self-hosted", "Linux", "X64", "scitex-org-cpu"]
    # Act
    verdict = classify_label(wanted, [ONLINE_ORG, OFFLINE_SPARTAN])
    # Assert
    assert verdict.liveness is Liveness.SERVED


def test_a_registered_but_offline_carrier_does_not_serve() -> None:
    """THE WHOLE POINT. `scitex-ci` is in the registry and nothing can run it.

    PS-224 passes this destination because the label is KNOWN. GitHub queues
    the job forever rather than rejecting it, so nothing anywhere reports.
    """
    # Arrange
    wanted = ["self-hosted", "Linux", "X64", "scitex-ci"]
    # Act
    verdict = classify_label(wanted, [ONLINE_ORG, OFFLINE_SPARTAN])
    # Assert
    assert verdict.liveness is Liveness.UNSERVED


def test_a_busy_online_runner_still_serves() -> None:
    """BUSY IS NOT DOWN, and conflating them invents outages.

    figrecipe separated QUEUE time from EXECUTION time on the same day; a
    saturated healthy pool must not read as an unservable label.
    """
    # Arrange
    busy = Runner("scitex-02-org-cpu-01", "online", ORG_CPU)
    # Act
    verdict = classify_label(sorted(ORG_CPU), [busy])
    # Assert
    assert verdict.liveness is Liveness.SERVED


def test_a_partial_label_match_does_not_serve() -> None:
    """GitHub matches by SUPERSET, so a subset carrier is not a carrier."""
    # Arrange
    partial = Runner("half", "online", frozenset({"scitex-ci"}))
    # Act
    verdict = classify_label(["self-hosted", "Linux", "X64", "scitex-ci"], [partial])
    # Assert
    assert verdict.liveness is Liveness.UNSERVED


def test_a_richer_runner_still_serves_a_narrower_request() -> None:
    """Superset the other way round IS a match — the control for the test above."""
    # Arrange
    rich = Runner("rich", "online", ORG_CPU | {"sac-control-plane"})
    # Act
    verdict = classify_label(sorted(ORG_CPU), [rich])
    # Assert
    assert verdict.liveness is Liveness.SERVED


def test_the_verdict_names_the_carriers() -> None:
    """A "served" answer must be checkable, not taken on trust."""
    # Arrange
    wanted = sorted(ORG_CPU)
    # Act
    verdict = classify_label(wanted, [ONLINE_ORG])
    # Assert
    assert verdict.carriers == ("scitex-01-org-cpu-01",)


def test_an_unavailable_inventory_is_unknown_not_unserved() -> None:
    """THE THIRD VALUE, and the reason this is safe to schedule.

    Calling an unreachable API an outage raises a false alarm every time
    GitHub hiccups, and a probe that cries wolf is one nobody reads.
    """
    # Arrange
    runners = None
    # Act
    verdict = classify_label(["scitex-ci"], runners)
    # Assert
    assert verdict.liveness is Liveness.UNKNOWN


def test_unknown_does_not_block() -> None:
    """A broken instrument is not an outage."""
    # Arrange
    verdict = classify_label(["scitex-ci"], None)
    # Act
    blocks = verdict.blocks
    # Assert
    assert blocks is False


def test_an_empty_runner_list_is_an_answer_not_a_failure() -> None:
    """`[]` means "asked, and the org has none" — that DOES block."""
    # Arrange
    runners: list[Runner] = []
    # Act
    verdict = classify_label(["scitex-ci"], runners)
    # Assert
    assert verdict.liveness is Liveness.UNSERVED


def test_a_valid_payload_parses() -> None:
    # Arrange
    payload = {
        "runners": [
            {"name": "a", "status": "online", "labels": [{"name": "scitex-ci"}]}
        ]
    }
    # Act
    runners = parse_runners(payload)
    # Assert
    assert runners == (Runner("a", "online", frozenset({"scitex-ci"})),)


def test_an_empty_runner_payload_parses_to_an_empty_tuple() -> None:
    """Distinct from None: the API answered and there are none."""
    # Arrange
    payload = {"runners": []}
    # Act
    runners = parse_runners(payload)
    # Assert
    assert runners == ()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not a dict",
        {"message": "Not Found"},
        {"runners": "not a list"},
        {"runners": [{"name": "a", "status": "online"}]},
        {"runners": [{"name": "a", "labels": [{"name": "x"}]}]},
    ],
)
def test_an_unrecognisable_payload_is_none_not_empty(payload: object) -> None:
    """`None` and `()` must never be confused.

    Measured cousin, 2026-08-15: `gh api` printed a 404 BODY to stdout, an
    emptiness test never fired, and 76 repositories were recorded as having a
    variable when 8 had none. Here the same conflation would report every
    destination as unserved, or — worse, depending which way it collapsed —
    as fine.
    """
    # Arrange
    given = payload
    # Act
    runners = parse_runners(given)
    # Assert
    assert runners is None


def test_the_probe_dedups_identical_destinations() -> None:
    """80 references to one label set is one question, asked once."""
    # Arrange
    dests = [["scitex-ci"], ["scitex-ci"], ["scitex-org-cpu"]]
    # Act
    report = probe(dests, [ONLINE_ORG])
    # Assert
    assert len(report.verdicts) == 2


def test_the_probe_orders_stably() -> None:
    """An unstable order turns a re-run into a diff."""
    # Arrange
    dests = [["z-label"], ["a-label"]]
    # Act
    report = probe(dests, [ONLINE_ORG])
    # Assert
    assert [sorted(v.labels)[0] for v in report.verdicts] == ["a-label", "z-label"]


def test_the_render_warns_when_nothing_could_be_judged() -> None:
    # Arrange
    report = probe([["scitex-ci"]], None)
    # Act
    text = render(report)
    # Assert
    assert "COULD NOT BE JUDGED" in text


def test_a_judged_render_carries_no_warning() -> None:
    """Positive control: a renderer that always warned would pass the test
    above and teach every reader to skip the line."""
    # Arrange
    report = probe([sorted(ORG_CPU)], [ONLINE_ORG])
    # Act
    text = render(report)
    # Assert
    assert "COULD NOT BE JUDGED" not in text


def test_the_render_counts_the_unserved() -> None:
    # Arrange
    report = probe([["scitex-ci"], sorted(ORG_CPU)], [ONLINE_ORG])
    # Act
    text = render(report)
    # Assert
    assert "1 with no online carrier" in text


def test_no_destinations_says_so_rather_than_reporting_health() -> None:
    """Nothing to check is not the same as everything is fine."""
    # Arrange
    report = probe([], [ONLINE_ORG])
    # Act
    text = render(report)
    # Assert
    assert "no runner destinations found" in text


# EOF
