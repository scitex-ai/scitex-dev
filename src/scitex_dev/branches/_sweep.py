#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE THREE DAYS RULE, as a decision function rather than a habit.

Operator, 2026-08-15, constitution §5 (verbatim)::

    drop branches other than main, develop, cla, and topic branches which are
    not edited in the last three days; three days rule must be set as a rule in
    constitution; we should forget any work which is not touched within the last
    three days

and, immediately after::

    THREE DAYS RULE is really important

The same section says how it must be enforced, and that instruction is why this
module exists at all::

    Automate it, do not remember it: a rule enforced by memory is enforced at
    exactly the wrong moment.

So the judgement lives HERE, as a pure function over facts, with the git and
GitHub plumbing kept outside it. A sweep whose reasoning is spread through a
shell pipeline can only be reviewed by running it, and running it is the
destructive part.

WHY THE OBVIOUS PREDICATE IS WRONG — measured, on this repo
------------------------------------------------------------
The natural test is ``git branch --no-merged develop``. It OVER-REPORTS under
squash merges: a squash-merged branch shares no commit with develop, so git
calls it unmerged forever. Measured 2026-08-15 on scitex-dev,
``fix/declare-psycopg-in-core`` and ``fix/postgres-reads-return-tuples`` had
landed as #601/#602 and still read as "not merged", as did
``fix/audit-assertion-names-rule-codes``, merged the same morning.

A sweep keyed on ancestry therefore either spares landed work forever, or — if
someone "fixes" it by trusting the flag the other way — deletes work that is
still open. **Ask GitHub whether a PR merged; do not ask git about ancestry.**

WHY AN OPEN PR IS NOT ABANDONMENT
----------------------------------
A branch with an open pull request is not untouched work; it is work someone
OWES. The rule's answer for it is to finish it or to say out loud that it is
dropped — never to have it vanish in a sweep. So :data:`Verdict.KEEP_OWED` is
its own outcome and not a flavour of "keep": the report has to be able to say
"you are carrying nine of these", which a silent keep cannot.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Final, NamedTuple

#: The only permanent exemptions, from the operator's sentence. Everything else
#: earns its life by being touched.
#:
#: A LITERAL SET, not a prefix or a pattern: `release/*`-style wildcards were
#: considered and rejected, because a pattern is how an exemption list quietly
#: grows to cover whatever someone names conveniently.
PROTECTED_BRANCHES: Final[frozenset[str]] = frozenset({"main", "develop", "cla"})

#: Three days, and the constitution is explicit that the discomfort is the point:
#: "A limit generous enough to never bite is the gate-that-cannot-fail in another
#: costume."
MAX_AGE_DAYS: Final[int] = 3


class Verdict(Enum):
    """What the sweep decided, and WHY — the why is the whole value.

    A bare drop/keep boolean would collapse four different reasons for keeping
    into one, and the report exists to distinguish them: `KEEP_OWED` is a
    to-do list, `KEEP_UNKNOWN` is a broken instrument, and confusing the two
    is how a stalled sweep looks like a clean one.
    """

    KEEP_PROTECTED = "protected"
    KEEP_IN_WORKTREE = "checked-out-in-a-worktree"
    KEEP_OWED = "open-pull-request"
    KEEP_FRESH = "touched-within-three-days"
    KEEP_UNKNOWN = "pr-state-unknown"
    DROP_MERGED = "pull-request-merged"
    DROP_STALE = "untouched-beyond-three-days"


class BranchFacts(NamedTuple):
    """What must be known about a branch before it can be judged.

    ``has_open_pr`` and ``pr_merged`` are ``bool | None`` on purpose, per §2's
    "every signal is three-valued": ``None`` means the GitHub lookup did not
    answer. Collapsing that into ``False`` would let an API hiccup delete a
    branch whose PR is open — the one outcome from which there is no cheap
    recovery.
    """

    name: str
    last_commit: date
    in_worktree: bool = False
    has_open_pr: bool | None = None
    pr_merged: bool | None = None


class Decision(NamedTuple):
    """One branch's fate, in a fixed shape (§2: answer in a declared shape)."""

    name: str
    verdict: Verdict
    age_days: int

    @property
    def drops(self) -> bool:
        return self.verdict in (Verdict.DROP_MERGED, Verdict.DROP_STALE)


