#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turning git and GitHub output into the facts :mod:`._sweep` judges.

Split from the judgement on purpose: :func:`~._sweep.classify` decides, this
module only reports. Everything here is a PURE PARSER over text a command
printed, so the whole fact-gathering path is testable without a repository and
without the network — which matters because the consumer of these facts deletes
branches.

THE DISTINCTION THIS MODULE EXISTS TO PRESERVE
-----------------------------------------------
``gh pr list`` printing ``[]`` and ``gh pr list`` FAILING are different answers::

    []        "I looked. This branch has no open PR."     -> has_open_pr=False
    <error>   "I could not look."                          -> has_open_pr=None

Both produce an empty mapping if you parse them the same way, and the empty
mapping reads as "no PRs anywhere" — which, fed to the sweep, licenses deleting
every branch in the repository.

This is not hypothetical. The same shape was measured on 2026-08-15 while
counting `CI_RUNS_ON` variables: ``gh api`` printed its 404 body to STDOUT, so
an emptiness test on the output never fired and 76 repositories were recorded as
"variable set" when 8 had none. There the cost was a wrong census; here it would
be deleted work.

So :func:`parse_pr_states` returns ``None`` — not ``{}`` — when it is handed a
non-answer, and :func:`build_facts` turns that into ``KEEP_UNKNOWN`` for every
branch rather than into a licence to drop them.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Final, NamedTuple

from ._sweep import BranchFacts

#: Prints one ``<iso-date> <branch>`` line per local branch::
#:
#:     git for-each-ref --format='%(committerdate:short) %(refname:short)' refs/heads/
#:
#: `committerdate`, not `authordate`: a rebased or cherry-picked commit keeps its
#: original AUTHOR date, so authordate would report work touched this morning as
#: months old and the sweep would delete it.
BRANCH_AGE_FORMAT: Final[str] = "%(committerdate:short) %(refname:short)"


class PrState(NamedTuple):
    """What GitHub said about one branch's pull requests.

    Both fields ``None`` means NOT ASKED or NOT ANSWERED — never "no PR".
    """

    has_open_pr: bool | None = None
    pr_merged: bool | None = None


#: The answer for a branch when the lookup did not happen or did not parse.
UNKNOWN_PR: Final[PrState] = PrState(None, None)


def parse_branch_ages(text: str) -> dict[str, date]:
    """Parse ``git for-each-ref`` output into ``{branch: last commit date}``.

    Malformed lines are SKIPPED rather than defaulted. A branch that does not
    appear here is simply not swept; a branch given a wrong date would be
    swept on that wrong date, and one of those failures is recoverable.
    """
    ages: dict[str, date] = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        stamp, name = parts[0].strip(), parts[1].strip()
        if not name:
            continue
        try:
            ages[name] = date.fromisoformat(stamp)
        except ValueError:
            continue
    return ages


def parse_worktree_branches(porcelain: str) -> frozenset[str]:
    """Parse ``git worktree list --porcelain`` into the set of checked-out branches.

    A DETACHED worktree contributes nothing, which is correct: it pins a commit,
    not a branch, so no branch is made undeletable by it.
    """
    prefix = "branch refs/heads/"
    return frozenset(
        line[len(prefix) :].strip()
        for line in porcelain.splitlines()
        if line.startswith(prefix) and line[len(prefix) :].strip()
    )


def _head_refs(payload: str) -> set[str] | None:
    """Extract ``headRefName`` values from a ``gh pr list --json`` payload.

    Returns ``None`` — meaning "no answer" — for anything that is not a JSON
    array. `gh` writes diagnostics to stdout often enough that "it printed
    something" is not evidence it answered the question asked.
    """
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list):
        return None
    refs: set[str] = set()
    for row in parsed:
        if not isinstance(row, dict):
            return None
        name = row.get("headRefName")
        if not isinstance(name, str) or not name:
            return None
        refs.add(name)
    return refs


def parse_pr_states(open_payload: str, merged_payload: str) -> dict[str, PrState] | None:
    """Combine the open-PR and merged-PR listings into per-branch state.

    Returns ``None`` if EITHER listing failed to parse. Not a partial mapping:
    a branch absent from a half-read listing is indistinguishable from a branch
    with no PR, and the sweep would read that absence as permission to drop.

    Expected input, both from ``gh``::

        gh pr list --state open   --json headRefName
        gh pr list --state merged --json headRefName

    An empty array from both is a real, usable answer — every branch then has
    ``has_open_pr=False, pr_merged=False`` and is judged on age alone.
    """
    open_refs = _head_refs(open_payload)
    merged_refs = _head_refs(merged_payload)
    if open_refs is None or merged_refs is None:
        return None
    states: dict[str, PrState] = {}
    for name in open_refs | merged_refs:
        states[name] = PrState(
            has_open_pr=name in open_refs, pr_merged=name in merged_refs
        )
    return states


def build_facts(
    ages: dict[str, date],
    *,
    worktree_branches: frozenset[str] = frozenset(),
    pr_states: dict[str, PrState] | None = None,
) -> list[BranchFacts]:
    """Assemble what the sweep needs, failing SAFE when GitHub did not answer.

    ``pr_states=None`` means the lookup did not answer, and every branch is
    reported with unknown PR state — which :func:`~._sweep.classify` turns into
    ``KEEP_UNKNOWN``. That is the difference between a sweep that pauses when
    it is blind and one that deletes the repository.

    A branch PRESENT in ``ages`` but ABSENT from a successful ``pr_states`` has
    genuinely no pull request, so it is reported ``False/False`` and judged on
    age. That is the one place an absence legitimately means "no".
    """
    facts: list[BranchFacts] = []
    for name, last_commit in ages.items():
        if pr_states is None:
            state = UNKNOWN_PR
        else:
            state = pr_states.get(name, PrState(has_open_pr=False, pr_merged=False))
        facts.append(
            BranchFacts(
                name=name,
                last_commit=last_commit,
                in_worktree=name in worktree_branches,
                has_open_pr=state.has_open_pr,
                pr_merged=state.pr_merged,
            )
        )
    return facts


# EOF
