#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The vocabulary of the branch-hygiene sweep: what it may keep, and why.

Separated from the decision function (:mod:`._decide`) and from the
world (:mod:`._probe`) so the RULES can be read — and reviewed — without
running the half that deletes things.

WHY THE PROTECTED SET IS MATCHED EXACTLY, AND WHY IT NAMES TWO CLA BRANCHES
---------------------------------------------------------------------------
The CLA SIGNATURE STORE is not a topic branch. It holds every contributor
signature the org has collected, and it is spelled DIFFERENTLY in
different repositories.

A first draft of this rule spelled it ``^cla$``, which does NOT match
``cla-signatures``: a rehearsal marked that branch for deletion in all
36 repositories that carry it, which would have erased every signature
fleet-wide.

The obvious repair — ``cla*`` — is worse in the other direction: it
matches ``claude/*``, the agent worktree and sweep branches that are
precisely the garbage this sweep exists to remove. Too narrow, then too
broad, and both readings looked correct in review.

So the set is EXACT NAMES and nothing else. A glob is not available here
on purpose: the two failures above were both glob failures, and the cost
of the first one is unrecoverable.

THE SET NEEDS BOTH SPELLINGS, BECAUSE THE STORE IS BEING RENAMED. This
module first listed ``cla-signatures`` alone, because that is the name
the original near-miss was reported under. Running the remote leg in
dry-run against scitex-dev's own origin then proposed deleting ``cla``,
which by then was the signature store — the rename ``cla-signatures`` ->
``cla`` was in flight across 68 repositories, and the org reusable's
``branch:`` input has been flipped to ``cla``.

So the two names are the SAME store at two moments in a migration, not
two independently created stores. Both are listed because a fleet-wide
rename does not land everywhere at once: on scitex-hub the deletion of
``cla-signatures`` was REFUSED by branch protection, so that name is
still live there while ``cla`` is live elsewhere. A sweep that protects
only the destination name collects the source name wherever step 3 has
not completed, and vice versa.

``cla-signatures`` becomes VESTIGIAL as the rename finishes, and it stays
anyway. A rule that protects a name nobody uses costs nothing; the
alternative is re-learning this in the one repository that lagged.

The correction is a SECOND EXACT NAME and not a pattern: ``cla*`` covers
both and also swallows ``claude/*``, which is the third time that glob
would have been wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: A branch is stale when nothing has touched it for this long. The
#: operator's rule is one day; it is a default rather than a constant so
#: a caller can widen it, and it is never narrowed silently.
DEFAULT_MAX_AGE_HOURS = 24.0

#: Never deleted, at any age, on any host, local or remote. Read the
#: module docstring before adding to this — in particular before
#: converting any entry to a pattern.
#:
#: ``cla`` AND ``cla-signatures`` are the SAME CLA signature store at two
#: moments of an in-flight fleet-wide rename (``cla-signatures`` ->
#: ``cla``, 68 repositories). Both are listed because the rename does not
#: land everywhere at once — at least one repository still carries the
#: old name because branch protection REFUSED its deletion. Removing
#: either name silently arms the sweep against every repository sitting
#: on that side of the migration.
PROTECTED_EXACT = frozenset(
    {"main", "master", "develop", "cla", "cla-signatures"}
)

#: Refs whose NAME collides with the push refspec grammar, so
#: ``git push <remote> --delete <name>`` cannot say which one is meant.
#: ``origin`` was measured in the field; ``HEAD`` has the same shape.
#: These are REPORTED, never retried and never forced.
AMBIGUOUS_REMOTE_NAMES = frozenset({"origin", "HEAD"})

#: Lowercase fragments that identify a delete the REMOTE refused on
#: policy grounds — branch protection, ``allow_deletions: false``, a
#: pre-receive hook. Measured on scitex-hub, where deleting
#: ``cla-signatures`` failed for exactly this reason and failing was
#: CORRECT: the branch holds contributor signatures and is protected on
#: purpose.
#:
#: A refusal like this is not this sweep failing. It is the remote
#: stating a policy, permanently — retrying cannot help, forcing must not
#: be attempted, and a daily job that goes red on it is a job somebody
#: disables. So it is a KEEP with its own reason, exactly like an
#: ambiguous name, and it never reaches the failure count.
REMOTE_REFUSAL_SIGNS = (
    "protected branch",
    "protected branch hook declined",
    "cannot delete",
    "deletion of the current branch prohibited",
    "refusing to delete",
    "allow_deletions",
    "pre-receive hook declined",
)

# --------------------------------------------------------------------- #
# Keep reasons — why a branch survived this pass.                        #
# --------------------------------------------------------------------- #

#: In :data:`PROTECTED_EXACT`. Age is exactly what does not decide these.
KEEP_PROTECTED = "protected"

#: An OPEN pull request points here. Deleting the head branch CLOSES the
#: PR and destroys the review with it — a 1133-occurrence migration
#: branch sat in the delete set until this reason existed.
KEEP_OPEN_PR = "open-pr"

#: Nobody answered "does this have an open PR?". Unknown is not False:
#: it is checked ABOVE every drop reason, because the one outcome with
#: no cheap recovery is deleting an open PR's head on a half-answer.
KEEP_PR_UNKNOWN = "pr-state-unknown"

#: Touched inside the window and not already merged.
KEEP_RECENT = "recent"

#: Neither age signal could be read. Keep, and say which signal is
#: missing rather than treating an unreadable ref as an ancient one.
KEEP_AGE_UNKNOWN = "age-unknown"

#: The repository's own checked-out branch. The primary checkout is not
#: a worktree this sweep may remove.
KEEP_CURRENT_HEAD = "current-head"

#: Held by a worktree with uncommitted work that was touched inside the
#: window. This is the one branch of the logic whose failure is
#: unrecoverable, so it keeps BOTH the worktree and the branch.
KEEP_WORKTREE_BUSY = "worktree-busy"

#: A worktree holds it and its state could not be measured — dirty or
#: not, touched or not. Same posture as every other unknown: keep.
KEEP_WORKTREE_UNKNOWN = "worktree-state-unknown"

#: ``git worktree remove`` refused, and no force was authorised.
KEEP_WORKTREE_REFUSED = "worktree-remove-refused"

#: The name cannot be spelled unambiguously in a delete refspec.
KEEP_AMBIGUOUS_NAME = "ambiguous-ref-name"

#: The remote refused the delete on policy grounds. Reported, never
#: retried, never forced — and NOT counted as a failure, because the
#: remote is working correctly.
KEEP_REMOTE_PROTECTED = "remote-refused-protected"

#: The ref moved between the read and the write. Never delete what you
#: measured a moment ago and cannot re-confirm now.
KEEP_MOVED = "moved-during-pass"

# --------------------------------------------------------------------- #
# Drop reasons — why a branch is finished.                               #
# --------------------------------------------------------------------- #

#: Already merged into develop. Finished work goes HOWEVER RECENTLY
#: TOUCHED: without this, every branch whose PR landed today is kept,
#: and the keep set measured 16 branches across 6 repositories instead
#: of 1.
DROP_MERGED = "merged-into-develop"

#: Nothing has touched it inside the window.
DROP_STALE = "stale"

# --------------------------------------------------------------------- #
# What to do about a worktree that holds a droppable branch.             #
# --------------------------------------------------------------------- #

#: No worktree holds it.
WT_NONE = ""

#: ``git worktree remove`` WITHOUT ``--force``. The refusal is the
#: check: it fires on UNCOMMITTED WORK, which is the property worth
#: guarding, rather than on the mere existence of a worktree.
WT_REMOVE = "remove"

#: ``git worktree remove --force``. Authorised for ONE shape only —
#: uncommitted work whose FILES have not been touched inside the window.
#: Every use is named in the report together with the entries it
#: discarded.
WT_REMOVE_FORCE = "remove-force"

#: Keep the worktree and the branch.
WT_KEEP = "keep"


@dataclass(frozen=True)
class BranchFacts:
    """Everything observed about one branch, before any judgement.

    Every optional field is ``None`` when it could not be read, never a
    convenient default: the decision function has to be able to tell
    "measured, and the answer is no" from "nobody answered".
    """

    name: str
    sha: str = ""
    last_commit_epoch: float | None = None
    last_move_epoch: float | None = None
    merged: bool | None = None
    has_open_pr: bool | None = None
    worktree_path: str | None = None
    worktree_is_primary: bool = False
    worktree_dirty: bool | None = None
    worktree_touch_epoch: float | None = None

    @property
    def touched_epoch(self) -> float | None:
        """The most RECENT of the age signals, or None if there are none.

        The newest wins so a branch created seconds ago off an ancient
        base reads as young. Taking the tip commit alone is how a fresh
        ref acquires a three-week-old age.
        """
        stamps = [
            stamp
            for stamp in (self.last_commit_epoch, self.last_move_epoch)
            if stamp is not None
        ]
        return max(stamps) if stamps else None


@dataclass(frozen=True)
class Discarded:
    """Uncommitted work a forced worktree removal destroyed.

    Exists so the destruction leaves a record. Forcing is authorised for
    an abandoned worktree, and it is still the only path in this sweep
    that removes work which was never committed anywhere — so it must
    NAME the path and the entries afterwards.
    """

    branch: str
    path: str
    entries: tuple[str, ...] = ()


@dataclass(frozen=True)
class BranchVerdict:
    """One branch, one decision, and what the decision cost."""

    name: str
    sha: str = ""
    drop: bool = False
    reason: str = ""
    worktree_path: str | None = None
    worktree_action: str = WT_NONE
    executed: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sha": self.sha,
            "drop": self.drop,
            "reason": self.reason,
            "worktree_path": self.worktree_path,
            "worktree_action": self.worktree_action,
            "executed": self.executed,
            "error": self.error,
        }


@dataclass(frozen=True)
class CheckoutResult:
    """What the "put this checkout back on develop" step did.

    ``action`` is one of ``missing`` / ``on-develop`` / ``dirty`` /
    ``switched`` / ``would-switch`` / ``no-develop`` / ``failed``.
    A dirty tree is REPORTED and SKIPPED — never stashed, never forced.
    """

    package: str = ""
    repo: str = ""
    action: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "repo": self.repo,
            "action": self.action,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RepoResult:
    """One repository's whole sweep."""

    package: str = ""
    repo: str = ""
    checkout: CheckoutResult = field(default_factory=CheckoutResult)
    local: tuple[BranchVerdict, ...] = ()
    remote: tuple[BranchVerdict, ...] = ()
    discarded: tuple[Discarded, ...] = ()
    backup_restore: str = ""
    prune: str = ""
    error: str = ""

    @property
    def unreadable(self) -> bool:
        return bool(self.error)

    @property
    def dropped(self) -> tuple[BranchVerdict, ...]:
        return tuple(v for v in self.local + self.remote if v.drop)

    @property
    def kept(self) -> tuple[BranchVerdict, ...]:
        return tuple(v for v in self.local + self.remote if not v.drop)

    @property
    def failures(self) -> tuple[BranchVerdict, ...]:
        """Deletions that were attempted and went wrong.

        A KEPT branch may carry an ``error`` too — the text of a
        ``worktree remove`` refusal, or of a remote's branch-protection
        refusal — and neither is this sweep failing. Both are a guard
        working, recorded so the report can name it. Counting them here
        would put a daily job permanently in the red for behaving
        correctly, which is how a gate gets disabled.
        """
        return tuple(v for v in self.local + self.remote if v.error and v.drop)

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "repo": self.repo,
            "checkout": self.checkout.to_dict(),
            "local": [v.to_dict() for v in self.local],
            "remote": [v.to_dict() for v in self.remote],
            "discarded": [
                {"branch": d.branch, "path": d.path, "entries": list(d.entries)}
                for d in self.discarded
            ],
            "backup_restore": self.backup_restore,
            "prune": self.prune,
            "error": self.error,
        }


@dataclass(frozen=True)
class SweepOutcome:
    """Every repository this pass touched, plus how it was invoked."""

    results: tuple[RepoResult, ...] = ()
    executed: bool = False
    remote_pass: bool = False
    host: str = ""

    @property
    def dropped_count(self) -> int:
        return sum(len(r.dropped) for r in self.results)

    @property
    def kept_count(self) -> int:
        return sum(len(r.kept) for r in self.results)

    @property
    def failure_count(self) -> int:
        return sum(len(r.failures) for r in self.results)

    @property
    def unreadable(self) -> tuple[RepoResult, ...]:
        return tuple(r for r in self.results if r.unreadable)

    def summary_line(self) -> str:
        verb = "deleted" if self.executed else "would delete"
        return (
            f"{len(self.results)} repo(s): {verb} {self.dropped_count}, "
            f"kept {self.kept_count}, {self.failure_count} failure(s), "
            f"{len(self.unreadable)} unreadable"
        )

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "executed": self.executed,
            "remote_pass": self.remote_pass,
            "summary": self.summary_line(),
            "results": [r.to_dict() for r in self.results],
        }


def exit_code_for(outcome: SweepOutcome) -> int:
    """``2`` unreadable, ``1`` a delete failed, ``0`` otherwise.

    An UNREADABLE repository outranks a failed deletion because it is
    the failure with no other witness: a repo that could not be
    enumerated reports zero candidates, which is exactly what a clean
    repo reports. A refused deletion at least names itself.

    A dirty checkout, a busy worktree and an open PR are NOT failures.
    They are the steady state of a fleet with people working in it, and
    a daily job that goes red on them is a job somebody disables.
    """
    if outcome.unreadable:
        return 2
    if outcome.failure_count:
        return 1
    return 0


# EOF
