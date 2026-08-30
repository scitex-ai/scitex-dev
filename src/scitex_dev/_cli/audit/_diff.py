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
   ``(rule_code, file, normalized_message[:60])`` — that survives
   trivial reformatting AND unrelated line shifts but distinguishes
   genuinely-different findings.
4. Net-new = HEAD-keys − BASE-keys. Re-emit only the matching lines.

Line-stable identity (2026-06-13, lead-directed refinement)
------------------------------------------------------------

The identity intentionally drops line numbers from both the file
component (no ``file:line``, just ``file``) and the normalized message
(any ``test.py:NN`` / ``line NN`` / ``:NN:`` substrings are scrubbed).
Reason: line numbers shift on every unrelated edit — a one-line
docstring tweak above a flagged construct would re-key every finding
in that file as "new", churning the ratchet and creating false
"regression" CI failures on patches that introduced zero violations.

The trade-off is that a file with N findings of the same rule is
keyed as ONE entry, so adding a new finding of that rule in the SAME
file with the SAME message stays invisible to the ratchet. We accept
that — it's the same trade lead documented in the spec ("a baseline
can only ever SHRINK; adding a new finding of an existing key class
in the same file is debt that the strict full audit still catches").
"Moved to evade" — moving a flagged construct to a different file —
still flips the file component and is correctly detected as new.
"""

from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# The keying half lives in `_diff_keys`; these names are RE-EXPORTED so
# `from ..._diff import ViolationKey` keeps resolving. Every importer in
# the tree spells it that way, and the split is not a reason to touch
# them.
from ._diff_keys import (  # noqa: F401
    TALLY_RULE,
    UNPARSED_RULE,
    ViolationKey,
    _ABS_PATH_RE,
    _ERRO_LINE_RE,
    _FINDING_RE,
    _TALLY_RE,
    _normalize_message,
    _normalize_unparsed,
    _strip_roots,
    _strip_trailing_lineno,
    _unparsed_key,
    extract_violation_keys,
)

#: Rules whose findings are NOT a property of the diff, and therefore can
#: never be attributed to one. A timing measurement describes the repo AND
#: the machine at that instant; net-new keying claims it describes the
#: change. Those are different objects, and no amount of best-of-N
#: reconciles them — widening N shrinks the straddle band around the
#: threshold without changing what the number is about, which is worse
#: because it looks fixed.
#:
#: Measured by scitex-cards, 2026-07-30, on a full audit of a develop
#: baseline worktree against each branch — 132 findings vs 132, the SOLE
#: difference being the §10 line:
#:
#:   * a PR adding a JAVASCRIPT file and one test was reported as
#:     introducing an import-time regression;
#:   * a PR DELETING a call, which measurably imported FASTER than develop
#:     (351/295/249ms vs 391/394/359ms, same machine, same minute), was
#:     reported with the identical finding text.
#:
#: So the same code produces the finding on one run and not another, and
#: under `--new-only` the blame lands on whoever happened to push.
#:
#: Excluded from ATTRIBUTION, never from REPORTING: the full audit still
#: emits these, and `partition_attributable` hands the count back so the
#: caller can disclose it. A silent exclusion here would rebuild the exact
#: defect the UNPARSED fail-open above exists to prevent.
#: TALLY joins them for a different reason: §10 findings are real but
#: describe the machine rather than the diff; a tally is not a finding at
#: all, it is arithmetic over findings already counted. Both are honestly
#: reported and neither can be blamed on a change.
#:
#: §1u is the third member and it arrives by the same argument as §10, one
#: axis over: it is a defect in `scitex/_mcp_tools/<pkg>.py`, a file that
#: ships in the UMBRELLA and is absent from the diff, the repository and
#: the dependency set of the package being graded. Whether it appears at
#: all depends on which `scitex` the job happened to resolve — measured on
#: scitex-io, where PR #167 resolved no umbrella and showed no finding
#: while a sibling PR resolved 2.28.13 and showed one, from identical
#: source. Net-new keying would hand that coin-flip to whoever pushed.
#: Reported, never attributed — same contract as the other two.
NON_ATTRIBUTABLE_RULES = frozenset({"§10", "§10w", "§1u", TALLY_RULE})


def is_attributable(key: ViolationKey) -> bool:
    """Can this finding honestly be blamed on a diff?"""
    return key.rule not in NON_ATTRIBUTABLE_RULES


def partition_attributable(
    keys: set[ViolationKey],
) -> tuple[set[ViolationKey], set[ViolationKey]]:
    """Split keys into (attributable, non_attributable).

    Returns BOTH halves on purpose. A caller that only wanted the first
    could have filtered inline; handing back the second is what makes the
    exclusion disclosable rather than invisible.
    """
    attributable = {k for k in keys if is_attributable(k)}
    return attributable, keys - attributable


def compute_net_new(
    head_stdout: str,
    base_stdout: str,
    *,
    distribution: str | None = None,
    roots: tuple[str, ...] = (),
) -> set[ViolationKey]:
    """Return the set of violation keys present at HEAD but absent at BASE.

    Net-new ≠ "things the PR added". A refactor that shifts every line
    flags every finding as new (line is part of the identity). Good
    enough for the first cut — refine when the false-positive rate
    becomes a problem.

    Findings from `NON_ATTRIBUTABLE_RULES` are removed: they are real, but
    they are not evidence about this diff. Use `compute_net_new_detailed`
    when the caller needs to report what was set aside.
    """
    net_new, _excluded = compute_net_new_detailed(
        head_stdout, base_stdout, distribution=distribution, roots=roots
    )
    return net_new


def compute_net_new_detailed(
    head_stdout: str,
    base_stdout: str,
    *,
    distribution: str | None = None,
    roots: tuple[str, ...] = (),
) -> tuple[set[ViolationKey], set[ViolationKey]]:
    """`compute_net_new`, plus the keys it declined to attribute.

    The second element is what a caller prints as "N finding(s) present at
    HEAD but not attributable to this change". Reporting zero when the
    number is non-zero is the failure mode this split exists to make
    impossible to reach by accident.
    """
    head = extract_violation_keys(
        head_stdout, distribution_filter=distribution, roots=roots
    )
    base = extract_violation_keys(
        base_stdout, distribution_filter=distribution, roots=roots
    )
    raw_net_new = head - base
    return partition_attributable(raw_net_new)


def filter_to_net_new_lines(
    audit_stdout: str,
    net_new: set[ViolationKey],
    *,
    distribution: str | None = None,
    roots: tuple[str, ...] = (),
) -> str:
    """Re-emit only those output lines whose key is in ``net_new``.

    Preserves non-finding lines (auditor banner / summary / disclaimer)
    so the caller still sees the audit's framing, but the violation
    bullets are restricted to net-new findings.
    """
    kept: list[str] = []
    for line in audit_stdout.splitlines():
        stripped = line.strip()
        m = _FINDING_RE.match(stripped)
        if m is None:
            # Mirror `extract_violation_keys`'s fail-open branch. If the
            # counter now keys an unparsed ERRO, the renderer must apply
            # the SAME net-new test to it — otherwise the two disagree
            # again, just in the opposite direction: a pre-existing
            # unparsed error would print on every run while counting
            # for nothing, which reads exactly like the bug this fixes.
            #
            # Non-ERRO lines (banner, summary, advisory prose) are kept
            # unconditionally — they are the audit's framing, not findings.
            if _ERRO_LINE_RE.match(stripped):
                if _unparsed_key(stripped, roots) in net_new:
                    kept.append(line)
                continue
            kept.append(line)
            continue
        if distribution and m.group("dist") != distribution:
            kept.append(line)
            continue
        rule = m.group("rule")
        # Key reconstruction MUST mirror `extract_violation_keys`'s
        # line-stripping or this filter would re-add inherited debt.
        key = ViolationKey(
            rule=rule,
            file_line=_strip_trailing_lineno(m.group("file_line") or ""),
            message_excerpt=_normalize_message(m.group("msg") or "")[:60],
        )
        if key in net_new:
            kept.append(line)
        # else: drop — inherited debt that BASE also reports
    return "\n".join(kept)


# Worktree staging lives in `._diff_worktree` — a VCS concern, not a
# parsing one. Re-exported here so existing importers are unaffected.
from ._diff_worktree import DiffAwareSetupError, worktree_at  # noqa: E402

__all__ = [
    "DiffAwareSetupError",
    "ViolationKey",
    "compute_net_new",
    "extract_violation_keys",
    "filter_to_net_new_lines",
    "worktree_at",
]


# EOF
