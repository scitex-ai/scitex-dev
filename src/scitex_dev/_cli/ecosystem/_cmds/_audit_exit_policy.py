#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What does each auditor actually exit non-zero ON?

The sub-auditors DO NOT SHARE AN EXIT POLICY, and the caller has been guessing.
That guess is the defect: a downgrade rule written over auditors whose exit
semantics differ silently will be right for some and wrong for others, and
nothing in the output says which.

MEASURED IN THE CODE, not taken from a docstring (constitution §1: read the
code, not the docs — the docstring happened to be right here, and I verified it
anyway because that is the only way to know):

    _project/_audit.py:239   exit_code = 1 if n_errors > 0 else 0   -> ERRORS_ONLY
    _django/_audit.py:433    exit_code = 1 if n_errors > 0 else 0   -> ERRORS_ONLY
    _skills/_audit.py:229    return 0 if not violations else 1      -> ANY_FINDING
    _api/_audit.py:216       return 0 if not violations else 1      -> ANY_FINDING

WHY IT MATTERS, with the case that proves it. scitex-agent-container's PR #1010
measured: ZERO errors, ZERO masked, 4 warning/info findings, 21 lines inspected
— and the build FAILED. Nothing to mask and nothing to downgrade, so no masking
predicate was even reached. A WARN-only run failed, because `audit-skills` and
`audit-python-apis` do not grade severity.

That single case also reconciles readings that looked contradictory: `audit-all
scitex-dev` exits 0 at 190 warnings / 0 errors, exits 0 at 5 warnings / 0
errors, and #1010 exits 1 at 4 warnings / 0 errors. All true. THE VARIABLE WAS
NEVER THE TIER — IT WAS THE EMITTER.

THE THIRD VALUE IS LOAD-BEARING HERE TOO
-----------------------------------------
Two auditors are deliberately absent from the table below: `audit-cli` and
`audit-mcp-tools`. I could not locate their exit expressions, so they have NO
DECLARED POLICY — and an undeclared policy is not a default, it is an unasked
question. :func:`policy_for` returns ``None`` for them, and a downgrade granted
on an unasked question is the same defect as one refused for no reason, wearing
the opposite sign.

Adding an auditor here requires READING ITS EXIT EXPRESSION. Guessing a policy
to make the table look complete would reintroduce exactly the defect this
module exists to remove.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class ExitPolicy(Enum):
    """What an auditor returns non-zero on."""

    #: Non-zero only when an ERROR-tier finding is present. Warnings are
    #: reported and cost nothing.
    ERRORS_ONLY = "non-zero-only-on-error-tier-findings"
    #: Non-zero on ANY finding, whatever its tier. These auditors do not grade
    #: severity at all, so a lone WARN fails the build.
    ANY_FINDING = "non-zero-on-any-finding-of-any-tier"
    #: NEVER non-zero. A reporting tool rather than a gate — it prints
    #: findings and returns 0 whatever it found. An auditor with this policy
    #: cannot appear in the failing set at all, so seeing one there is a
    #: contradiction rather than a case to adjudicate.
    WARN_ONLY = "always-zero-reports-but-never-fails"


#: auditor name -> the policy READ FROM ITS SOURCE. Absence is meaningful: it
#: means "not measured", never "assume the common case".
AUDITOR_EXIT_POLICY: Mapping[str, ExitPolicy] = {
    "audit-project": ExitPolicy.ERRORS_ONLY,
    "audit-django": ExitPolicy.ERRORS_ONLY,
    "audit-skills": ExitPolicy.ANY_FINDING,
    "audit-python-apis": ExitPolicy.ANY_FINDING,
    # _summary/__init__.py:302, its own words: "return exit code (always 0 --
    # warn-only)". Worth knowing on its own: a WARN_ONLY auditor explains the
    # measurement that confused me for hours -- `audit-all scitex-dev` exits 0
    # at 190 warnings because those warnings come from the auditor that never
    # fails, while #1010's 4 warnings came from ones that always do.
    "audit-cli": ExitPolicy.WARN_ONLY,
}


def policy_for(auditor: str) -> ExitPolicy | None:
    """Return ``auditor``'s declared exit policy, or ``None`` if undeclared.

    ``None`` is the third value and it does NOT mean ERRORS_ONLY. A caller
    that cannot learn an auditor's policy cannot ask it the right question,
    and must therefore refuse to downgrade it rather than assume.
    """
    return AUDITOR_EXIT_POLICY.get(auditor)


def is_downgradeable(auditor: str) -> bool:
    """True only when we KNOW what this auditor exits on.

    The conservative side of an unprovable case, and consistent with how the
    rest of this package treats unknowns: a run that could not be judged stays
    red and says so, rather than going green on a guess.
    """
    return policy_for(auditor) is not None


def failing_audit_is_explained(auditor: str, report) -> bool:
    """Is THIS failing auditor's exit fully accounted for by declared skips?

    Each auditor is asked the question ITS OWN policy makes meaningful, which
    is the whole point of the table above:

    * ``ERRORS_ONLY`` -- it exits on error-tier findings, so warnings could
      not have caused this exit. Ask only whether the ERROR-tier findings are
      accounted for: ``unmasked_error_count == 0``.
    * ``ANY_FINDING`` -- it does not grade severity, so ANY leftover finding
      could have caused the exit. Ask the strict question: ``fully_masked``.

    An UNDECLARED auditor returns False. Not "assume ERRORS_ONLY", not
    "assume the strict question" — we cannot ask the right question at all,
    and a downgrade granted on an unasked question is the same defect as one
    refused for no reason, wearing the opposite sign.

    ``report`` is that ONE auditor's :class:`~._audit_masking.MaskReport`.
    Passing the whole run's report here would reintroduce scitex-ai/
    scitex-dev#590, where a finding printed by an auditor that exited 0
    vetoed a downgrade it had no part in.
    """
    policy = policy_for(auditor)
    if policy is None:
        return False
    if policy is ExitPolicy.WARN_ONLY:
        # It declares it never exits non-zero, yet here it is in the failing
        # set. One of those is wrong, and neither is a case to adjudicate.
        # Refusing the downgrade keeps the contradiction VISIBLE instead of
        # resolving it in the direction that happens to be convenient.
        return False
    if policy is ExitPolicy.ERRORS_ONLY:
        # `fully_masked` would be too strict here: an undeclared WARNING
        # cannot have caused an ERRORS_ONLY auditor to exit non-zero, so
        # holding the package red for it is punishing a finding that is
        # provably not the reason.
        #
        # BUT `unmasked_error_count == 0` ALONE IS TOO LOOSE, and the existing
        # test suite caught me shipping exactly that. It is trivially true
        # when the auditor reported NOTHING AT ALL -- a crash, a launch
        # failure -- which would excuse the one case that most needs to stay
        # red. "A crash is not a deferral; nothing was declared, so nothing is
        # excused." So require something MASKED to have been found: the exit
        # must be explained by a declared rule, not merely unexplained by an
        # error. This is the same "at least one" guard `fully_masked` carries,
        # for the same reason.
        return report.unmasked_error_count == 0 and report.masked_count > 0
    # ANY_FINDING. This is the branch scitex-agent-container's #1010 proves
    # we need: 0 errors, 4 warnings, build FAILED. Anything less strict here
    # takes that run green while a sub-auditor is legitimately failing.
    return report.fully_masked


__all__ = [
    "AUDITOR_EXIT_POLICY",
    "ExitPolicy",
    "failing_audit_is_explained",
    "is_downgradeable",
    "policy_for",
]

# EOF
