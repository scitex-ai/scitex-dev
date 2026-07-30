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

import re
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


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

# An ERRO line the structured parser CANNOT key must still count.
#
# Measured 2026-07-29 on real ``audit-all`` output:
#
#   scitex-io   : 49 level-prefixed lines, 0 parsed, 0 keys, 33 of them ERRO
#   scitex-stats: 1962 level-prefixed, 1917 parsed, 45 dropped, 29 of them ERRO
#
# For scitex-io that is the whole P0 in one line: the gate PRINTS 33
# errors and produces ZERO keys, so nothing can be net-new and it exits
# 0. `extract_violation_keys` skipped what it could not parse while
# `filter_to_net_new_lines` kept the same line as framing — the renderer
# and the counter disagreed by construction and neither knew.
#
# Three real ERRO shapes `_FINDING_RE` cannot express:
#
#   ERRO: scitex-io: CLI conventions: not-auditable: unknown
#       ^ no bracketed rule tag at all (the module docstring above
#         advertises this shape; the regex has never matched it)
#   ERRO: scitex-io (/home/.../scitex-io): project-structure: 31 error(s)
#       ^ subject carries a parenthesised path, so ``<dist>:`` fails
#   ERRO:   [E] [PS-221 §3 ...] /home/.../pyproject.toml: requirement ...
#       ^ TWO bracket groups, and the subject after them is a PATH
#
# The fix is deliberately NOT a hairier regex — a hairier regex is how
# this got here. Anything the structured parser cannot key becomes an
# UNPARSED key, so it participates in the diff and can block.
#
# WHY ONLY ``ERRO`` (this is load-bearing, not laziness): the level
# prefix is NOT a finding discriminator. Multi-line advisory BANNERS
# carry it on every continuation line — a scitex-dev run measured 432
# level-prefixed lines of which 431 were currency-gate prose and 1 was
# a finding. Failing open on any level would have manufactured ~430
# findings and blocked every PR in the fleet: a gate that cannot pass,
# which is exactly as broken as the gate that cannot fail. Advisories
# are emitted at WARN/INFO; restricting fail-open to ERRO keeps prose
# out while letting every real error through. See card
# advisory-banner-impersonates-finding-line-20260729 for the emitter-
# side fix that would let this widen safely.
_ERRO_LINE_RE = re.compile(r"^ERRO:\s")

# Rule code carried by a finding the structured parser could not key.
# Reported separately from parsed findings so "N findings" never
# silently means "N findings plus however many we could not read".
UNPARSED_RULE = "UNPARSED"

# Absolute checkout roots differ between HEAD and the temporary baseline
# worktree, so a raw-text identity MUST drop them — otherwise every
# unparsed line reads as net-new on every run and the gate blocks
# everything. Collapses ``/home/x/proj/pkg/src/a.py`` to ``a.py``.
_ABS_PATH_RE = re.compile(r"(?<![\w.])/(?:[\w.\-]+/)+")


# A DIRECTORY path has no trailing slash, so `_ABS_PATH_RE` leaves its LAST
# component — which for the two trees compared here IS the checkout name, and
# those differ by construction. `(.../floor)` vs `(.../base-abc)` on the same
# finding gave two identities: one phantom net-new plus one phantom
# disappearance, on every PR emitting such a line (measured 2026-07-31 on
# scitex-cards: 95 keys each side, 1 new, 1 gone). `audit` is required, so
# that phantom blocked merges repo-wide.
#
# Widening `_ABS_PATH_RE` instead would eat the stable basename of FILE paths
# and collapse distinct findings — the collision `_unparsed_key` exists to
# avoid. The roots are known facts the caller already computes.
# Longest first, so a root prefixing another leaves no fragment.
def _strip_roots(line: str, roots: tuple[str, ...]) -> str:
    for root in sorted((r for r in roots if r), key=len, reverse=True):
        line = line.replace(root, "<TREE>")
    return line


def _normalize_unparsed(line: str, roots: tuple[str, ...] = ()) -> str:
    """Line-stable identity for a finding the structured parser missed.

    Applies the same line-number scrubbing as a parsed finding's
    message, then strips absolute directory prefixes so HEAD and the
    detached baseline worktree — which live at different paths by
    construction — produce the same identity for the same finding.
    """
    return _normalize_message(_ABS_PATH_RE.sub("", _strip_roots(line, roots)))


# Strips trailing ``:NN`` line-number suffix from a file-path token.
# Anchored at end-of-string so a colon inside the path (Windows drives,
# URL-shaped paths) cannot mis-fire.
_TRAILING_LINENO_RE = re.compile(r":\d+$")

