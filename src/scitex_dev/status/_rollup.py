#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N checks into one verdict — and the CALLER says what unknown means.

    report = rollup("scitex-cards", checks, unknown_policy=UnknownPolicy.TOLERATE)
    report = rollup("relocation", checks, unknown_policy=UnknownPolicy.REFUSE)

A KNOWN FAILURE ALWAYS WINS
---------------------------
Under every policy: if any check is ``not-ok``, the rollup is ``not-ok``. A
definite problem is not made less definite by an unknown standing next to it.

WHAT AN UNKNOWN MEANS IS NOT THE TYPE'S DECISION
------------------------------------------------
It depends on what the aggregate is FOR, and the two answers are opposite:

* Relocation must **refuse** — never move an agent onto a host you could not
  inspect.
* A dashboard tile may **tolerate** — the question there is "may I proceed?",
  not "is everything known?".

Baking either into the type makes the other one wrong, so the policy is a
REQUIRED keyword argument with no default. A default policy is the same
collapse a boolean verdict is, moved one level up and made invisible — and
harder to find, because nobody reads the aggregation function.

The naive aggregate — ``ok = not any(check failed)`` — is wrong in both
directions over a set containing unknowns. It answers "fine" when the truth is
"I could not look", and it offers no way to answer "do not proceed" when the
looking is what failed.

AN UNKNOWN IS NEVER SILENT
--------------------------
Whatever the policy, the summary NAMES every unknown check. A tolerated
unknown is still an unknown; an aggregate that answers "ok" without saying
what it could not see has lied by omission. There is exactly one summary
implementation and no way to supply your own, because that rule is the one a
caller in a hurry would drop.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Iterable

from ._check import Check
from ._errors import CheckError, UnknownPolicyError
from ._verdict import Verdict

__all__ = ["Report", "UnknownPolicy", "rollup"]


class UnknownPolicy(enum.Enum):
    """What an ``unknown`` check means for the aggregate. Stated, never assumed."""

    #: An unknown BLOCKS: the rollup is ``not-ok``. For decisions that take an
    #: irreversible action on the strength of the checks — relocating an agent,
    #: promoting a release, deleting a source. Never act on a host you could
    #: not inspect.
    REFUSE = "refuse"

    #: An unknown is CONTAGIOUS: the rollup is ``unknown``. The honest choice
    #: when the aggregate is itself a report something else will decide from —
    #: "I cannot tell you the whole is healthy" is what actually happened, and
    #: flattening it here discards the distinction one layer before the reader
    #: who needs it.
    PROPAGATE = "propagate"

    #: An unknown does NOT block: the rollup is ``ok``, and names the unknowns.
    #: For "may I proceed?" rather than "is everything known?" — a dashboard
    #: tile, an advisory banner. It is not licence to hide them.
    TOLERATE = "tolerate"

    @classmethod
    def from_wire(cls, value: object) -> "UnknownPolicy":
        """Parse the spec's string form, or raise."""
        for member in cls:
            if member.value == value:
                return member
        raise UnknownPolicyError(
            f"unknown rollup policy {value!r}. The choices are "
            f"{[m.value for m in cls]}, and one of them must be stated: what "
            f"an unknown means for an aggregate depends on what the aggregate "
            f"is for, so there is no default that is right twice."
        )


@dataclass(frozen=True, slots=True)
class Report:
    """A package's checks, rolled up under a stated policy.

    Build it with :func:`rollup`; the verdict and the summary are computed
    there and nowhere else, so neither can be asserted independently of the
    checks they describe.
    """

    package: str
    verdict: Verdict
    checks: "tuple[Check, ...]"
    unknown_policy: UnknownPolicy
    summary: str

    @property
    def failing(self) -> "tuple[str, ...]":
        """Names of the checks that answered ``not-ok``."""
        return tuple(c.name for c in self.checks if c.verdict is Verdict.NOT_OK)

    @property
    def unknown(self) -> "tuple[str, ...]":
        """Names of the checks that could not find out."""
        return tuple(c.name for c in self.checks if c.verdict is Verdict.UNKNOWN)

    def to_dict(self) -> "dict[str, Any]":
        """The wire form — the four keys the fleet's doctors already publish.

        ``unknown_policy`` is deliberately NOT serialised. The four-key record
        is what existing readers parse, and a fifth key would make every one of
        them wrong about a shape that was not the problem. The policy is a
        property of the CALLER's decision rather than of the observation, and
        it is readable on this object by anyone holding it; the unknowns
        themselves are named in ``summary``, which is what a JSON reader
        actually needs in order not to be misled.
        """
        return {
            "package": self.package,
            "ok": self.verdict.ok,
            "checks": [check.to_dict() for check in self.checks],
            "summary": self.summary,
        }