def classify(
    facts: BranchFacts, *, today: date, max_age_days: int = MAX_AGE_DAYS
) -> Decision:
    """Decide one branch's fate. Pure — reads nothing, deletes nothing.

    ORDER IS THE CONTRACT, and each step is a veto over everything below it:

    1. protected — never dropped, whatever its age;
    2. checked out in a worktree — dropping it would strand a working tree;
    3. PR state UNKNOWN — refuse to judge rather than guess;
    4. PR merged — droppable at ANY age, because the work is safe on develop
       (this is the step that makes squash merges tractable);
    5. PR open — owed, not abandoned;
    6. fresh — touched inside the window;
    7. otherwise — stale, and it goes.

    Step 3 sits ABOVE step 4 deliberately. If the lookup failed we do not know
    whether the PR merged OR is open, and both of the branches below it read
    that same missing answer.
    """
    age = (today - facts.last_commit).days
    if facts.name in PROTECTED_BRANCHES:
        return Decision(facts.name, Verdict.KEEP_PROTECTED, age)
    if facts.in_worktree:
        return Decision(facts.name, Verdict.KEEP_IN_WORKTREE, age)
    if facts.has_open_pr is None or facts.pr_merged is None:
        return Decision(facts.name, Verdict.KEEP_UNKNOWN, age)
    if facts.pr_merged:
        return Decision(facts.name, Verdict.DROP_MERGED, age)
    if facts.has_open_pr:
        return Decision(facts.name, Verdict.KEEP_OWED, age)
    if age <= max_age_days:
        return Decision(facts.name, Verdict.KEEP_FRESH, age)
    return Decision(facts.name, Verdict.DROP_STALE, age)


class SweepPlan(NamedTuple):
    """The dry-run, which §2 requires before any bulk operation acts.

    Carries the AFFECTED SET, not a count someone has to trust: "The dry-run
    must print the counts and the affected set, not a summary you trust."
    """

    decisions: tuple[Decision, ...]

    def by(self, verdict: Verdict) -> tuple[Decision, ...]:
        return tuple(d for d in self.decisions if d.verdict is verdict)

    @property
    def drops(self) -> tuple[Decision, ...]:
        return tuple(d for d in self.decisions if d.drops)

    @property
    def owed(self) -> tuple[Decision, ...]:
        """Branches with open PRs — a to-do list the sweep must SURFACE.

        The rule's answer for these is to finish them or drop them out loud.
        Printing them is how "I am carrying nine open PRs" stops being
        something you discover by accident.
        """
        return self.by(Verdict.KEEP_OWED)

    @property
    def unjudged(self) -> tuple[Decision, ...]:
        """Branches whose PR state could not be read.

        NOT an empty category to ignore: a sweep that could not reach GitHub
        produces an all-`KEEP_UNKNOWN` plan, which must read as "the instrument
        failed", never as "nothing to do".
        """
        return self.by(Verdict.KEEP_UNKNOWN)


def plan_sweep(
    facts: list[BranchFacts], *, today: date, max_age_days: int = MAX_AGE_DAYS
) -> SweepPlan:
    """Classify every branch, in a stable order, deleting nothing."""
    return SweepPlan(
        tuple(
            classify(f, today=today, max_age_days=max_age_days)
            for f in sorted(facts, key=lambda f: f.name)
        )
    )


def render_plan(plan: SweepPlan) -> str:
    """Render the dry-run for a human to read BEFORE anything is deleted."""
    lines: list[str] = []
    for verdict in Verdict:
        group = plan.by(verdict)
        if not group:
            continue
        lines.append(f"{verdict.value}: {len(group)}")
        lines.extend(f"    {d.name}  ({d.age_days}d)" for d in group)
    lines.append(f"TOTAL {len(plan.decisions)}, dropping {len(plan.drops)}")
    if plan.unjudged:
        lines.append(
            f"WARNING: {len(plan.unjudged)} branch(es) could not be judged — "
            "the PR lookup did not answer. They are KEPT. Re-run once GitHub "
            "is reachable rather than treating this as a clean sweep."
        )
    return "\n".join(lines)


# EOF
