# -*- coding: utf-8 -*-
"""`summarize()` ships the SCOPE alongside the count.

`total`/`matching`/`needing_sync` count REMOTE (host, pkg) cells. The
`localhost` column is reference and deliberately excluded. That exclusion
is invisible in the output, so from a container — no reachable fleet host —
the summary reduces to `0 / 0 / []` printed directly beneath a table in
which 45 of 68 localhost cells carried a drift marker (measured
2026-08-11, reported independently by dotfiles).

Every number was correct for the question it answers. Together they read
as an answer to the question the reader asked. A zero with no scope cannot
be told from a zero after checking, so the scope ships with the count.

No mocks (NM001-003): `summarize` is a pure function over the state dict,
so the tests hand it real state shapes.
One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from scitex_dev._ecosystem._packages import summarize


def _state(hosts, rows):
    return {"hosts": list(hosts), "rows": list(rows)}


def _row(pkg, origin, localhost, cells):
    return {"pkg": pkg, "origin": origin, "localhost": localhost, "cells": cells}


def test_summary_reports_zero_hosts_when_none_are_in_scope():
    # Arrange — the container case: rows exist and localhost diverges from
    # origin on every one of them, but no remote host is reachable.
    state = _state(
        [],
        [
            _row("scitex-io", "aaaaaaa", "bbbbbbb", {}),
            _row("scitex-ml", "ccccccc", "ddddddd", {}),
        ],
    )
    # Act
    summ = summarize(state)
    # Assert
    assert summ["hosts_in_scope"] == 0


def test_a_zero_total_is_accompanied_by_a_zero_scope():
    # Arrange — same state. `total: 0` alone is what reads as "all clean";
    # it is only honest next to the scope that produced it.
    state = _state([], [_row("scitex-io", "aaaaaaa", "bbbbbbb", {})])
    # Act
    summ = summarize(state)
    # Assert
    assert (summ["total"], summ["hosts_in_scope"]) == (0, 0)


def test_scope_is_nonzero_when_hosts_are_present():
    # Arrange — POSITIVE CONTROL. The two tests above pass both when the
    # scope is computed correctly and when `hosts_in_scope` is hardcoded to
    # 0; on their own they cannot tell the two apart.
    state = _state(
        ["spartan", "scitex-nas-03"],
        [_row("scitex-io", "aaaaaaa", "aaaaaaa", {"spartan": "aaaaaaa"})],
    )
    # Act
    summ = summarize(state)
    # Assert
    assert summ["hosts_in_scope"] == 2


def test_localhost_divergence_is_still_excluded_from_the_count():
    # Arrange — the exclusion is DELIBERATE and this pins it: localhost
    # differs from origin, one remote host matches. The count is about
    # sync targets, and localhost is not one.
    state = _state(
        ["spartan"],
        [_row("scitex-io", "aaaaaaa", "zzzzzzz", {"spartan": "aaaaaaa"})],
    )
    # Act
    summ = summarize(state)
    # Assert
    assert (summ["total"], summ["matching"]) == (1, 1)


def test_a_diverging_remote_host_is_counted_and_named():
    # Arrange — second POSITIVE CONTROL: the counter must still detect real
    # remote drift, otherwise the test above is indistinguishable from a
    # summarizer that counts nothing at all.
    state = _state(
        ["spartan"],
        [_row("scitex-io", "aaaaaaa", "aaaaaaa", {"spartan": "zzzzzzz"})],
    )
    # Act
    summ = summarize(state)
    # Assert
    assert summ["needing_sync"] == [{"host": "spartan", "pkg": "scitex-io"}]


# EOF
