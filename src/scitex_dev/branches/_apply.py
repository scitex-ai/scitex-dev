#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The half that deletes — and the guarantees that make it safe to schedule.

:mod:`._sweep` decides and :mod:`._facts` reports; this is the only module that
CHANGES anything, so every rule the constitution has about bulk operations
lands here.

DRY RUN IS THE DEFAULT, NOT A FLAG YOU REMEMBER
------------------------------------------------
``apply_plan(..., dry_run=True)`` is the signature's default. §2: "Dry-run every
bulk operation. Any change whose blast radius you cannot enumerate in advance
runs first in dry-run." A destructive default that must be opted OUT of is a
different program from one that must be opted IN to, and only one of them is
safe to wire to a scheduler.

ARCHIVE BEFORE DELETE, AND A FAILED ARCHIVE CANCELS THE DELETE
---------------------------------------------------------------
§5: "Forgetting is not the same as destroying. Record what you drop — branch,
sha, last-commit date, subject — and tag any commit reachable from no ref before
it goes."

So each drop is: write the archive line, tag the commit, THEN delete the branch —
and if either of the first two fails, THE DELETE DOES NOT HAPPEN. A branch that
survives a sweep is an inconvenience; a branch deleted with no tag and no log
line is the unrecoverable case the archive exists to prevent.

The failure is reported, never swallowed: one unarchivable branch must not
silence the sweep, and it must not look like a clean run either.

ONLY THE PLAN'S DROPS ARE TOUCHED
----------------------------------
`apply_plan` re-reads each decision's verdict rather than trusting the caller to
have filtered. The plan is the contract; a caller that hands over a list it
filtered itself is one refactor away from filtering it wrong.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Callable, NamedTuple, Sequence

from ._sweep import Decision, SweepPlan

#: Tag namespace for dropped branches, so a resurrection is `git checkout <tag>`.
#:
#: Namespaced by DATE because the same branch name is re-created routinely in
#: this fleet (`pr575`, `chore/changelog-*`), and a flat namespace would make
#: the second sweep's tag collide with the first's and fail — which, under the
#: archive-before-delete rule, would silently start refusing to drop anything.
TAG_PREFIX: str = "archive"


class DropOutcome(NamedTuple):
    """What happened to ONE branch. ``detail`` is populated on failure."""

    name: str
    archived: bool
    tagged: bool
    deleted: bool
    detail: str = ""

    @property
    def failed(self) -> bool:
        return not (self.archived and self.tagged and self.deleted)


class ApplyReport(NamedTuple):
    """The result of one apply, in a fixed shape (§2)."""

    dry_run: bool
    outcomes: tuple[DropOutcome, ...] = ()

    @property
    def failures(self) -> tuple[DropOutcome, ...]:
        return tuple(o for o in self.outcomes if o.failed)


def tag_name(decision: Decision, *, today: date, prefix: str = TAG_PREFIX) -> str:
    """Build the archive tag for a dropped branch.

    Slashes in the branch survive into the tag — git allows them, and flattening
    `feat/x` and `feat-x` onto one name would let two different branches claim
    the same archive.
    """
    return f"{prefix}/{today:%Y%m%d}/{decision.name}"


def archive_line(decision: Decision, sha: str, subject: str) -> str:
    """One record of a dropped branch: date, sha, name, subject.

    Exactly the four fields §5 asks for, in a shape `grep` and a human both
    read. Not JSON: this file is read by whoever is trying to recover something
    at an unhelpful hour.
    """
    return f"{decision.age_days:>4}d  {sha}  {decision.name}  {subject}"


def apply_plan(
    repo: Path,
    plan: SweepPlan,
    *,
    today: date,
    archive_path: Path,
    dry_run: bool = True,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    tag_prefix: str = TAG_PREFIX,
) -> ApplyReport:
    """Drop the plan's DROP-verdict branches, archiving each one first.

    Parameters
    ----------
    dry_run : bool
        Default TRUE. Nothing is written, tagged or deleted; the report
        describes what WOULD happen.

    Notes
    -----
    Order per branch is archive -> tag -> delete, and a failure at any step
    stops that branch there. See the module docstring: an unarchived deletion
    is the one outcome this design exists to prevent.
    """
    run = runner or subprocess.run
    outcomes: list[DropOutcome] = []

    for decision in plan.drops:
        sha, subject = _describe(repo, decision.name, run)
        if sha is None:
            outcomes.append(
                DropOutcome(
                    decision.name,
                    archived=False,
                    tagged=False,
                    deleted=False,
                    detail="could not read the branch's tip — refusing to drop "
                    "what cannot be recorded",
                )
            )
            continue

        if dry_run:
            outcomes.append(
                DropOutcome(decision.name, archived=False, tagged=False, deleted=False)
            )
            continue

        try:
            _append(archive_path, archive_line(decision, sha, subject))
        except OSError as exc:
            outcomes.append(
                DropOutcome(
                    decision.name,
                    archived=False,
                    tagged=False,
                    deleted=False,
                    detail=f"archive write failed, so the drop was cancelled — {exc}",
                )
            )
            continue

        tag = tag_name(decision, today=today, prefix=tag_prefix)
        if not _ok(run, repo, ("tag", tag, sha)):
            outcomes.append(
                DropOutcome(
                    decision.name,
                    archived=True,
                    tagged=False,
                    deleted=False,
                    detail=f"could not create tag {tag!r}, so the drop was cancelled",
                )
            )
            continue

        if not _ok(run, repo, ("branch", "-D", decision.name)):
            outcomes.append(
                DropOutcome(
                    decision.name,
                    archived=True,
                    tagged=True,
                    deleted=False,
                    detail="tagged and recorded, but the delete failed — the tag "
                    "is harmless and the branch is intact",
                )
            )
            continue

        outcomes.append(
            DropOutcome(decision.name, archived=True, tagged=True, deleted=True)
        )

    return ApplyReport(dry_run=dry_run, outcomes=tuple(outcomes))


def _describe(
    repo: Path, branch: str, run: Callable[..., subprocess.CompletedProcess]
) -> tuple[str | None, str]:
    """Return ``(sha, subject)`` for a branch tip, or ``(None, "")``."""
    proc = _git(run, repo, ("log", "-1", "--format=%H%x00%s", branch))
    if proc is None or proc.returncode != 0:
        return None, ""
    raw = (proc.stdout or "").strip()
    if "\x00" not in raw:
        return None, ""
    sha, _, subject = raw.partition("\x00")
    return (sha or None), subject


def _git(
    run: Callable[..., subprocess.CompletedProcess], repo: Path, args: Sequence[str]
) -> subprocess.CompletedProcess | None:
    try:
        return run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _ok(
    run: Callable[..., subprocess.CompletedProcess], repo: Path, args: Sequence[str]
) -> bool:
    proc = _git(run, repo, args)
    return proc is not None and proc.returncode == 0


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# EOF
