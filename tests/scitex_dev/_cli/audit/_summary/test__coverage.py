#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The DENOMINATOR behind a CLI-convention verdict.

No mocks (STX-NM002): every test builds a real Click group and drives the
real `_walk`, so the coverage figures are produced by the same code path the
audit uses. Nothing patches the walker or fakes a command tree.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click  # noqa: E402

from scitex_dev._cli.audit._summary._coverage import (  # noqa: E402
    HIDDEN,
    SKIP_REASONS,
    SurfaceCoverage,
    describe_or_unknown,
)
from scitex_dev._cli.audit._summary._walker import _walk  # noqa: E402


def _tree_with_one_hidden():
    """A real 3-node CLI: root, one visible leaf, one hidden leaf."""

    @click.group(invoke_without_command=True)
    def root():
        pass

    @root.command()
    def build():
        pass

    @root.command(hidden=True)
    def oldname():
        pass

    return root


def _walked(cmd, display="demo"):
    cov = SurfaceCoverage()
    _walk(cmd, [], [], display, cov)
    return cov


class TestTheCountExists:
    def test_inspected_commands_are_recorded(self):
        # Arrange
        cov = _walked(_tree_with_one_hidden())
        # Act
        n = len(cov.inspected)
        # Assert — root + visible leaf.
        assert n == 2

    def test_inspected_records_the_command_PATH_not_just_a_count(self):
        # Arrange — a set of paths answers "WHICH command was missed?", which
        # is the question an operator asks when a count looks wrong. An int
        # cannot.
        cov = _walked(_tree_with_one_hidden())
        # Act
        paths = sorted(cov.inspected)
        # Assert
        assert paths == ["demo", "demo build"]


class TestSkipsAreCountedNotDropped:
    def test_a_hidden_command_is_recorded_as_skipped(self):
        # Arrange
        cov = _walked(_tree_with_one_hidden())
        # Act
        skipped = cov.skipped
        # Assert
        assert skipped == {"demo oldname": HIDDEN}

    def test_a_hidden_command_is_NOT_counted_as_inspected(self):
        # Arrange — folding a skip into the inspected count would report
        # coverage the run does not have: the unearned-green shape.
        cov = _walked(_tree_with_one_hidden())
        # Act
        inspected = cov.inspected
        # Assert
        assert "demo oldname" not in inspected

    def test_total_counts_every_command_reached(self):
        # Arrange
        cov = _walked(_tree_with_one_hidden())
        # Act
        total = cov.total
        # Assert — 2 inspected + 1 skipped; nothing silently vanished.
        assert total == 3

    def test_describe_names_the_skip_and_its_reason(self):
        # Arrange
        cov = _walked(_tree_with_one_hidden())
        # Act
        text = cov.describe()
        # Assert
        assert text == "2 command(s) inspected, 1 skipped (1 hidden)"


class TestZeroInspectedIsARefusalNotAPass:
    def test_a_hidden_root_yields_no_coverage(self):
        # Arrange — reachable: the whole CLI is hidden.
        @click.group(hidden=True)
        def root():
            pass

        cov = _walked(root, "demo2")
        # Act
        n = len(cov.inspected)
        # Assert
        assert n == 0

    def test_no_coverage_is_not_answerable(self):
        # Arrange — this predicate is what stops a clean verdict being
        # emitted for a run that inspected nothing.
        @click.group(hidden=True)
        def root():
            pass

        cov = _walked(root, "demo2")
        # Act
        answerable = cov.is_answerable()
        # Assert
        assert answerable is False

    def test_a_real_surface_IS_answerable(self):
        # Arrange — NEGATIVE CONTROL for the predicate above. If this also
        # returned False the refusal would fire on every package and the
        # gate would be useless in the opposite direction.
        cov = _walked(_tree_with_one_hidden())
        # Act
        answerable = cov.is_answerable()
        # Assert
        assert answerable is True


class TestAbsentCoverageIsLouderThanSuccess:
    def test_absent_coverage_says_it_is_not_reported(self):
        # Arrange — the whole defect was a clean verdict with no denominator
        # reading exactly like a verified one.
        # Act
        text = describe_or_unknown(None)
        # Assert
        assert "NOT REPORTED" in text

    def test_present_coverage_renders_the_figure(self):
        # Arrange
        cov = _walked(_tree_with_one_hidden())
        # Act
        text = describe_or_unknown(cov)
        # Assert
        assert "2 command(s) inspected" in text


class TestValidatorFailsWhereTheBugIs:
    def test_an_unknown_skip_reason_raises(self):
        # Arrange — validated at construction so a typo fails where it is
        # written, not as a plausible word three layers downstream.
        cov = SurfaceCoverage()
        # Act
        # Assert
        with pytest.raises(ValueError):
            cov.record_skipped("demo x", "not-a-real-reason")

    def test_a_command_cannot_be_both_inspected_and_skipped(self):
        # Arrange
        cov = SurfaceCoverage()
        cov.record_inspected("demo x")
        # Act
        # Assert
        with pytest.raises(ValueError):
            cov.record_skipped("demo x", HIDDEN)

    def test_skip_reasons_is_closed(self):
        # Arrange — an unused member of a set documented as closed is an
        # invitation to misuse it; PASS_THROUGH was removed when wiring
        # showed pass-throughs are inspected under §2, not skipped.
        # Act
        reasons = SKIP_REASONS
        # Assert
        assert reasons == frozenset({HIDDEN})


# EOF
