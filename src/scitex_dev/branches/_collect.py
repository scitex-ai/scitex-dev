#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/branches/_collect.py
"""Read the world, and SAY WHAT COULD NOT BE READ.

The parsers in `_facts` are pure: given text, they produce facts. This module
is the layer that goes and gets the text — `git for-each-ref`, `git worktree
list`, `gh pr list` — and it is deliberately separate, because it is the only
part of the sweep that can be wrong about the WORLD rather than about its own
logic.

WHY THIS LAYER IS THE DANGEROUS ONE. The sweep DELETES on what it reads here.
Measured on 2026-08-15, twice, in this repository:

  * an audit walker returned 1142 files with `fd` present and 1227 without —
    the same tree, two answers, no announcement.
  * `Path.exists()` raised on one host and answered on three, because a
    directory existed on one machine and not the others.

Both were environment-dependent reads that looked like facts. A sweep that
deletes branches on that class of answer must treat "I could not read it" as
its own outcome, never as a quiet False.

SO: :func:`collect_facts` returns the facts AND a :class:`CollectionReport`
naming every source it could not read. `classify` already keeps a branch whose
PR state is UNKNOWN — this makes the unknown VISIBLE instead of merely safe.
Being safe silently is how a stalled sweep looks like a clean one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, NamedTuple, Sequence

from ._facts import (
    BRANCH_AGE_FORMAT,
    build_facts,
    parse_branch_ages,
    parse_pr_states,
    parse_worktree_branches,
)

#: A command runner: argv -> (exit_code, stdout). Injected so tests drive a
#: REAL callable rather than patching a module internal (the ecosystem linter
#: forbids the latter, and it is right: a test that rewrites production
#: internals is not testing production).
Runner = Callable[[Sequence[str]], "tuple[int, str]"]


class CollectionReport(NamedTuple):
    """What was read, and — the load-bearing half — what was not."""

    #: Sources that failed to answer, named so a reader can go fix them.
    #: Empty means every source answered; it does NOT mean every answer was
    #: interesting.
    unreadable: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        """True only when every source answered.

        A sweep may still act on an incomplete collection — `classify` keeps
        anything it cannot judge — but the operator must be told, because
        "kept 12 branches" and "kept 12 branches because gh was unreachable"
        are different reports and only one of them is a to-do list.
        """
        return not self.unreadable


def run_command(argv: Sequence[str]) -> tuple[int, str]:
    """Default :data:`Runner`: run argv, return (exit_code, stdout).

    Never raises on a non-zero exit — the caller decides what an unanswered
    source means, and a crash here would deny it that choice.
    """
    try:
        proc = subprocess.run(list(argv), capture_output=True, text=True)
    except OSError as exc:  # binary missing, not executable, ...
        return 127, str(exc)
    return proc.returncode, proc.stdout


def collect_facts(
    repo: Path,
    *,
    runner: Runner = run_command,
) -> tuple[list, CollectionReport]:
    """Gather every fact the sweep needs, recording what could not be read.

    The PR source is treated differently from the git sources ON PURPOSE.
    `git for-each-ref` failing means we do not know the branches at all, so
    there is nothing to sweep and the caller gets an empty list. `gh pr list`
    failing means we know the branches but not their PR state — which
    `parse_pr_states` represents as ``None``, and `build_facts` turns into
    UNKNOWN per branch, and `classify` turns into KEEP. The sweep still runs;
    it simply refuses to delete anything it cannot vouch for.
    """
    unreadable: list[str] = []

    # BRANCH_AGE_FORMAT, never a hand-written format string. The module
    # exports it so the producer and the parser cannot drift — and writing
    # one from memory here got the FIELD ORDER BACKWARDS on the first
    # attempt, which parsed to zero branches and would have swept nothing
    # while reporting a clean run.
    rc, ages_out = runner(
        [
            "git",
            "-C",
            str(repo),
            "for-each-ref",
            f"--format={BRANCH_AGE_FORMAT}",
            "refs/heads/",
        ]
    )
    if rc != 0:
        # No branch list means no sweep. Returning an empty plan here is the
        # honest outcome: we did not decide to keep everything, we failed to
        # look, and the report says which.
        return [], CollectionReport(("git for-each-ref",))
    ages = parse_branch_ages(ages_out)

    rc, wt_out = runner(["git", "-C", str(repo), "worktree", "list", "--porcelain"])
    if rc != 0:
        # A branch checked out in a worktree must never be deleted. Losing
        # this list is therefore NOT survivable by keeping less — it would
        # make the sweep delete MORE. Refuse outright.
        return [], CollectionReport(("git worktree list",))
    in_worktree = parse_worktree_branches(wt_out)

    # TWO listings, because `parse_pr_states` needs both and returns None if
    # EITHER fails: "a branch absent from a half-read listing is
    # indistinguishable from a branch with no PR, and the sweep would read
    # that absence as permission to drop." Half an answer is worse than none
    # here, so a single failure discards both.
    rc_open, open_out = runner(
        ["gh", "pr", "list", "--state", "open", "--json", "headRefName"]
    )
    rc_merged, merged_out = runner(
        ["gh", "pr", "list", "--state", "merged", "--json", "headRefName"]
    )
    if rc_open != 0 or rc_merged != 0:
        pr_states = None
        unreadable.append("gh pr list")
    else:
        pr_states = parse_pr_states(open_out, merged_out)
        if pr_states is None:
            unreadable.append("gh pr list (unparseable output)")

    facts = build_facts(
        ages, worktree_branches=in_worktree, pr_states=pr_states
    )
    return facts, CollectionReport(tuple(unreadable))


def render_collection(report: CollectionReport) -> str:
    """Say plainly what was not read, or say that everything was."""
    if report.is_complete:
        return "all fact sources answered"
    return (
        f"{len(report.unreadable)} source(s) COULD NOT BE READ: "
        + ", ".join(report.unreadable)
        + ". Branches whose state depends on them are KEPT, not deleted — so "
        "this run is safe but INCOMPLETE, and re-running it once the source "
        "is reachable may drop more."
    )


__all__ = [
    "CollectionReport",
    "Runner",
    "collect_facts",
    "render_collection",
    "run_command",
]

# EOF
