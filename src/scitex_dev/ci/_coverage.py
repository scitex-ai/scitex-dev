#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Did the required checks actually RUN on this commit?

A green pull request means "no required check reported failure". It does NOT
mean "every required check reported". Those two are identical on screen and
opposite in meaning, and GitHub renders the second one exactly like the first:
a PR whose workflows never triggered shows no red, because there is nothing to
be red.

MEASURED 2026-08-15 on this repository. PR #591 was based on a TOPIC BRANCH,
and the workflows declare::

    on:
      pull_request:
        branches: [main, develop]

`branches:` filters the BASE, so a PR into a topic branch matches nothing and
no workflow runs. #591 sat for three days showing only its CLA check, read as
"green" by me each time I looked at it. Nothing anywhere said "0 of 4 required
checks ran" — the information was absent, not wrong, which is the harder kind
to notice.

WHAT THIS MODULE IS AND IS NOT
------------------------------
Pure decision logic over facts a caller supplies. It performs no network I/O,
so it is testable without a GitHub token and deterministic in CI. Fetching the
facts (`gh pr view`, `gh api .../check-runs`) belongs to the caller.

THE THIRD VALUE, AGAIN
----------------------
A caller that could not read the required-context list must not get a verdict.
Reporting COVERED would restore the silence this exists to break; reporting
UNCOVERED would cry wolf on every API hiccup and train the reader to skip it.
:class:`Coverage` therefore has three members, and UNKNOWN does not block.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Iterable, NamedTuple

#: The base branches the workflows' ``pull_request.branches:`` filter names. A
#: PR based anywhere else structurally cannot trigger them — no run is queued,
#: so there is not even a pending check to notice.
CI_BASE_BRANCHES: Final[frozenset[str]] = frozenset({"main", "develop"})


class Coverage(Enum):
    """Whether this commit's required checks demonstrably ran."""

    COVERED = "every-required-check-reported"
    UNCOVERED = "at-least-one-required-check-never-ran"
    UNKNOWN = "required-check-list-unavailable"


class CoverageVerdict(NamedTuple):
    """The answer for one PR head, with the evidence attached."""

    coverage: Coverage
    missing: tuple[str, ...] = ()
    #: Set when the BASE branch alone explains the absence. Distinguishing
    #: this from "a check was configured and did not run" matters, because
    #: the two have different fixes: retarget the PR, versus find out why a
    #: workflow failed to start.
    unreachable_base: str | None = None

    @property
    def blocks(self) -> bool:
        """UNKNOWN does not block — a broken instrument is not a defect."""
        return self.coverage is Coverage.UNCOVERED


def classify_pr_coverage(
    base_ref: str,
    required_contexts: Iterable[str] | None,
    ran_contexts: Iterable[str] | None,
) -> CoverageVerdict:
    """Decide whether ``base_ref``'s required checks ran on this head.

    ``required_contexts`` is the branch-protection required list for the BASE
    branch; ``ran_contexts`` is what actually reported on the head commit.
    Either being ``None`` — as opposed to empty — means the caller could not
    read it, and yields UNKNOWN rather than a guess. ``()`` is a real answer
    ("asked, and there are none") and is treated as one.
    """
    if required_contexts is None or ran_contexts is None:
        return CoverageVerdict(Coverage.UNKNOWN)

    required = tuple(dict.fromkeys(required_contexts))
    ran = set(ran_contexts)
    missing = tuple(c for c in required if c not in ran)

    # The base check comes AFTER the missing computation on purpose: when a
    # PR targets an unreachable base we still want to name WHICH checks are
    # absent, not just that the base is wrong. A caller retargeting the PR
    # should be able to see what they will gain.
    unreachable = base_ref if base_ref not in CI_BASE_BRANCHES else None

    if not missing:
        # A reachable base with nothing missing is covered. An UNREACHABLE
        # base with nothing missing is also covered — if no checks are
        # required, there is nothing for the base to have prevented, and
        # inventing a finding there would flag every draft PR in the fleet.
        return CoverageVerdict(Coverage.COVERED, unreachable_base=unreachable)
    return CoverageVerdict(Coverage.UNCOVERED, missing, unreachable)


def render(verdict: CoverageVerdict) -> str:
    """Render for a human, naming the fix rather than only the fault."""
    if verdict.coverage is Coverage.UNKNOWN:
        return (
            "COULD NOT BE JUDGED: the required-check list was unavailable, so "
            "this is not a clean result — re-run when the API is reachable."
        )
    if verdict.coverage is Coverage.COVERED:
        return "every required check reported on this commit"
    lines = [
        f"{len(verdict.missing)} required check(s) NEVER RAN on this commit: "
        + ", ".join(verdict.missing),
        "A PR is green when nothing required FAILED. That is not the same as "
        "every required check having reported, and GitHub renders the two "
        "identically.",
    ]
    if verdict.unreachable_base:
        lines.append(
            f"CAUSE: the base branch is {verdict.unreachable_base!r}, which "
            f"the workflows' `pull_request.branches:` filter does not name "
            f"({', '.join(sorted(CI_BASE_BRANCHES))}). No run was queued, so "
            "there is not even a pending check to notice. Retarget the PR, or "
            "add the base to the filter."
        )
    return "\n".join(lines)


# EOF
