#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Error hierarchy for :mod:`scitex_dev.status`.

Every error here carries an ACTIONABLE hint — the constitution's "an error
that only states what broke is half-written" rule. Each one names the
offending value AND the next step.

Nothing in this module is a warning. A :class:`~._status_code.StatusCode`
that degrades silently is worse than one that refuses: the malformed value
travels, and the layer that finally chokes on it is three boundaries away
from the context that would explain it.
"""

from __future__ import annotations

__all__ = [
    "CheckError",
    "InferredCauseError",
    "MissingProbeError",
    "StatusError",
    "UnknownCodeError",
    "UnknownKindError",
    "UnknownPolicyError",
    "UnknownVerdictError",
]


class StatusError(Exception):
    """Base class for every :mod:`scitex_dev.status` failure."""


class UnknownKindError(StatusError):
    """``kind`` is not one of the registered kinds.

    Refused rather than defaulted. A default kind would mean the tag no
    longer says which dictionary to open, and the whole design rests on
    that tag being trustworthy.

    Register a new kind in ``spec/kinds.yaml`` — which is a spec change, and
    should be, because every reader of the value has to learn it.
    """


class UnknownCodeError(StatusError):
    """``code`` is not valid within its declared ``kind``.

    Enumerated domains are checked, not just ranges: ``http 999`` passes a
    100-599 range test and is still a code nobody defined — a typo wearing a
    uniform. ``errno`` additionally requires the NAME, because errno NUMBERS
    are platform-specific and a number crossing a host boundary is a value
    that changes meaning in transit.
    """


class InferredCauseError(StatusError):
    """``message`` asserts a cause the sender did not observe (rule M1).

    Stating an OBSERVED cause is fine (``ENOENT: /etc/foo``). CONCLUDING an
    unobserved one is refused, because a hint that asserts a cause has
    stopped being a hint and become a verdict the reader cannot check.

    Measured 2026-08-11: a transport-failure message printed "THEREFORE the
    fault is specific to POST /agents" from two control probes that cannot
    see that route. A reader acted on it within two minutes and filed a P1
    against the wrong component. The route was fine — the client had stopped
    listening after 30 s while the server worked for 5 min 12 s.

    The fix is the shape from scitex-agent-container PR #956: say what was
    OBSERVED, what is RULED OUT, what is NOT ESTABLISHED, and what probe to
    run NEXT.
    """


class MissingProbeError(StatusError):
    """A "received, not finished" code carries no way to ask about it (rule M2).

    ``http 102`` and ``http 202`` mean the work is still going. Without a
    named probe the reader's only option is to wait and then guess, which is
    the 30 s / 5 min 12 s incident exactly.

    Name a probe in ``message``: a backtick-quoted command, a URL, or a path.
    """


class UnknownVerdictError(StatusError):
    """A verdict value is not one of the three in ``spec/verdicts.yaml``.

    Refused rather than defaulted, and refused rather than decayed. A reader
    that meets a verdict it does not implement must say so; quietly folding it
    into ``ok`` or ``not-ok`` is the exact collapse the three-valued verdict
    exists to prevent, performed by the code that was supposed to prevent it.
    """


class CheckError(StatusError):
    """A :class:`~._check.Check` is missing something its verdict requires.

    ``unknown`` without a reason is barely better than the boolean it
    replaced: the reader still has to guess, and now has a third word for
    guessing. ``not-ok`` without a hint is the constitution's half-written
    error. Both are refused at construction, where the context that would
    explain them still exists.
    """


class UnknownPolicyError(StatusError):
    """A rollup was asked for a policy that does not exist.

    What an unknown MEANS for an aggregate is the caller's decision — refuse,
    propagate, or tolerate — and there is no default, because a default policy
    is the same collapse as a boolean verdict, moved one level up and made
    invisible.
    """


# EOF
