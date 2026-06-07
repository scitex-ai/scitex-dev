#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_cli/audit/_diff.py

"""Diff-aware audit helpers (lead task #40 part b).

When run from a worktree on a feature branch, the per-leaf audits today
fail on *inherited* violations the agent didn't introduce — debt that was
already in ``develop`` before the branch forked. That blocks every new
PR on tech debt unrelated to the change at hand (the scitex-todo
5-iteration loop, agent-container's develop, etc.).

This module owns the **net-new** comparison: given the audit output at
HEAD and at the merge base, report ONLY findings present at HEAD that
were absent at base. Pre-existing violations stop blocking new PRs
while anything the PR actually introduces still trips CI.

Design:

1. **Worktree-detach** the base ref via ``git worktree add`` into a
   tmpdir so the caller's HEAD never moves. Cleans up via try/finally
   even on failure.
2. Run ``scitex-dev ecosystem audit-all`` twice (HEAD path, base path)
   via the existing ``--path PATH`` plumbing landed in PR #137.
3. Parse each auditor's output into a stable **violation key** —
   ``(rule_code, file:line, message_excerpt[:60])`` — that survives
   trivial reformatting but distinguishes genuinely-different findings.
4. Net-new = HEAD-keys − BASE-keys. Re-emit only the matching lines.

The first-cut violation identity intentionally trades precision for
simplicity: a refactor that shifts every line in a file will flag all
findings on that file as "new". That's accurate-ish in spirit (the
agent IS responsible for the change) and a refinement (line-anchor
fuzzy match) can land in a follow-up if it bites in practice.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


# Matches a single auditor finding line emitted by ``audit-cli`` /
# ``audit-project`` / siblings. Example shapes:
#
#   ERRO:   [PA-306 §3 no-mocks] scitex-dev: tests/.../file.py:43: STX-TQ007: ...
#   ERRO:   [PS-202 §2 src-tests-mirror] scitex-io: src/scitex_io/foo.py:NNN: ...
#   ERRO:   scitex-dev: scitex-dev ecosystem regen-umbrella: leaf token ...
#
# The captured groups are: level, rule_code, distribution, file_and_line,
# message. file_and_line is optional (some §1 rules are repo-level).
_FINDING_RE = re.compile(
    r"^(?P<level>ERRO|WARN|INFO):\s+"
    r"\[(?P<rule>[A-Z0-9\-§]+)[^\]]*\]\s+"
    r"(?P<dist>[\w\-]+):\s+"
    r"(?:(?P<file_line>[^:]+(?::\d+)?):\s+)?"
    r"(?P<msg>.+?)\s*$"
)


@dataclass(frozen=True)
class ViolationKey:
    """Identity that stays stable under whitespace + ANSI re-coloring.

    Two findings collide iff they come from the same auditor rule on
    the same file (and line, if line-locatable) with the same message
    prefix. We intentionally truncate the message at 60 chars so a
    cosmetic word change in a hint doesn't make a finding "new".
    """

    rule: str
    file_line: str  # "" if the finding is repo-wide
    message_excerpt: str


def extract_violation_keys(
    audit_stdout: str,
    *,
    distribution_filter: str | None = None,
) -> set[ViolationKey]:
    """Parse a per-auditor stdout stream into a set of violation keys.

    ``distribution_filter`` keeps only findings reported for the named
    dist (audit-all is polyrepo-capable; the filter avoids cross-leaf
    bleed when one stdout contains multiple distributions).
    """
    keys: set[ViolationKey] = set()
    for line in audit_stdout.splitlines():
        m = _FINDING_RE.match(line.strip())
        if m is None:
            continue
        if distribution_filter and m.group("dist") != distribution_filter:
            continue
        rule = m.group("rule")
        keys.add(
            ViolationKey(
                rule=rule,
                file_line=m.group("file_line") or "",
                message_excerpt=(m.group("msg") or "")[:60],
            )
        )
    return keys


def compute_net_new(
    head_stdout: str,
    base_stdout: str,
    *,
    distribution: str | None = None,
) -> set[ViolationKey]:
    """Return the set of violation keys present at HEAD but absent at BASE.

    Net-new ≠ "things the PR added". A refactor that shifts every line
    flags every finding as new (line is part of the identity). Good
    enough for the first cut — refine when the false-positive rate
    becomes a problem.
    """
    head = extract_violation_keys(head_stdout, distribution_filter=distribution)
    base = extract_violation_keys(base_stdout, distribution_filter=distribution)
    return head - base


def filter_to_net_new_lines(
    audit_stdout: str,
    net_new: set[ViolationKey],
    *,
    distribution: str | None = None,
) -> str:
    """Re-emit only those output lines whose key is in ``net_new``.

    Preserves non-finding lines (auditor banner / summary / disclaimer)
    so the caller still sees the audit's framing, but the violation
    bullets are restricted to net-new findings.
    """
    kept: list[str] = []
    for line in audit_stdout.splitlines():
        m = _FINDING_RE.match(line.strip())
        if m is None:
            kept.append(line)
            continue
        if distribution and m.group("dist") != distribution:
            kept.append(line)
            continue
        rule = m.group("rule")
        key = ViolationKey(
            rule=rule,
            file_line=m.group("file_line") or "",
            message_excerpt=(m.group("msg") or "")[:60],
        )
        if key in net_new:
            kept.append(line)
        # else: drop — inherited debt that BASE also reports
    return "\n".join(kept)


# --------------------------------------------------------------------- #
# Worktree-detach context manager                                        #
# --------------------------------------------------------------------- #


class DiffAwareSetupError(RuntimeError):
    """Raised when the base-ref worktree cannot be staged."""


@contextmanager
def worktree_at(repo: Path, ref: str) -> Iterator[Path]:
    """Stage ``ref`` as a temporary git worktree; yield its path.

    The caller's HEAD never moves — ``git worktree add`` clones the
    on-disk index of ``ref`` into a fresh dir under ``$TMPDIR``. On exit
    (success or failure) we always run ``git worktree remove --force``
    so the staging dir doesn't leak and the worktree registry stays
    clean.

    Raises ``DiffAwareSetupError`` on add failure (e.g. ref not found,
    locked worktree, dirty index) so the diff-aware caller can degrade
    gracefully (fall back to strict audit + a warning).
    """
    if not (repo / ".git").exists():
        raise DiffAwareSetupError(
            f"{repo} is not a git repository — diff-aware audit needs one."
        )
    stage = Path(tempfile.mkdtemp(prefix="audit-base-"))
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(stage), ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise DiffAwareSetupError(
                f"`git worktree add {ref}` failed (rc={r.returncode}): "
                f"{r.stderr.strip()}"
            )
        yield stage
    finally:
        # Best-effort teardown: --force survives a working tree with
        # local changes (the auditor occasionally writes pytest cache
        # files into the worktree). Worktree registry is reaped via
        # `prune` so a missed remove doesn't accumulate stubs.
        try:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(stage)],
                capture_output=True,
                check=False,
            )
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "prune"],
                capture_output=True,
                check=False,
            )


__all__ = [
    "DiffAwareSetupError",
    "ViolationKey",
    "compute_net_new",
    "extract_violation_keys",
    "filter_to_net_new_lines",
    "worktree_at",
]


# EOF
