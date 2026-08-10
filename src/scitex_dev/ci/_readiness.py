#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/ci/_readiness.py
"""The verdict: one shape every time, whatever the answer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ._check_run import CheckRun
from ._exit_codes import ExitCode

__all__ = ["MergeReadiness", "Readiness"]


class Readiness(str, Enum):
    """The three-valued answer. Never collapsed."""

    #: Every check that ran belongs to the current head and passed.
    READY = "ready"
    #: A definite no, with at least one reason naming a specific check.
    NOT_READY = "not-ready"
    #: The question could not be answered. NOT a synonym for "no".
    CANNOT_DETERMINE = "cannot-determine"


@dataclass(frozen=True, slots=True)
class MergeReadiness:
    """The same shape every time, whatever the answer.

    A caller never has to guess which field exists on this call. Validated
    where it is built, so a malformed verdict fails here rather than three
    layers downstream in whatever decided to merge.
    """

    readiness: Readiness
    #: Fully qualified — ``owner/repo#N``. A bare number is ambiguous across
    #: this fleet's repositories and has already been misread once.
    pr: str
    head_sha: "str | None"
    reasons: tuple[str, ...] = field(default_factory=tuple)
    checks: tuple[CheckRun, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, Readiness):
            raise ValueError(
                f"readiness must be a Readiness, got {type(self.readiness).__name__}. "
                "A bare string or bool here is how 'could not tell' becomes 'yes'."
            )
        if "#" not in self.pr:
            raise ValueError(
                f"pr must be fully qualified as 'owner/repo#N', got {self.pr!r}. "
                "Two repositories in this fleet had a #521 on the same day; a "
                "bare number identified the wrong pull request."
            )
        if self.readiness is not Readiness.READY and not self.reasons:
            raise ValueError(
                f"readiness={self.readiness.value} with no reasons. A refusal "
                "that does not state what is wrong is unactionable — the "
                "caller cannot fix what it is not told."
            )

    @property
    def exit_code(self) -> int:
        return {
            Readiness.READY: ExitCode.READY,
            Readiness.NOT_READY: ExitCode.NOT_READY,
            Readiness.CANNOT_DETERMINE: ExitCode.CANNOT_DETERMINE,
        }[self.readiness]

    @property
    def merge_command(self) -> "str | None":
        """The pinned merge, ready to run. ``None`` unless READY.

        WHY THIS IS EMITTED RATHER THAN DESCRIBED, measured 2026-08-09:
        ``render()`` printed a 7-character SHA, and ``--match-head-commit``
        rejects it (``Could not coerce value "5b39c44" to GitObjectID``).
        So the documented two-step handed the reader a value from step one
        that step two refused. The pin is the entire safety mechanism, and
        a pin that errors is a pin people stop passing.

        Worse, an abbreviated SHA LOOKS like the value the flag wants. On
        the same day, one was reconstructed by padding a short form with
        invented hex; GitHub rejected it, which is the only reason the
        fabrication was caught.
        """
        if self.readiness is not Readiness.READY or not self.head_sha:
            return None
        owner_repo, _, number = self.pr.partition("#")
        return (
            f"gh pr merge {number} --repo {owner_repo} --merge "
            f"--match-head-commit {self.head_sha}"
        )

    def render(self) -> str:
        """Human-readable, one line per problem.

        The head is printed in FULL. It is the value the merge must be
        pinned to, and a display abbreviation is not a value.
        """
        lines = [f"{self.readiness.value}: {self.pr} @ {self.head_sha or 'unknown'}"]
        lines.extend(f"  - {reason}" for reason in self.reasons)
        command = self.merge_command
        if command:
            lines.append("")
            lines.append("merge PINNED to the head these checks describe:")
            lines.append(f"  {command}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "readiness": self.readiness.value,
            "pr": self.pr,
            "head_sha": self.head_sha,
            "exit_code": int(self.exit_code),
            "merge_command": self.merge_command,
            "reasons": list(self.reasons),
            "checks": [
                {
                    "name": c.name,
                    "state": c.state,
                    "head_sha": c.head_sha,
                    "stale": c.stale,
                    "ran": c.ran,
                }
                for c in self.checks
            ],
        }


# EOF