def _summarise(checks: "tuple[Check, ...]") -> str:
    """Count the checks and NAME the exceptional ones.

    The format is the one ``scitex-cards``' doctor already publishes, so the
    package that documented this shape keeps its output byte-for-byte after
    adopting the primitive. Naming the unknowns is not cosmetic — it is the
    part of the "never silent" rule a JSON reader can actually see.
    """
    failing = [c.name for c in checks if c.verdict is Verdict.NOT_OK]
    unknown = [c.name for c in checks if c.verdict is Verdict.UNKNOWN]
    passed = sum(1 for c in checks if c.verdict is Verdict.OK)
    summary = f"{passed}/{len(checks)} checks passed"
    if failing:
        summary += "; failing: " + ", ".join(failing)
    if unknown:
        summary += "; unknown: " + ", ".join(unknown)
    return summary


def rollup(
    package: str,
    checks: "Iterable[Check]",
    *,
    unknown_policy: UnknownPolicy,
) -> Report:
    """Roll ``checks`` up into one :class:`Report` under a STATED policy.

    ``unknown_policy`` is keyword-only and has no default, so the question
    "what does an unknown mean here?" is answered at every call site rather
    than once, invisibly, by whoever wrote this function.

    Precedence: a ``not-ok`` anywhere wins under every policy. Only when there
    is no known failure does the policy decide, and only then does it matter.

    An EMPTY check set takes the SAME path an unknown does. A doctor that ran
    nothing has established nothing, so REFUSE blocks on it, PROPAGATE reports
    ``unknown``, and TOLERATE answers ``ok`` — which is what "nothing blocks
    me" means when there was nothing to block. Treating it as a fourth case
    would leave REFUSE able to return a verdict its own contract says it never
    returns.
    """
    if not isinstance(unknown_policy, UnknownPolicy):
        raise UnknownPolicyError(
            f"`unknown_policy` must be an UnknownPolicy member; got "
            f"{unknown_policy!r} ({type(unknown_policy).__name__}). State it: "
            f"REFUSE if acting on an uninspected thing would be unsafe, "
            f"PROPAGATE if this rollup is itself a report, TOLERATE if the "
            f"question is 'may I proceed?'. There is no default because no "
            f"default is right twice."
        )

    frozen = tuple(checks)
    for position, check in enumerate(frozen):
        if not isinstance(check, Check):
            raise CheckError(
                f"checks[{position}] is {check!r} "
                f"({type(check).__name__}), not a Check. Build it with "
                f"Check.ok / Check.not_ok / Check.unknown, or parse a wire "
                f"record with Check.from_dict — a bare dict has not been "
                f"validated, and the rules it skips are the ones that make an "
                f"unknown worth more than a boolean."
            )

    nothing_established = not frozen or any(
        check.verdict is Verdict.UNKNOWN for check in frozen
    )
    if any(check.verdict is Verdict.NOT_OK for check in frozen):
        verdict = Verdict.NOT_OK
    elif nothing_established:
        verdict = {
            UnknownPolicy.REFUSE: Verdict.NOT_OK,
            UnknownPolicy.PROPAGATE: Verdict.UNKNOWN,
            UnknownPolicy.TOLERATE: Verdict.OK,
        }[unknown_policy]
    else:
        verdict = Verdict.OK

    return Report(
        package=package,
        verdict=verdict,
        checks=frozen,
        unknown_policy=unknown_policy,
        summary=_summarise(frozen),
    )


# EOF
