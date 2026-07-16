"""Data model for the CI-failure-reading primitive.

The distilled shapes a red CI run collapses to: :class:`JobFailure` (one
job's few-line reason) and :class:`RunFailures` (every failing job of a
run). :class:`CIWhyError` is the loud, UNKNOWN-not-green error the whole
primitive raises rather than pretending a run it cannot read is fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

#: A ``gh`` seam: given ``gh`` argv (without the leading ``gh``), return
#: stdout text. The one injection point that touches the network — every
#: resolver takes it so tests pass a plain callable and stay offline.
GhRunner = Callable[[list[str]], str]


class CIWhyError(RuntimeError):
    """gh is missing/unauthenticated/errored, or the target won't resolve.

    Raised, never swallowed into a reassuring "no failures": not knowing
    WHY a run is red is UNKNOWN, and UNKNOWN must not read as green. A CLI
    layer turns this into a loud stderr error plus a non-zero exit.
    """


@dataclass
class JobFailure:
    """The distilled failure of ONE job — a few lines, not a whole log."""

    job: str
    py: Optional[str] = None
    os: Optional[str] = None
    failed_tests: list[str] = field(default_factory=list)
    assertions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # ##[error] annotations
    tail: list[str] = field(default_factory=list)
    url: str = ""

    @property
    def signal(self) -> str:
        """Which tier produced the primary evidence (priority order)."""
        if self.failed_tests:
            return "pytest-summary"
        if self.assertions:
            return "pytest-assertion"
        if self.errors:
            return "annotation"
        if self.tail:
            return "tail"
        return "none"

    def context(self) -> str:
        """`` (py3.11, ubuntu)`` — the matrix context, or empty."""
        bits = [b for b in (self.py and f"py{self.py}", self.os) if b]
        return f" ({', '.join(bits)})" if bits else ""

    def primary_lines(
        self, *, max_assertions: int = 8, max_errors: int = 5, max_tests: int = 20
    ) -> list[str]:
        """The compact evidence to show under this job's header."""
        lines: list[str] = []
        if self.failed_tests:
            lines.extend(self.failed_tests[:max_tests])
            extra = len(self.failed_tests) - max_tests
            if extra > 0:
                lines.append(f"... and {extra} more failing test(s)")
        if self.assertions:
            lines.extend(self.assertions[:max_assertions])
        if not self.failed_tests and not self.assertions:
            if self.errors:
                lines.extend(f"##[error] {e}" for e in self.errors[:max_errors])
            elif self.tail:
                lines.append("(no pytest/annotation signal — last log lines:)")
                lines.extend(self.tail)
            else:
                lines.append("(failed, but gh returned no log content)")
        return lines

    def to_dict(self) -> dict:
        """A JSON-ready view of this job's distilled failure."""
        return {
            "job": self.job,
            "python": self.py,
            "os": self.os,
            "signal": self.signal,
            "failed_tests": self.failed_tests,
            "assertions": self.assertions,
            "errors": self.errors,
            "tail": self.tail,
            "url": self.url,
        }


@dataclass
class RunFailures:
    """Every distilled job failure for ONE run."""

    run_id: str
    workflow: str = ""
    title: str = ""
    branch: str = ""
    url: str = ""
    failures: list[JobFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        """A JSON-ready view of the run and its per-job failures."""
        return {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "title": self.title,
            "branch": self.branch,
            "url": self.url,
            "failures": [f.to_dict() for f in self.failures],
        }


__all__ = ["CIWhyError", "GhRunner", "JobFailure", "RunFailures"]
