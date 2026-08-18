#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`--new-only` is forbidden fleet-wide, and this module says why.

Operator ruling, 2026-08-18, unprompted and immediately after an agent
reported using it:

    「--new-only は禁止です！！！」
    「いかなるパッケージも、です。」

WHAT THE FLAG DID
-----------------
It capped PRE-EXISTING findings to warning, so only newly-introduced
ones could fail a build. That sounds like a reasonable migration aid and
it is how the flag was justified when it shipped.

WHY IT IS BANNED RATHER THAN DISCOURAGED
----------------------------------------
The damage is not that debt survives — debt is visible and someone can
decide about it. It is that a package STOPS HONOURING A SHARED RULE
WITHOUT ANYONE DECIDING TO. The gate keeps reporting green, against a
smaller rule set than the one it claims to enforce, and nothing marks
the moment it stopped. A reader of that green cannot tell it apart from
a green earned against the full set.

That is the same shape as every defect this fleet chased through
2026-08-18: an unknown — here, "was this rule even applied?" — rendered
as a confident answer.

WHY THE FLAG STILL EXISTS INSTEAD OF BEING DELETED
--------------------------------------------------
Deleting it yields ``no such option: --new-only``, which is an error
that names a TYPO rather than a ruling. Every caller carrying it in a
script would go looking for the correct spelling of a flag that was
removed on purpose. Refusing WITH THE REASON teaches the rule instead;
the flag's own ``--help`` now leads with FORBIDDEN so a reader learns it
before they try it.

THE SUPPORTED ALTERNATIVE IS NAMED ON PURPOSE
---------------------------------------------
A refusal that offers nothing invites the next move, which is to disable
the gate entirely. So the message points at a reasoned, DATED
``audit.exemptions`` entry: an exemption names ONE path and says why,
where ``--new-only`` excused everything that already existed, silently
and permanently.
"""

from __future__ import annotations

#: The refusal text. One constant so the CLI, the tests, and any future
#: cross-package rule cannot drift about what the ruling was.
FORBIDDEN_NEW_ONLY = (
    "--new-only is FORBIDDEN. Operator ruling, 2026-08-18: "
    "「--new-only は禁止です！！！」「いかなるパッケージも、です。」\n"
    "\n"
    "What it did: capped PRE-EXISTING findings to warning so they never "
    "blocked a build. What that means in practice: a package quietly "
    "stops honouring a rule the whole fleet agreed to, and nothing "
    "reports the moment it stopped — the gate still reports green, "
    "against a smaller set of rules than the one it claims to enforce.\n"
    "\n"
    "Run without it and fix, or exempt what is genuinely exceptional "
    "with a reasoned, DATED entry under `audit.exemptions` — an "
    "exemption names one path and says why; --new-only excused "
    "everything that already existed, silently and forever."
)

#: Spellings a caller might reach for, so a cross-package scan has one
#: place to read rather than each auditor inventing its own list.
FORBIDDEN_SPELLINGS: tuple[str, ...] = ("--new-only", "new_only=True")


def refuse_if_requested(new_only: bool) -> None:
    """Raise if ``--new-only`` was passed. No-op otherwise.

    Takes the FLAG rather than reading argv so the guard cannot fire on
    an ordinary run — a refusal that triggered unconditionally would look
    identical to a working ban while breaking everything.
    """
    if new_only:
        raise ValueError(FORBIDDEN_NEW_ONLY)


__all__ = [
    "FORBIDDEN_NEW_ONLY",
    "FORBIDDEN_SPELLINGS",
    "refuse_if_requested",
]

# EOF
