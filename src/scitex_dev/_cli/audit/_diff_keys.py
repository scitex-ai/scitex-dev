#!/usr/bin/env python3
# Timestamp: 2026-08-13
# File: scitex_dev/_cli/audit/_diff_keys.py

"""Turn one auditor's stdout into stable violation KEYS.

Split out of ``_diff.py`` on 2026-08-13. That module had grown two jobs
that change for different reasons: READING one stream into keys (here),
and RELATING two streams to decide what a diff can be blamed for
(``_diff.py``). The tally-wording defect that prompted the split lived
entirely in this half while every caller in the tree uses the other.

The identity is ``(rule_code, file, normalized_message[:60])`` — line
numbers are deliberately dropped from both the file component and the
message, so an unrelated edit above a flagged construct does not re-key
every finding in that file as "new". The reasoning, and the trade it
accepts, are documented at length in ``_diff``'s module docstring.

Three line shapes are recognised, and the order matters:

1. a STRUCTURED finding (``_FINDING_RE``) — keyed on its parts;
2. a roll-up TALLY (``_TALLY_RE``) — keyed WITHOUT its counts, so
   arithmetic over findings already counted cannot masquerade as a new
   finding;
3. any other ``ERRO`` line — keyed on its whole normalized text rather
   than dropped, because "I could not parse this" must not silently
   become "there was nothing here".
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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

# Rule code for a per-auditor ROLL-UP TALLY — a line that COUNTS findings
# instead of being one:
#
#   ERRO: scitex-todo (/home/.../scitex-cards): project-structure:
#         14 error(s), 56 warning(s), 4 info
#
# The parenthesised subject defeats `<dist>:` above, so before this the
# tally fell through the ERRO fail-open and was keyed by `_unparsed_key`
# on its WHOLE line — counts included. Any component moving therefore
# swapped the key: one out, one in, total unchanged.
#
# A tally is derived from findings ALREADY keyed individually, so keying
# it double-counts them and guarantees a spurious net-new whenever any one
# moves. It can never be independent evidence about a diff.
#
# Measured by scitex-cards 2026-08-02 on a DOCS-ONLY PR: 131 at HEAD, 131
# at baseline, "1 net-new" — the pair differing only by `4 info` -> `6
# info`. Deterministic across a re-run of the same commit, so it read as a
# regression rather than a flake. Card:
# dev-audit-new-only-reports-net-new-with-identical-counts-20260802
#
# Excluded from ATTRIBUTION via NON_ATTRIBUTABLE_RULES, never from
# REPORTING — a silent drop would rebuild the defect the fail-open exists
# to prevent.
TALLY_RULE = "TALLY"

# EVERY AUDITOR SPELLS ITS OWN TALLY, and the noun is not shared. The
# project-structure auditor counts `error(s)` and `warning(s)`; the Python
# API auditor counts `violation(s)`:
#
#   ERRO: scitex-cards: Python API: 409 violation(s)
#
# Recognising only the first wording reproduced the ORIGINAL defect on the
# second spelling, so the noun is a set here rather than a literal.
# Measured by scitex-cards 2026-08-13: 141 keys at HEAD, 142 at baseline
# -- strictly FEWER findings -- reported as "1 net-new", that one key
# being this tally with a moved count. The gate blocked a PR that had
# REMOVED violations, and the only diff that could have satisfied it was
# one whose total happened to land back on the baseline's number.
#
# Anchored on the message TAIL so a real finding that merely mentions a
# count ("expected 3 error(s) in fixture") is not swallowed.
_TALLY_COUNT = r"\d+\s+(?:error|warning|violation|finding)\(s\)"
_TALLY_RE = re.compile(
    rf":\s*{_TALLY_COUNT}"
    rf"(?:,\s*{_TALLY_COUNT})*"
    r"(?:,\s*\d+\s+info)?\s*$"
)

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
                # A roll-up tally is keyed SEPARATELY so its moving counts
                # cannot masquerade as a net-new finding. Still keyed (so
                # it stays counted and disclosable), just not attributable.
                if _TALLY_RE.search(stripped):
                    # Drop the numeric tail from the identity so the tally
                    # keeps ONE stable key across runs. Leaving the counts
                    # in would still be safe (TALLY is non-attributable),
                    # but the key would churn on every run and show up as a
                    # spurious add/remove pair in any raw key comparison.
                    keys.add(
                        ViolationKey(
                            rule=TALLY_RULE,
                            file_line="",
                            message_excerpt=_TALLY_RE.sub(
                                "", _normalize_unparsed(stripped, roots)
                            )[:60],
                        )
                    )
                else:
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


# EOF
