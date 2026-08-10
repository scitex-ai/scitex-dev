#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A domain exit code must not be impersonable by a framework exit code.

Measured 2026-08-09, by walking into it on the first real merge the gate
ever guarded. ``EXIT_NOT_READY`` was 2. The venv held a scitex-dev older
than the ``ci verify`` subcommand, so Click answered

    Error: No such command 'verify'.
    exit 2

and the gating hook read that as the DOMAIN answer, reporting "the pull
request is NOT ready to merge" about a pull request green on 7/7 checks.

The constitution forbids this verbatim (§2): "Never overload a small exit
code with a domain meaning: 1 and 2 already mean 'generic failure' and
'usage error' in every CLI framework, so a missing or renamed verb will
impersonate your success value."

The rule existed, was specific, and was walked past by someone who had read
it — inside the change that fixed two sibling instances of the same
UNKNOWN-collapsed-into-a-pole defect. Hence a check that RUNS.

The enums below are REAL enums, not patched globals. A guard verified by
rewriting the thing it guards is not verified.
"""

from __future__ import annotations

from enum import IntEnum

import pytest

from scitex_dev.ci._exit_codes import (
    EXIT_NOT_READY,
    EXIT_READY,
    EXIT_UNKNOWN,
    EXIT_USAGE,
    FRAMEWORK_RESERVED_EXIT_CODES,
    ExitCode,
    assert_no_domain_code_is_framework_reserved,
)


class ShippedBug(IntEnum):
    """The exact enum that shipped in 0.43.0 — NOT_READY parked on Click's 2."""

    READY = 0
    NOT_READY = 2
    CANNOT_DETERMINE = 3


class GenericFailureCollision(IntEnum):
    """The other half of the reserved range."""

    READY = 0
    NOT_READY = 1


class Safe(IntEnum):
    """What ships now."""

    READY = 0
    NOT_READY = 10
    CANNOT_DETERMINE = 11


def rejection_message(codes) -> str:
    """The guard's complaint, as text. Empty when it did not complain.

    A helper rather than a second assertion inside each test: asserting on
    the message AND on the raise would mean the message check is silently
    skipped whenever the raise check fails.
    """
    try:
        assert_no_domain_code_is_framework_reserved(codes)
    except RuntimeError as exc:
        return str(exc)
    return ""


class TestTheGuardFiresOnTheBugThatShipped:
    """A check that cannot fail is decoration. Prove this one can."""

    def test_the_shipped_enum_is_rejected(self):
        # Arrange
        codes = ShippedBug
        # Act / raises is the assertion
        with pytest.raises(RuntimeError):
            # Assert
            assert_no_domain_code_is_framework_reserved(codes)

    def test_the_rejection_names_the_offending_member(self):
        # Arrange
        codes = ShippedBug
        # Act
        message = rejection_message(codes)
        # Assert
        assert "NOT_READY" in message

    def test_the_rejection_explains_why_two_is_taken(self):
        # Arrange
        codes = ShippedBug
        # Act
        message = rejection_message(codes)
        # Assert
        assert "usage error" in message

    def test_a_collision_with_generic_failure_is_also_rejected(self):
        # Arrange
        codes = GenericFailureCollision
        # Act / raises is the assertion
        with pytest.raises(RuntimeError):
            # Assert
            assert_no_domain_code_is_framework_reserved(codes)


class TestTheGuardAcceptsWhatShipsNow:
    def test_the_safe_enum_passes(self):
        # Arrange
        codes = Safe
        # Act
        result = assert_no_domain_code_is_framework_reserved(codes)
        # Assert
        assert result is None

    def test_the_real_shipped_enum_passes(self):
        # Arrange
        codes = ExitCode
        # Act
        result = assert_no_domain_code_is_framework_reserved(codes)
        # Assert
        assert result is None


class TestTheShippedVocabulary:
    def test_ready_is_zero_because_success_is_universally_zero(self):
        # Arrange
        member = ExitCode.READY
        # Act
        value = int(member)
        # Assert
        assert value == 0

    def test_not_ready_is_outside_the_reserved_range(self):
        # Arrange
        member = ExitCode.NOT_READY
        # Act
        reserved = member.value in FRAMEWORK_RESERVED_EXIT_CODES
        # Assert
        assert not reserved

    def test_cannot_determine_is_outside_the_reserved_range(self):
        # Arrange
        member = ExitCode.CANNOT_DETERMINE
        # Act
        reserved = member.value in FRAMEWORK_RESERVED_EXIT_CODES
        # Assert
        assert not reserved

    def test_not_ready_and_cannot_determine_stay_distinct(self):
        """Collapsing them is the defect family this gate exists for."""
        # Arrange
        pair = (ExitCode.NOT_READY, ExitCode.CANNOT_DETERMINE)
        # Act
        same = pair[0] == pair[1]
        # Assert
        assert not same


class TestTheAliasesStillWork:
    """IntEnum members ARE ints, so callers keep working; numbers changed."""

    def test_exit_ready_is_still_zero(self):
        # Arrange
        alias = EXIT_READY
        # Act
        value = int(alias)
        # Assert
        assert value == 0

    def test_exit_not_ready_moved_off_the_reserved_range(self):
        # Arrange
        alias = EXIT_NOT_READY
        # Act
        reserved = alias in FRAMEWORK_RESERVED_EXIT_CODES
        # Assert
        assert not reserved

    def test_exit_unknown_moved_off_the_reserved_range(self):
        # Arrange
        alias = EXIT_UNKNOWN
        # Act
        reserved = alias in FRAMEWORK_RESERVED_EXIT_CODES
        # Assert
        assert not reserved

    def test_exit_usage_is_two_because_that_is_clicks_number(self):
        """It was declared as 1, which was wrong — and believing we owned a
        number we had mislabelled is how 2 came to look free."""
        # Arrange
        alias = EXIT_USAGE
        # Act
        value = int(alias)
        # Assert
        assert value == 2


# EOF
