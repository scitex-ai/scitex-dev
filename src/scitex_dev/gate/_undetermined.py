#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/_undetermined.py
"""The gate's third verdict: the check RAN and could not tell.

WHY IT IS A SEPARATE MODULE. The two halves of this verdict were originally
written where they were needed — the constructor in ``_spec`` beside
``GateResult``, the finding-attachment in ``_run`` beside the runner — and
that is exactly how a concept becomes impossible to find. It is one idea:
*a check that could not observe its subject must refuse, and must say what
was unavailable.* The kind string, the message shape and the fix-hint are a
single contract, and splitting them across two modules means the next
person changing one will not see the other.

DIRECTION OF IMPORT: this module reads ``_spec`` and nothing reads it back.
``GateResult.cannot_determine`` stays on the dataclass because it only
constructs a ``GateResult``; putting it here would make the cycle.

THE DISTINCTION THIS PROTECTS, which is the whole reason the verdict exists:

    passed=False, undetermined=False   the SUBJECT failed
                                       -> go fix the thing being checked
    passed=False, undetermined=True    the CHECK could not observe it
                                       -> go fix what was unavailable
    check raised                       the CHECK is broken
                                       -> report it to the owning package
    passed=None (runner-set)           nobody ran it, on purpose
                                       -> disabled in config, or `requires`
                                          not importable. A decision.

Reporting any of these as any other sends a reader somewhere useless, and a
check that sends readers to the wrong place stops being read.

Prior art, in this same repository: the audit's §10 import-budget check
already refuses this way — "§10 import-budget SKIPPED — COULD NOT MEASURE
RELIABLY ... No verdict is claimed in either direction: this is neither a
pass nor a failure of the budget." The audit could say that. The gate could
not, until this.
"""

from __future__ import annotations

from ._spec import Finding

#: The finding kind. Deliberately distinct from ``check_crashed`` (a bug in
#: the check) and from whatever kinds a check emits for a real failure.
UNDETERMINED_KIND = "check_undetermined"

#: What the reader is told to do. It says NOT-A-FAILURE first, because the
#: instinct on seeing a red gate is to go and change the subject, and here
#: that is wasted work.
UNDETERMINED_FIX_HINT = (
    "This is NOT a failure of the thing being checked — the check could not "
    "observe it. Fix what was unavailable. If this expectation genuinely does "
    "not apply to this repo, DECLARE that by disabling the check in "
    ".scitex/dev/config.yaml rather than leaving it unverifiable."
)

__all__ = [
    "UNDETERMINED_FIX_HINT",
    "UNDETERMINED_KIND",
    "is_undetermined",
    "with_undetermined_finding",
]


def is_undetermined(result) -> bool:
    """True when `result` reports it could not tell.

    ``getattr`` rather than attribute access: a ``GateResult`` built by a
    leaf installed against an older scitex-dev has no such field, and a
    runner that raised on that would take out every check in the process
    for a change made here.
    """
    return bool(getattr(result, "undetermined", False))


def undetermined_reason(result) -> str:
    """The reason `result` gave, or the empty string. Never raises."""
    return str(getattr(result, "undetermined_reason", "") or "").strip()


def with_undetermined_finding(check, result) -> tuple[Finding, ...]:
    """Append the could-not-tell finding, preserving the check's own.

    Appended rather than substituted: whatever context the check managed to
    gather before giving up is usually the most useful thing on the page.
    """
    findings = tuple(result.findings)
    if not is_undetermined(result):
        return findings
    reason = undetermined_reason(result)
    return findings + (
        Finding(
            check_id=check.id,
            kind=UNDETERMINED_KIND,
            message=(
                "could not be determined: "
                + (reason or "no reason given by the check")
            ),
            severity="error",
            fix_hint=UNDETERMINED_FIX_HINT,
        ),
    )
