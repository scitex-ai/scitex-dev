#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`0 unmasked error(s)` with exit=1 must not name a single culprit.

An earlier version of this note read:

    "some sub-auditors exit NON-ZERO on WARN-tier findings, so a
     `summary: ... 0 unmasked error(s)` line can legitimately accompany
     exit=1."

That offers ONE explanation for a shape with at least two causes, and it
offers it as though it were the diagnosis.

MEASURED 2026-08-18: sac hit that exact shape locally, read this note,
and concluded warn-tier findings were gating their build. They were not.
Their exit came from `CLI conventions: not-auditable: unknown` — an
ERROR-tier finding that is not counted as unmasked, appearing only
locally because audit-cli needs the distribution installed to introspect
it.

They then proposed relaxing the gate for 83 packages. They declined to
do it unilaterally, which is the only reason it was measured first and
found unnecessary. The note nearly cost the fleet its audit gate.
"""

from __future__ import annotations

from scitex_dev.testing._audit_outcome import violations_message

_AN_ERROR = "ERRO:   [E] [PS-231 §1 reimplements-org-workflow] a.yml"


def _note() -> str:
    return violations_message("sac", "cmd", 1, [_AN_ERROR], "")


def test_the_note_offers_more_than_one_cause() -> None:
    """One named cause reads as the diagnosis, whatever the hedging."""
    # Arrange
    message = _note()
    # Act
    enumerates = "(a)" in message and "(b)" in message
    # Assert
    assert enumerates


def test_it_names_the_not_auditable_cause_specifically() -> None:
    """The one that actually bit sac, and the one nothing else records."""
    # Arrange
    message = _note()
    # Act
    names_it = "not-auditable" in message
    # Assert
    assert names_it


def test_it_says_the_message_cannot_tell_them_apart() -> None:
    """The honest claim. Anything stronger invites the same wrong read."""
    # Arrange
    message = _note()
    # Act
    disclaims = "cannot tell them apart" in message
    # Assert
    assert disclaims


def test_it_tells_the_reader_not_to_trust_the_note_itself() -> None:
    """A note that survived being wrong should say so out loud.

    "READ THE FINDINGS ABOVE, NOT THE COUNT, AND NOT THIS NOTE" — the
    last clause exists because this text has already misled a reader
    once.
    """
    # Arrange
    message = _note()
    # Act
    self_deprecating = "NOT THIS NOTE" in message
    # Assert
    assert self_deprecating


# EOF
