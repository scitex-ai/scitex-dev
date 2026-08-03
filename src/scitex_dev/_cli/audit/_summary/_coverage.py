#!/usr/bin/env python3
"""The DENOMINATOR behind a CLI-convention verdict.

``SUCC: <pkg>: no CLI convention violations`` carried no denominator, so it
read identically whether the walker inspected forty commands or zero. That
is the defect this module exists to remove: a verdict without a denominator
cannot be distinguished from a run that never happened, and the empty case
renders as the CLEAN case.

Measured 2026-07-29 on this repo's own audit output, which is what made the
gap concrete: the summary printed ``374 line(s) inspected, 366 UNREADABLE``
next to per-package lines that claimed cleanliness with no count at all.
Two different reporters, one missing number.

WHY A SET AND NOT AN INT
------------------------
An int can only be trusted if every increment is correct, and it cannot be
audited after the fact. A set of command paths can: the caller can print
it, diff two runs, and answer "which command was not inspected?" — the
question an operator actually asks when a count looks wrong. It also makes
double-counting structurally impossible rather than merely unlikely.

WHY SKIPS ARE COUNTED, NOT DROPPED
----------------------------------
The walker deliberately does not inspect two kinds of command: ``hidden``
ones (deprecation redirects kept for back-compat) and ``pass-through``
entry points (help forwarded verbatim from an upstream tool). Both are
legitimate. Neither is *inspected*, so folding them into the inspected
count would report coverage the run does not have — the same unearned-green
shape as counting a skipped CI leg as passed.

So a skip is a THIRD value, kept with its reason:

    inspected   the rules ran against this command
    skipped     deliberately not inspected, reason recorded
    (absent)    nobody looked, and nobody said so -> see `describe`

THE ZERO CASE IS A REFUSAL, NOT A PASS
--------------------------------------
``inspected`` empty means the walker produced no coverage at all. That is
not a clean CLI; it is an unanswered question, and the caller must refuse
rather than emit success. :meth:`SurfaceCoverage.is_answerable` is the
predicate for that decision, kept here so every caller refuses on the same
condition instead of each re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "HIDDEN",
    "SKIP_REASONS",
    "SurfaceCoverage",
    "describe_or_unknown",
]

#: A command marked ``hidden=True`` — not part of the public CLI surface.
#: The ONLY way a command is reached and not inspected at all.
HIDDEN = "hidden"

#: The CLOSED set of reasons a command may be skipped. Closed on purpose:
#: an unrecognised reason is a caller bug, and letting it through would
#: reintroduce an uncounted third state under a new name.
#:
#: Deliberately ONE member. An earlier draft of this module also carried
#: ``PASS_THROUGH``, on the assumption that pass-through entry points are
#: skipped. Wiring the walker disproved it: §2 (universal flags) runs on
#: EVERY node including pass-throughs, and the pass-through branch exempts
#: only §1 / §1d / §4. So a pass-through is INSPECTED under a narrower rule
#: set — not skipped — and recording it as skipped would have understated
#: real coverage. The member was removed rather than left unused, because an
#: unused member of a set documented as closed is an invitation to misuse it.
SKIP_REASONS = frozenset({HIDDEN})


@dataclass
class SurfaceCoverage:
    """What the CLI walker actually looked at, accumulated in place.

    Mutable and appended to as the walk proceeds, mirroring the auditor's
    existing ``out: list`` convention so the two accumulators are threaded
    the same way and neither can be forgotten independently of the other.
    """

    inspected: set[str] = field(default_factory=set)
    skipped: dict[str, str] = field(default_factory=dict)

    def record_inspected(self, command: str) -> None:
        """Mark ``command`` as having had the rules run against it."""
        if command in self.skipped:
            raise ValueError(
                f"{command!r} was already recorded as skipped "
                f"({self.skipped[command]!r}) — a command is inspected or "
                "skipped, never both; this is a walker bug, not a data issue"
            )
        self.inspected.add(command)

    def record_skipped(self, command: str, reason: str) -> None:
        """Mark ``command`` as deliberately not inspected, with its reason.

        The reason is validated against :data:`SKIP_REASONS` here — at the
        point of construction — so a typo fails where it is written rather
        than rendering as a plausible word three layers downstream.
        """
        if reason not in SKIP_REASONS:
            raise ValueError(
                f"unknown skip reason {reason!r} — expected one of "
                f"{sorted(SKIP_REASONS)}"
            )
        if command in self.inspected:
            raise ValueError(
                f"{command!r} was already recorded as inspected — a command "
                "is inspected or skipped, never both; this is a walker bug"
            )
        self.skipped[command] = reason

    @property
    def total(self) -> int:
        """Every command the walker reached, inspected or not."""
        return len(self.inspected) + len(self.skipped)

    def is_answerable(self) -> bool:
        """False when no command was inspected, so no verdict is licensed.

        Kept as a named predicate rather than an inline ``if not
        coverage.inspected`` at each call site: every caller must refuse on
        the SAME condition, and a predicate is greppable where a scattered
        truthiness test is not.
        """
        return bool(self.inspected)

    def describe(self) -> str:
        """The denominator as a clause to append to a verdict line.

        ``None`` coverage is handled by :func:`describe_or_unknown` rather
        than here, because a method cannot be called on the absent case —
        and the absent case is exactly the one that must not render as
        silence.
        """
        clause = f"{len(self.inspected)} command(s) inspected"
        if not self.skipped:
            return clause
        by_reason: dict[str, int] = {}
        for reason in self.skipped.values():
            by_reason[reason] = by_reason.get(reason, 0) + 1
        detail = ", ".join(f"{n} {r}" for r, n in sorted(by_reason.items()))
        return f"{clause}, {len(self.skipped)} skipped ({detail})"


def describe_or_unknown(coverage: SurfaceCoverage | None) -> str:
    """Render coverage, naming the absent case instead of hiding it.

    A caller that has no coverage object gets a clause saying so. That is
    deliberately louder than the old behaviour, which printed a clean
    verdict and let the reader assume a denominator existed.
    """
    if coverage is None:
        return "coverage NOT REPORTED — this verdict has no denominator"
    return coverage.describe()