# Strips line-number-shaped substrings from the message excerpt so a
# rule whose detail embeds ``... at line NN ...`` or ``tests/foo.py:NN:``
# keys identically across unrelated line shifts. We deliberately match
# only digit runs that look like line refs — bare numbers in prose
# (``2 mocks found``) are preserved so two genuinely-distinct findings
# don't collide.
_MSG_LINENO_PATTERNS = (
    re.compile(r":\d+(?=:|$|\s)"),  # ``...py:43`` or ``foo:88 ``
    re.compile(r"\bline\s+\d+\b", re.I),  # ``at line 88``
)


def _strip_trailing_lineno(file_token: str) -> str:
    """Drop the trailing ``:NN`` from a file-path token, if present.

    Used to derive the line-stable file component of the identity.
    A bare ``foo/bar.py`` round-trips unchanged; ``foo/bar.py:43`` →
    ``foo/bar.py``; ``some:thing:42`` → ``some:thing`` (only the
    trailing decimal suffix is stripped).
    """
    return _TRAILING_LINENO_RE.sub("", file_token)


def _normalize_message(msg: str) -> str:
    """Strip line-number substrings from a finding's message.

    Ratchet stability depends on the identity not embedding line
    references that shift on unrelated edits. The message excerpt is
    the loosest component (any rule can put arbitrary text there), so
    we additionally scrub two common shapes: trailing ``:NN``-style
    file/line refs and ``at line NN`` prose.

    Leaves all other content intact — a rule whose detail mentions
    ``2 mocks found in tests/conftest.py`` keeps the file mention,
    because that's part of WHAT changed, not a line-shift artefact.
    """
    out = msg
    for pat in _MSG_LINENO_PATTERNS:
        out = pat.sub("", out)
    # Collapse the whitespace gaps the substitutions can leave behind
    # so ``foo  bar`` doesn't collide-or-not-collide with ``foo bar``.
    return " ".join(out.split())


@dataclass(frozen=True)
class ViolationKey:
    """Identity that stays stable under whitespace, ANSI re-coloring,
    AND unrelated line shifts.

    Two findings collide iff they come from the same auditor rule on
    the same file with the same normalized message prefix. Line numbers
    are deliberately NOT part of the identity — see the module
    docstring's "line-stable identity" section for the rationale and
    the trade-off (debt of the same rule code in the same file with
    the same message keys as one entry; "moved to evade" — moving the
    flagged construct to a different file — still flips the identity).

    Field name carries forward ``file_line`` for ON-WIRE compatibility
    with any pickled / cached ViolationKey sets; the VALUE no longer
    contains the line number.
    """

    rule: str
    file_line: str  # file path with NO trailing ``:NN`` — name kept for compat
    message_excerpt: str


def _unparsed_key(stripped_line: str, roots: tuple[str, ...] = ()) -> ViolationKey:
    """Identity for an ERRO line the structured parser could not key.

    Uses the WHOLE normalized line, not a 60-char excerpt. A parsed
    finding can afford truncation because ``rule`` and ``file_line``
    still separate it from its neighbours; an unparsed one has neither
    — every one of them keys as ``(UNPARSED, "")`` plus the excerpt, so
    truncating is the only thing standing between two different errors
    and a single identity. Measured on real output: excerpting 33 ERRO
    lines to 60 chars collapsed them to 4 keys, which would let a new
    error hide behind an existing one whose first 60 characters happen
    to match.
    """
    return ViolationKey(
        rule=UNPARSED_RULE,
        file_line="",
        message_excerpt=_normalize_unparsed(stripped_line, roots),
    )


def extract_violation_keys(
    audit_stdout: str,
    *,
    distribution_filter: str | None = None,
    roots: tuple[str, ...] = (),
) -> set[ViolationKey]:
    """Parse a per-auditor stdout stream into a set of violation keys.

    ``distribution_filter`` keeps only findings reported for the named
    dist (audit-all is polyrepo-capable; the filter avoids cross-leaf
    bleed when one stdout contains multiple distributions).
    """
    keys: set[ViolationKey] = set()
    for line in audit_stdout.splitlines():
        stripped = line.strip()
        m = _FINDING_RE.match(stripped)
        if m is None:
            # FAIL OPEN. An error we cannot read is still an error; the
            # old `continue` here is what let the required gate print
            # errors and exit 0.
            #
            # Deliberately NOT subject to `distribution_filter`: an
            # unparsed line has no readable dist, and "I could not tell
            # whose this is" must not collapse into "not theirs". An
            # unknown is a third value, not a quiet no.
            if _ERRO_LINE_RE.match(stripped):
                keys.add(_unparsed_key(stripped, roots))
            continue
        if distribution_filter and m.group("dist") != distribution_filter:
            continue
        rule = m.group("rule")
        file_token = _strip_trailing_lineno(m.group("file_line") or "")
        msg_norm = _normalize_message(m.group("msg") or "")
        keys.add(
            ViolationKey(
                rule=rule,
                file_line=file_token,
                message_excerpt=msg_norm[:60],
            )
        )
    return keys


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
NON_ATTRIBUTABLE_RULES = frozenset({"§10", "§10w"})


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
