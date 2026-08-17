#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/ecosystem/_cmds/test__list_exemptions.py

"""`ecosystem list-exemptions` must never present a partial count as a total.

The command exists because exceptions are permitted only if they stay
visible. That makes ONE failure mode dominant, and it is not a crash: it is
the command cheerfully printing "3 exemptions" when it could only read 18 of
70 packages. That answer is wrong in the reassuring direction, and it gets
MORE reassuring as checkouts go missing — a register that under-reports as it
degrades is worse than no register, because nobody doubts it.

So the tests below are mostly about the coverage half of the answer, not the
exemption half.
"""

from __future__ import annotations

from scitex_dev._cli.ecosystem._cmds._list_exemptions import (
    _emit_human,
    build_report,
)
from scitex_dev._ecosystem._exemption_census import (
    ExemptionCensus,
    ExemptionRow,
)

ROW = ExemptionRow(
    package="scitex-io",
    rule="PS-224",
    path=".github/workflows/x.yml::job",
    line=0,
    reason="needs a Docker-capable runner; the pool has none",
)


def _collect(census, total):
    """Render the human view into a list of (text, is_err) pairs."""
    lines: list[tuple[str, bool]] = []
    _emit_human(
        build_report(census, total),
        lambda text="", err=False: lines.append((text, err)),
    )
    return lines


def test_a_census_with_unread_packages_is_reported_incomplete():
    # Arrange
    census = ExemptionCensus(unreadable=(("scitex-io", "not checked out"),))
    # Act
    report = build_report(census, packages_total=70)
    # Assert
    assert report["complete"] is False


def test_a_fully_read_census_is_reported_complete():
    # Arrange
    census = ExemptionCensus(clean=("scitex-io",))
    # Act
    report = build_report(census, packages_total=1)
    # Assert
    assert report["complete"] is True


def test_unread_packages_are_counted_separately_from_clean_ones():
    """'Declares none' and 'never asked' must not share a bucket."""
    # Arrange
    census = ExemptionCensus(
        clean=("scitex-io",), unreadable=(("scitex-hub", "absent"),)
    )
    # Act
    report = build_report(census, packages_total=2)
    # Assert
    assert report["packages_unread"] == 1


def test_a_clean_package_is_not_counted_as_unread():
    # Arrange
    census = ExemptionCensus(
        clean=("scitex-io",), unreadable=(("scitex-hub", "absent"),)
    )
    # Act
    report = build_report(census, packages_total=2)
    # Assert
    assert report["packages_read"] == 1


def test_a_package_with_exemptions_counts_as_read():
    """It was consulted — that is what read means, findings or not."""
    # Arrange
    census = ExemptionCensus(exemptions=(ROW,))
    # Act
    report = build_report(census, packages_total=1)
    # Assert
    assert report["packages_read"] == 1


def test_the_reason_survives_into_the_payload():
    """An exemption without its reason is an unexplained exception."""
    # Arrange
    census = ExemptionCensus(exemptions=(ROW,))
    # Act
    report = build_report(census, packages_total=1)
    # Assert
    assert report["exemptions"][0]["reason"] == ROW.reason


def test_an_incomplete_report_says_the_total_is_not_fleet_wide():
    """The sentence that stops the number being quoted as a total."""
    # Arrange
    census = ExemptionCensus(
        exemptions=(ROW,), unreadable=(("scitex-hub", "absent"),)
    )
    # Act
    lines = _collect(census, total=70)
    # Assert
    assert any("NOT a fleet-wide count" in text for text, _ in lines)


def test_the_incompleteness_warning_goes_to_stderr():
    """So a piped `| head` cannot silently drop the caveat off the answer."""
    # Arrange
    census = ExemptionCensus(unreadable=(("scitex-hub", "absent"),))
    # Act
    lines = _collect(census, total=70)
    # Assert
    assert all(err for text, err in lines if "INCOMPLETE" in text)


def test_a_complete_report_does_not_cry_incomplete():
    """The warning must be a signal, not decoration on every run."""
    # Arrange
    census = ExemptionCensus(exemptions=(ROW,))
    # Act
    lines = _collect(census, total=1)
    # Assert
    assert not any("INCOMPLETE" in text for text, _ in lines)


def test_each_unread_package_is_named_with_its_reason():
    """A count of unread packages is not actionable; the names are."""
    # Arrange
    census = ExemptionCensus(
        unreadable=(("scitex-hub", "not checked out at /x"),)
    )
    # Act
    lines = _collect(census, total=70)
    # Assert
    assert any("not checked out at /x" in text for text, _ in lines)


# EOF
